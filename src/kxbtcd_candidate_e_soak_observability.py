"""Durable, offline-testable soak evidence. No network or execution behavior.

The sampler supplies cumulative source counters and real host/bridge readings;
this module never substitutes zero for missing evidence. Transport producers
submit individual local latency observations through record_latency(). Small
runs retain exact quantiles; high-volume runs use a bounded deterministic
reservoir and an on-disk SQLite index sealed only at finalization.
Offline fixtures must identify themselves as offline_fixture. A production
entry point must require production provenance and wire the actual producers.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import heapq
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from .kxbtcd_candidate_e_soak_archive import file_sha256, write_json_atomic


class SoakObservabilityError(RuntimeError):
    pass


COUNTERS = (
    "coinbase_message_count", "coinbase_heartbeat_count",
    "coinbase_reconnect_attempts", "coinbase_reconnect_successes",
    "kalshi_snapshot_count", "kalshi_delta_count", "kalshi_sequence_gap_count",
    "kalshi_recovery_count", "kalshi_reconnect_attempts",
    "kalshi_reconnect_successes", "kalshi_ping_attempts",
    "kalshi_pong_successes", "kalshi_pong_timeouts", "event_rollover_count",
    "raw_bytes_written", "compressed_bytes_written",
)
GAUGES = (
    "process_cpu_seconds", "process_memory_rss_bytes",
    "host_memory_available_bytes", "host_load_1m", "host_load_5m",
    "host_load_15m", "filesystem_free_bytes",
)
LATENCIES = (
    "coinbase_receive_interarrival", "kalshi_ping_pong_rtt",
    "event_rollover_recovery", "rest_request_duration",
    "receive_to_raw_persist_duration", "raw_persist_to_parse_apply_duration",
    "receive_to_readiness_evaluation_duration",
)
SAMPLE_FIELDS = frozenset(COUNTERS + GAUGES + (
    "coinbase_connection_generation", "kalshi_connection_generation",
    "chrony_signed_offset_ms", "chrony_absolute_offset_ms", "chrony_leap_status",
    "clock_status", "clock_evidence_age_ns", "linux_boot_id", "time_namespace_id",
))
READINESS_INPUT_CONTRACTS = frozenset({
    "legacy_coinbase_ws_and_kalshi",
    "v2_exact_rest_candle_and_kalshi",
})
NS = 1_000_000_000
METRIC_SAMPLE_INTERVAL_NS = 60 * NS
# Metric evidence has a hard 60-second maximum interval.  Schedule its
# durable write before that boundary so normal process or filesystem jitter
# cannot turn an otherwise healthy attempt into a false failure.
METRIC_SAMPLE_SCHEDULING_MARGIN_NS = 5 * NS
# Per-message latency is diagnostic evidence, not model training input.  Keep a
# deterministic, bounded representative sample per metric so a long-running
# bot cannot fill local or S3 storage merely by observing healthy traffic.
DEFAULT_LATENCY_SAMPLE_CAP = 4096
TOKEN = re.compile(r"[A-Za-z0-9_.:\[\]-]{1,160}\Z")


def _number(value, *, signed=False, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (not signed and value < 0)
            or (integer and not isinstance(value, int))):
        raise SoakObservabilityError("invalid numeric evidence")
    return value


def _utc(value):
    if not isinstance(value, str):
        raise SoakObservabilityError("UTC timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SoakObservabilityError("invalid UTC timestamp") from None
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise SoakObservabilityError("timestamp must explicitly use UTC")
    return value


def _token(value):
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise SoakObservabilityError("invalid evidence token")
    if any(marker in value.upper() for marker in ("PRIVATE_KEY", "API_KEY", "SECRET")):
        raise SoakObservabilityError("secret marker in evidence")
    return value


class SoakObservability:
    """One run-owned sink; producers must stop before finish().

    sample_metrics(now_ns) must return exactly SAMPLE_FIELDS. Counts are
    cumulative since this attempt, not since the most recent connection.
    declare_latency_producers must enumerate the actually wired producers;
    count=0 remains explicit when, for example, no rollover occurred.
    """

    def __init__(self, *, root, sample_metrics, utc_now_text,
                 evidence_mode, expected_boot_id, declared_latency_producers,
                 required_generation_sources=("coinbase", "kalshi"),
                 readiness_input_contract="legacy_coinbase_ws_and_kalshi",
                 readiness_interval_seconds=1, monotonic_ns=time.monotonic_ns,
                 latency_sample_cap=DEFAULT_LATENCY_SAMPLE_CAP):
        if evidence_mode not in {"production", "offline_fixture"}:
            raise SoakObservabilityError("explicit evidence provenance required")
        if set(declared_latency_producers) != set(LATENCIES):
            raise SoakObservabilityError("all latency producers must be wired")
        required_generation_sources = tuple(required_generation_sources)
        if (not required_generation_sources
                or not set(required_generation_sources) <= {"coinbase", "kalshi"}
                or len(set(required_generation_sources)) != len(required_generation_sources)):
            raise SoakObservabilityError("invalid required generation sources")
        if readiness_input_contract not in READINESS_INPUT_CONTRACTS:
            raise SoakObservabilityError("invalid readiness input contract")
        _number(readiness_interval_seconds)
        if not 0 < readiness_interval_seconds <= 5:
            raise SoakObservabilityError("readiness interval must be <=5 seconds")
        if isinstance(latency_sample_cap, bool) or not isinstance(latency_sample_cap, int) or latency_sample_cap < 1:
            raise SoakObservabilityError("latency sample cap must be positive")
        self.root = Path(root)
        self.sample_metrics = sample_metrics
        self.utc_now_text = utc_now_text
        self.monotonic_ns = monotonic_ns
        self.evidence_mode = evidence_mode
        self.expected_boot_id = _token(expected_boot_id)
        self.required_generation_sources = frozenset(required_generation_sources)
        self.readiness_input_contract = readiness_input_contract
        self.interval_ns = int(readiness_interval_seconds * NS)
        self.lock = threading.RLock()
        self.started = self.closed = self.failed = False
        self.last_sample_ns = self.last_observation_ns = None
        self.last_sample = self.last_snapshot = self.last_readiness = None
        self.transitions = 0
        self.last_state = None
        self.sample_count = self.readiness_count = 0
        self._hashes = {}
        self._streams = {}
        self.db = None
        self.latency_sample_cap = latency_sample_cap
        self._latency_counts = {name: 0 for name in LATENCIES}
        self._latency_samples = {name: [] for name in LATENCIES}

    def _check(self):
        if not self.started or self.closed or self.failed:
            raise SoakObservabilityError("evidence sink unavailable")

    def start(self, *, run_id, started_monotonic_ns):
        with self.lock:
            if self.started:
                raise SoakObservabilityError("evidence sink already started")
            self.run_id = _token(run_id)
            self.start_ns = _number(started_monotonic_ns, integer=True)
            # Exclusive ownership: never overwrite an earlier attempt.
            self.root.mkdir(parents=True, exist_ok=False)
            self.started = True
            try:
                for name in ("readiness", "metrics", "latency", "source_events"):
                    self._streams[name] = (self.root / (name + ".jsonl")).open("xb")
                    self._hashes[name] = sha256()
                self.db = sqlite3.connect(self.root / "latency.sqlite", check_same_thread=False)
                self.db.execute("PRAGMA temp_store=FILE")
                self.db.execute("PRAGMA cache_size=-2048")
                self.db.execute("CREATE TABLE latency (name TEXT, value INTEGER)")
                self.db.execute("CREATE INDEX latency_values ON latency(name, value)")
            except Exception:
                self.failed = True
                self.abort()
                raise SoakObservabilityError("cannot initialize durable telemetry") from None

    def _write(self, name, value):
        self._write_many(name, (value,))

    def _write_many(self, name, values):
        try:
            payload = b"".join(
                (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
                for value in values
            )
            if not payload:
                return
            stream = self._streams[name]
            if os.fstat(stream.fileno()).st_size != stream.tell():
                raise OSError("evidence file changed outside writer")
            if stream.write(payload) != len(payload):
                raise OSError("short evidence write")
            stream.flush()
            os.fsync(stream.fileno())
            self._hashes[name].update(payload)
        except Exception:
            self.failed = True
            raise SoakObservabilityError("durable telemetry write failed") from None

    def _envelope(self, now_ns):
        _number(now_ns, integer=True)
        if now_ns < self.start_ns:
            raise SoakObservabilityError("evidence precedes run")
        return dict(schema_version="candidate_e_soak_observability.v1",
                    run_id=self.run_id, evidence_mode=self.evidence_mode,
                    utc=_utc(self.utc_now_text()), monotonic_ns=now_ns)

    def record_latency(self, name, *, started_ns, ended_ns):
        with self.lock:
            self._check()
            try:
                if name not in LATENCIES:
                    raise SoakObservabilityError("unknown latency metric")
                _number(started_ns, integer=True)
                _number(ended_ns, integer=True)
                if ended_ns < started_ns or started_ns < self.start_ns:
                    raise SoakObservabilityError("latency monotonic regression")
                duration = ended_ns - started_ns
                observation_index = self._latency_counts[name]
                self._latency_counts[name] += 1
                # Keep the smallest stable SHA-256 priorities.  This is a
                # deterministic uniform reservoir without a source of mutable
                # randomness or unbounded disk writes.
                priority = int.from_bytes(
                    sha256(f"{name}:{observation_index}".encode("ascii")).digest()[:8], "big"
                )
                sample = self._latency_samples[name]
                entry = (-priority, observation_index, started_ns, ended_ns, duration)
                if len(sample) < self.latency_sample_cap:
                    heapq.heappush(sample, entry)
                elif priority < -sample[0][0]:
                    heapq.heapreplace(sample, entry)
            except Exception:
                self.failed = True
                raise SoakObservabilityError("latency evidence failed") from None

    def record_source_event(self, *, source, event, generation, monotonic_ns, event_ticker=None, failure_class=None,
                            close_code=None, reconnect_reason=None):
        """Persist generation/recovery lineage without payloads or credentials."""
        with self.lock:
            self._check()
            try:
                if source not in {"coinbase", "kalshi"} or event not in {
                    "generation_open", "reconnect_attempt", "recovered", "sequence_gap",
                    "rollover", "ping", "pong", "pong_timeout", "disconnected", "transport_error",
                }:
                    raise SoakObservabilityError("invalid source event")
                _number(generation, integer=True)
                if event_ticker is not None:
                    _token(event_ticker)
                if failure_class is not None:
                    _token(failure_class)
                if close_code is not None:
                    _number(close_code, integer=True)
                    if not 1000 <= close_code <= 4999:
                        raise SoakObservabilityError("invalid transport close code")
                if reconnect_reason is not None:
                    _token(reconnect_reason)
                if event != "transport_error" and failure_class is not None:
                    raise SoakObservabilityError("failure class only allowed for transport error")
                if event != "transport_error" and close_code is not None:
                    raise SoakObservabilityError("close code only allowed for transport error")
                if event != "reconnect_attempt" and reconnect_reason is not None:
                    raise SoakObservabilityError("reconnect reason only allowed for reconnect attempt")
                record = self._envelope(monotonic_ns)
                record.update(source=source, event=event, generation=generation, event_ticker=event_ticker)
                if failure_class is not None:
                    record["failure_class"] = failure_class
                if close_code is not None:
                    record["close_code"] = close_code
                if reconnect_reason is not None:
                    record["reconnect_reason"] = reconnect_reason
                self._write("source_events", record)
            except Exception:
                self.failed = True
                raise SoakObservabilityError("source event evidence failed") from None

    def _sample(self, now_ns, readiness, *, finalization=False):
        value = dict(self.sample_metrics(now_ns))
        if set(value) != SAMPLE_FIELDS:
            raise SoakObservabilityError("required metric fields missing or unexpected")
        for key in COUNTERS + GAUGES:
            try:
                _number(value[key], integer=key in COUNTERS or key.endswith("_bytes"))
            except SoakObservabilityError:
                raise SoakObservabilityError(f"invalid numeric evidence: {key}") from None
        if self.last_sample is not None:
            for key in COUNTERS + ("process_cpu_seconds",):
                if value[key] < self.last_sample[key]:
                    raise SoakObservabilityError("cumulative metric regressed")
        for key in ("coinbase_connection_generation", "kalshi_connection_generation"):
            if value[key] is not None:
                _number(value[key], integer=True)
                if self.last_sample is not None and self.last_sample[key] is not None:
                    if value[key] < self.last_sample[key]:
                        raise SoakObservabilityError("source generation regressed")
            elif (readiness.ready_read_only and not finalization
                  and key.removesuffix("_connection_generation")
                  in self.required_generation_sources):
                raise SoakObservabilityError("ready without required current generation")
        boot = _token(value["linux_boot_id"])
        _token(value["time_namespace_id"])
        if boot != self.expected_boot_id:
            raise SoakObservabilityError("unexpected host boot change")
        if value["clock_status"] not in {"PASS", "BLOCKED", "FATAL"}:
            raise SoakObservabilityError("invalid clock status")
        for key in ("chrony_signed_offset_ms", "chrony_absolute_offset_ms", "clock_evidence_age_ns"):
            if value[key] is not None:
                try:
                    _number(value[key], signed=key == "chrony_signed_offset_ms")
                except SoakObservabilityError:
                    raise SoakObservabilityError(f"invalid numeric evidence: {key}") from None
        if value["chrony_leap_status"] is not None:
            if value["chrony_leap_status"] not in {"Normal", "Insert second", "Delete second", "Not synchronised"}:
                raise SoakObservabilityError("invalid leap status")
        if readiness.ready_read_only and not finalization:
            if (value["clock_status"] != "PASS" or value["clock_evidence_age_ns"] is None
                    or value["clock_evidence_age_ns"] > 5 * NS
                    or value["chrony_absolute_offset_ms"] is None
                    or value["chrony_absolute_offset_ms"] > 250
                    or value["chrony_signed_offset_ms"] is None
                    or value["chrony_leap_status"] != "Normal"):
                raise SoakObservabilityError("ready with invalid clock evidence")
        if value["chrony_signed_offset_ms"] is not None and value["chrony_absolute_offset_ms"] != abs(value["chrony_signed_offset_ms"]):
            raise SoakObservabilityError("inconsistent clock offsets")
        if (not finalization and self.last_sample_ns is not None
                and now_ns - self.last_sample_ns > METRIC_SAMPLE_INTERVAL_NS):
            raise SoakObservabilityError("required metric sampling interval missed")
        record = self._envelope(now_ns)
        record["phase"] = "finalization" if finalization else "measurement_attempt"
        record["metrics"] = value
        self._write("metrics", record)
        self.db.commit()
        self.last_sample = value
        self.last_sample_ns = now_ns
        self.sample_count += 1

    def observe(self, readiness, snapshot):
        with self.lock:
            self._check()
            try:
                now_ns = snapshot.evaluated_monotonic_ns
                if self.last_observation_ns is not None and now_ns < self.last_observation_ns:
                    raise SoakObservabilityError("readiness monotonic regression")
                if self.last_observation_ns is not None and now_ns - self.last_observation_ns > 5 * NS:
                    raise SoakObservabilityError("required readiness evaluation interval missed")
                if snapshot.started_monotonic_ns != self.start_ns:
                    raise SoakObservabilityError("run identity mismatch")
                if readiness.ready_read_only != (readiness.state == "READY_READ_ONLY"):
                    raise SoakObservabilityError("inconsistent readiness state")
                if readiness.ready_read_only and (readiness.status.value != "PASS"
                        or readiness.current_boot_id != self.expected_boot_id
                        or readiness.clock_reason != "PASS"):
                    raise SoakObservabilityError("inconsistent ready evidence")
                if self.last_state is not None and self.last_state != readiness.state:
                    self.transitions += 1
                record = self._envelope(now_ns)
                fields = asdict(readiness)
                fields["status"] = readiness.status.value
                for key, value in fields.items():
                    if isinstance(value, str):
                        _token(value)
                record.update(readiness=fields, timing=asdict(snapshot))
                self._write("readiness", record)
                # Reserve five seconds before the hard sample deadline.  The
                # runner's one-second cadence otherwise leaves only one second
                # for ordinary process or durable-I/O scheduling jitter.
                if (self.last_sample_ns is None or snapshot.terminal
                        or now_ns + METRIC_SAMPLE_SCHEDULING_MARGIN_NS
                        >= self.last_sample_ns + METRIC_SAMPLE_INTERVAL_NS):
                    self._sample(now_ns, readiness)
                self.last_observation_ns = now_ns
                self.last_state = readiness.state
                self.last_snapshot = snapshot
                self.last_readiness = readiness
                self.readiness_count += 1
            except SoakObservabilityError as exc:
                self.failed = True
                # Every explicit SoakObservabilityError uses a fixed local
                # reason string. Preserve that reason for terminal diagnosis
                # without surfacing source payloads, headers, or exceptions.
                raise SoakObservabilityError(
                    "required observability evidence failed: "
                    + str(exc)) from None
            except Exception as exc:
                self.failed = True
                raise SoakObservabilityError(
                    "required observability evidence failed: "
                    + type(exc).__name__) from None

    def _distribution(self, name, actual_count):
        count = self.db.execute("SELECT count(*) FROM latency WHERE name=?", (name,)).fetchone()[0]
        def value_at(index):
            return self.db.execute("SELECT value FROM latency WHERE name=? ORDER BY value LIMIT 1 OFFSET ?", (name, index)).fetchone()[0]
        if not count:
            return dict(count=0, median=None, p95=None, p99=None, max=None)
        middle = value_at(count // 2)
        median = middle if count % 2 else (value_at(count // 2 - 1) + middle) / 2
        result = dict(count=actual_count, median=median, p95=value_at(math.ceil(.95 * count)-1),
                      p99=value_at(math.ceil(.99 * count)-1), max=value_at(count-1))
        if actual_count != count:
            result["sample_count"] = count
        return result

    def _seal_latency_samples(self):
        if self.db.execute("SELECT count(*) FROM latency").fetchone()[0] != 0:
            raise SoakObservabilityError("latency index was modified outside the sink")
        expected_hash = sha256()
        for name in LATENCIES:
            records = []
            for _, observation_index, started_ns, ended_ns, duration in sorted(
                    self._latency_samples[name], key=lambda entry: entry[1]):
                record = self._envelope(ended_ns)
                record.update(metric=name, started_monotonic_ns=started_ns,
                              duration_ns=duration, observation_index=observation_index,
                              sample_kind="deterministic_reservoir")
                records.append(record)
                self.db.execute("INSERT INTO latency VALUES (?, ?)", (name, duration))
                expected_hash.update(f"{name}:{duration}\n".encode("ascii"))
            self._write_many("latency", records)
        self.db.commit()
        index_hash = sha256()
        for name, duration in self.db.execute("SELECT name, value FROM latency ORDER BY rowid"):
            index_hash.update(f"{name}:{duration}\n".encode("ascii"))
        if index_hash.digest() != expected_hash.digest():
            raise SoakObservabilityError("latency index integrity mismatch")

    def finish(self, result, safety_status):
        with self.lock:
            self._check()
            try:
                if not result.coinbase_thread_stopped or not result.kalshi_thread_stopped:
                    raise SoakObservabilityError("source writers still alive")
                if self.last_snapshot is None or not self.last_snapshot.terminal or not self.sample_count:
                    raise SoakObservabilityError("terminal observations missing")
                if (result.run.state != self.last_snapshot.state
                        or result.run.measurement_complete != self.last_snapshot.measurement_complete):
                    raise SoakObservabilityError("terminal observation mismatch")
                if safety_status not in {"PASS", "FAIL"}:
                    raise SoakObservabilityError("invalid safety classification")
                # Re-sample after the caller has closed the final raw segments;
                # the last compression bytes must appear in final storage totals.
                finalization_ns = self.monotonic_ns()
                if finalization_ns < self.last_snapshot.evaluated_monotonic_ns:
                    raise SoakObservabilityError("finalization monotonic regression")
                self._sample(finalization_ns, self.last_readiness, finalization=True)
                self._seal_latency_samples()
                distributions = {
                    name: self._distribution(name, self._latency_counts[name]) for name in LATENCIES
                }
                self.db.close()
                self.db = None
                for name, stream in self._streams.items():
                    stream.flush()
                    os.fsync(stream.fileno())
                    stream.close()
                    if file_sha256(self.root / (name + ".jsonl")) != self._hashes[name].hexdigest():
                        raise SoakObservabilityError("telemetry integrity mismatch")
                run = self.last_snapshot
                elapsed = (run.evaluated_monotonic_ns - self.start_ns) / NS
                # These are whole-attempt rates, explicitly including startup.
                # They must not silently become active-window shakedown U/C.
                rates = {key: self.last_sample[key] * 3600 / elapsed if elapsed > 0 else None
                         for key in ("raw_bytes_written", "compressed_bytes_written")}
                report = dict(schema_version="candidate_e_soak_observability_summary.v1",
                    run_id=self.run_id, evidence_mode=self.evidence_mode,
                    safety_invariant_status=safety_status, measurement_complete=run.measurement_complete,
                    empirical_operational_adequacy="NOT_ASSESSED",
                    aws_qualification="NOT_ESTABLISHED", orders=0, production_writes=0,
                    signals=0, execution_mode="disabled",
                    readiness_input_contract=self.readiness_input_contract, timing=asdict(run),
                    readiness_transition_count=self.transitions, readiness_record_count=self.readiness_count,
                    metric_sample_count=self.sample_count,
                    finalization_monotonic_ns=finalization_ns,
                    availability=(run.ready_duration_seconds / run.active_elapsed_seconds
                                  if run.active_elapsed_seconds else None),
                    latency_unit="nanoseconds",
                    quantile_method=("nearest_rank; median averages middle pair; exact through "
                                     f"{self.latency_sample_cap} samples per metric, then deterministic reservoir"),
                    latency=distributions, final_metrics=self.last_sample,
                    whole_attempt_bytes_per_hour=rates,
                    canonical_disk_gate="UNRESOLVED_REQUIRES_ACCEPTED_SHAKEDOWN")
                write_json_atomic(self.root / "summary.json", report)
                self.closed = True
                return [("soak_" + name, self.root / filename) for name, filename in (
                    ("readiness", "readiness.jsonl"), ("metrics", "metrics.jsonl"),
                    ("latency", "latency.jsonl"), ("latency_index", "latency.sqlite"),
                    ("source_events", "source_events.jsonl"),
                    ("summary", "summary.json"))]
            except Exception:
                self.failed = True
                self.abort()
                raise SoakObservabilityError("cannot seal complete observability evidence") from None

    def abort(self):
        """Release handles without fabricating terminal evidence or deleting bytes."""
        with self.lock:
            self.failed = True
            for stream in self._streams.values():
                try:
                    stream.close()
                except Exception:
                    pass
            if self.db is not None:
                try:
                    self.db.close()
                except Exception:
                    pass
                self.db = None


def run_observed_soak(*, observability, close_runtime_artifacts, **kwargs):
    """Required-observability entry point for offline integration and later CLI.

    The older lifecycle remains a component-test API. Production packaging must
    use this boundary, supply real adapters, and check production provenance.
    """
    from .kxbtcd_candidate_e_soak_manifest_lifecycle import run_soak_with_manifest_lifecycle
    if not isinstance(observability, SoakObservability) or not callable(close_runtime_artifacts):
        raise SoakObservabilityError("observability and raw artifact closure are required")
    interval = kwargs.get("readiness_evaluation_interval_seconds", 1.0)
    if int(interval * NS) != observability.interval_ns:
        raise SoakObservabilityError("observer and runner cadence mismatch")
    return run_soak_with_manifest_lifecycle(observability=observability,
        close_runtime_artifacts=close_runtime_artifacts, **kwargs)


def close_verified_runtime_archives(core):
    """Close every source manager and enumerate verified raw evidence.

    Called only after both source supervisors stop. Inventory is assembled
    after closure, including each final partial hour; no early generator/glob
    snapshot can silently omit that final segment.
    """
    from .kxbtcd_candidate_e_soak_runtime_core import ARCHIVE_SOURCES
    from .kxbtcd_candidate_e_soak_archive import validate_closed_segment
    core.close()
    artifacts = []
    for source in ARCHIVE_SOURCES:
        manager = core.manager(source)
        if manager.active_raw_path is not None:
            raise SoakObservabilityError("raw writer still active")
        for index, path in enumerate(manager.closed_descriptor_paths):
            descriptor = validate_closed_segment(path)
            if descriptor["source"] != source:
                raise SoakObservabilityError("raw archive source mismatch")
            compressed = path.parent / descriptor["compressed_filename"]
            artifacts.extend(((f"raw_descriptor_{source}_{index}", path),
                              (f"raw_compressed_{source}_{index}", compressed)))
    return artifacts

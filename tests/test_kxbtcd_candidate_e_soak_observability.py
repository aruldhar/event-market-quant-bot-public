import json
import socket
import threading
from dataclasses import replace

import pytest

from src.kxbtcd_candidate_e_soak_observability import (
    COUNTERS, GAUGES, LATENCIES, SoakObservability, SoakObservabilityError,
    run_observed_soak,
    close_verified_runtime_archives,
)
from src.kxbtcd_candidate_e_soak_manifest import DESIGN_FINGERPRINT
from src.kxbtcd_candidate_e_soak_readiness import SoakReadinessResult
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus

BOOT = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("network prohibited in observability tests")
    monkeypatch.setattr(socket, "socket", reject)
    monkeypatch.setattr(socket, "create_connection", reject)


def ready():
    return SoakReadinessResult("READY_READ_ONLY", GateStatus.PASS, "PASS", True,
        BOOT, BOOT, "time:[123]", "PASS", "PASS", "PASS", "PASS")


def blocked():
    return replace(ready(), state="BLOCKED_CLOCK", status=GateStatus.BLOCKED,
                   ready_read_only=False, reason="CLOCK_EVIDENCE_STALE")


def metrics(now):
    return dict.fromkeys(COUNTERS, 0) | dict.fromkeys(GAUGES, 1) | dict(
        coinbase_connection_generation=1, kalshi_connection_generation=1,
        chrony_signed_offset_ms=-0.1, chrony_absolute_offset_ms=0.1,
        chrony_leap_status="Normal", clock_status="PASS", clock_evidence_age_ns=1,
        linux_boot_id=BOOT, time_namespace_id="time:[123]")


class Clock:
    ns = 0
    def now(self):
        return self.ns
    def sleep(self, seconds):
        self.ns += int(seconds * 1e9)


def setup_run(tmp_path, sampler=metrics, **observer_options):
    clock = Clock()
    observer = SoakObservability(root=tmp_path / "telemetry", sample_metrics=sampler,
        utc_now_text=lambda: "2026-09-06T00:00:00Z", evidence_mode="offline_fixture",
        expected_boot_id=BOOT, declared_latency_producers=LATENCIES,
        readiness_interval_seconds=5, monotonic_ns=clock.now, **observer_options)
    kwargs = dict(manifest_path=tmp_path / "run.json", run_id="offline_observability_test",
        run_role="AWS_SHAKEDOWN", design_fingerprint=DESIGN_FINGERPRINT,
        git_head="b"*40, docker_image_digest="sha256:"+"a"*64, host_boot_id=BOOT,
        requested_active_duration_seconds=3600, initial_filesystem_free_bytes=50_000_000_000,
        expected_boot_id=BOOT, run_coinbase_supervisor=lambda stop: stop.wait(),
        run_kalshi_supervisor=lambda stop: stop.wait(), sample_readiness=lambda _: ready(),
        readiness_evaluation_interval_seconds=5, monotonic_ns=clock.now,
        sleep_seconds=clock.sleep, utc_now_text=lambda: "2026-09-06T00:00:00Z",
        artifact_root=tmp_path)
    return observer, clock, kwargs


def run(observer, kwargs, close=lambda: []):
    return run_observed_soak(observability=observer, close_runtime_artifacts=close, **kwargs)


def test_complete_with_blocked_intervals_and_exact_latency(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    def sample(now):
        if now == 0:
            for name in LATENCIES:
                for duration in (1, 2, 3, 100):
                    observer.record_latency(name, started_ns=0, ended_ns=duration)
            observer.record_source_event(source="kalshi", event="sequence_gap", generation=1,
                monotonic_ns=0, event_ticker="KXBTCD-TEST")
        return blocked() if 600e9 <= now < 900e9 else ready()
    kwargs["sample_readiness"] = sample
    result = run(observer, kwargs)
    report = json.loads((observer.root / "summary.json").read_text())
    assert result.terminal_manifest["measurement_complete"] is True
    assert report["timing"]["blocked_duration_seconds"] == 300
    assert report["availability"] == pytest.approx(3300/3600)
    assert report["readiness_transition_count"] == 2
    assert report["latency"][LATENCIES[0]] == dict(count=4, median=2.5, p95=100, p99=100, max=100)
    assert report["evidence_mode"] == "offline_fixture"
    assert report["empirical_operational_adequacy"] == "NOT_ASSESSED"
    assert report["aws_qualification"] == "NOT_ESTABLISHED"
    assert len(result.terminal_manifest["artifact_descriptors"]) == 6
    assert observer.closed


def test_transport_error_persists_only_safe_exception_class(tmp_path):
    observer, clock, _ = setup_run(tmp_path)
    observer.start(run_id="transport_error", started_monotonic_ns=0)
    observer.record_source_event(source="kalshi", event="transport_error", generation=1,
        monotonic_ns=1, event_ticker="KXBTCD-TEST", failure_class="ConnectionClosedError")
    observer.abort()
    record = json.loads((observer.root / "source_events.jsonl").read_text())
    assert record["failure_class"] == "ConnectionClosedError"


def test_reconnect_attempt_persists_safe_decision_reason(tmp_path):
    observer, _, _ = setup_run(tmp_path)
    observer.start(run_id="reconnect_reason", started_monotonic_ns=0)
    observer.record_source_event(
        source="kalshi", event="reconnect_attempt", generation=1,
        monotonic_ns=1, event_ticker="KXBTCD-TEST",
        reconnect_reason="KALSHI_PONG_STALE",
    )
    observer.abort()
    record = json.loads((observer.root / "source_events.jsonl").read_text())
    assert record["reconnect_reason"] == "KALSHI_PONG_STALE"


def test_v2_ready_evidence_does_not_require_coinbase_websocket_generation(tmp_path):
    def v2_metrics(now):
        return metrics(now) | {"coinbase_connection_generation": None}
    observer = SoakObservability(root=tmp_path / "telemetry", sample_metrics=v2_metrics,
        utc_now_text=lambda: "2026-09-06T00:00:00Z", evidence_mode="offline_fixture",
        expected_boot_id=BOOT, declared_latency_producers=LATENCIES,
        required_generation_sources=("kalshi",), monotonic_ns=lambda: 0)
    observer.start(run_id="v2_rest_without_ws", started_monotonic_ns=0)
    observer._sample(0, ready())
    observer.abort()


def test_v2_summary_seals_its_independent_rest_input_contract(tmp_path):
    def v2_metrics(now):
        return metrics(now) | {"coinbase_connection_generation": None}
    observer, _, kwargs = setup_run(tmp_path, sampler=v2_metrics,
        required_generation_sources=("kalshi",),
        readiness_input_contract="v2_exact_rest_candle_and_kalshi")
    run(observer, kwargs)
    report = json.loads((observer.root / "summary.json").read_text())
    assert report["readiness_input_contract"] == "v2_exact_rest_candle_and_kalshi"


def test_v2_ready_evidence_still_requires_current_kalshi_generation(tmp_path):
    def missing_kalshi(now):
        return metrics(now) | {"coinbase_connection_generation": None,
                               "kalshi_connection_generation": None}
    observer = SoakObservability(root=tmp_path / "telemetry", sample_metrics=missing_kalshi,
        utc_now_text=lambda: "2026-09-06T00:00:00Z", evidence_mode="offline_fixture",
        expected_boot_id=BOOT, declared_latency_producers=LATENCIES,
        required_generation_sources=("kalshi",), monotonic_ns=lambda: 0)
    observer.start(run_id="v2_requires_kalshi", started_monotonic_ns=0)
    with pytest.raises(SoakObservabilityError, match="required current generation"):
        observer._sample(0, ready())
    observer.abort()


@pytest.mark.parametrize("field", list(COUNTERS) + list(GAUGES) + ["clock_status", "linux_boot_id"])
def test_missing_metric_cannot_terminalize(tmp_path, field):
    def missing(now):
        value = metrics(now)
        del value[field]
        return value
    observer, clock, kwargs = setup_run(tmp_path, missing)
    with pytest.raises(SoakObservabilityError):
        run(observer, kwargs)
    assert json.loads((tmp_path / "run.json").read_text())["lifecycle_state"] == "RUNNING"
    assert not (observer.root / "summary.json").exists()
    assert not any(t.name.startswith("candidate-e-soak-") for t in threading.enumerate())


@pytest.mark.parametrize("field,value", [
    ("process_cpu_seconds", float("nan")), ("coinbase_message_count", True),
    ("filesystem_free_bytes", -1), ("clock_evidence_age_ns", 5_000_000_001),
    ("chrony_absolute_offset_ms", 251), ("clock_status", "BLOCKED"),
    ("linux_boot_id", "different-boot"), ("coinbase_connection_generation", None),
    ("unexpected_field", "secret"),
])
def test_invalid_metric_cannot_terminalize(tmp_path, field, value):
    observer, clock, kwargs = setup_run(tmp_path, lambda now: metrics(now) | {field: value})
    with pytest.raises(SoakObservabilityError):
        run(observer, kwargs)
    assert not (observer.root / "summary.json").exists()


def test_invalid_metric_reports_safe_metric_name(tmp_path):
    observer, _, kwargs = setup_run(
        tmp_path, lambda now: metrics(now) | {"host_load_1m": float("nan")},
    )
    with pytest.raises(SoakObservabilityError, match="invalid numeric evidence: host_load_1m"):
        run(observer, kwargs)


def test_initial_timeout_is_safe_but_incomplete(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    kwargs["sample_readiness"] = lambda _: blocked()
    result = run(observer, kwargs)
    assert result.terminal_manifest["safety_invariant_status"] == "PASS"
    assert result.terminal_manifest["measurement_complete"] is False
    report = json.loads((observer.root / "summary.json").read_text())
    assert report["availability"] is None
    assert report["latency"][LATENCIES[0]]["median"] is None


def test_final_compression_sample_occurs_after_sources_stop(tmp_path):
    total = {"compressed_bytes_written": 0}
    observer, clock, kwargs = setup_run(tmp_path, lambda now: metrics(now) | total)
    def close():
        assert not any(t.name.startswith("candidate-e-soak-") for t in threading.enumerate())
        total["compressed_bytes_written"] = 42
        return []
    run(observer, kwargs, close)
    report = json.loads((observer.root / "summary.json").read_text())
    assert report["final_metrics"]["compressed_bytes_written"] == 42


@pytest.mark.parametrize("failure", ["close", "tamper", "index", "missing"])
def test_finalization_failure_preserves_running(tmp_path, failure):
    observer, clock, kwargs = setup_run(tmp_path)
    def close():
        if failure == "close":
            raise OSError("raw closure failed")
        if failure == "tamper":
            with (observer.root / "metrics.jsonl").open("ab") as stream:
                stream.write(b'{}\n')
        if failure == "index":
            observer.db.execute("INSERT INTO latency VALUES ('rest_request_duration', 77)")
        if failure == "missing":
            return [("raw", tmp_path / "does-not-exist")]
        return []
    with pytest.raises(Exception):
        run(observer, kwargs, close)
    assert json.loads((tmp_path / "run.json").read_text())["lifecycle_state"] == "RUNNING"


def test_writer_failure_stops_both_sources(tmp_path, monkeypatch):
    observer, clock, kwargs = setup_run(tmp_path)
    original = observer._write
    def fail(name, value):
        if name == "metrics":
            raise OSError("disk full")
        return original(name, value)
    monkeypatch.setattr(observer, "_write", fail)
    with pytest.raises(SoakObservabilityError):
        run(observer, kwargs)
    assert observer.failed
    assert not any(t.name.startswith("candidate-e-soak-") for t in threading.enumerate())


def test_sampling_gap_and_counter_reset_rejected(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path, lambda now: metrics(now) | {"coinbase_message_count": 10 if now == 0 else 0})
    with pytest.raises(SoakObservabilityError):
        run(observer, kwargs)
    observer, clock, kwargs = setup_run(tmp_path / "gap")
    kwargs["sleep_seconds"] = lambda _: setattr(clock, "ns", clock.ns + 61_000_000_000)
    with pytest.raises(SoakObservabilityError, match="required readiness evaluation interval missed"):
        run(observer, kwargs)


def test_one_second_runner_schedules_metric_sample_five_seconds_early(tmp_path):
    clock = Clock()
    observer = SoakObservability(
        root=tmp_path / "telemetry", sample_metrics=metrics,
        utc_now_text=lambda: "2026-09-06T00:00:00Z",
        evidence_mode="offline_fixture", expected_boot_id=BOOT,
        declared_latency_producers=LATENCIES,
        readiness_interval_seconds=1, monotonic_ns=clock.now,
    )
    observer.start(run_id="sampling_margin", started_monotonic_ns=0)
    from src.kxbtcd_candidate_e_soak_run_control import SoakRunController
    controller = SoakRunController(
        started_monotonic_ns=0,
        requested_active_duration_seconds=3600,
    )
    for second in range(56):
        now_ns = second * 1_000_000_000
        observer.observe(ready(), controller.observe(
            evaluated_monotonic_ns=now_ns,
            readiness=ready(),
        ))
    assert observer.sample_count == 2
    assert observer.last_sample_ns == 55_000_000_000
    observer.abort()


def test_latched_producer_failure_and_no_post_close_writes(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    observer.start(run_id="unit", started_monotonic_ns=0)
    with pytest.raises(SoakObservabilityError):
        observer.record_latency(LATENCIES[0], started_ns=2, ended_ns=1)
    with pytest.raises(SoakObservabilityError):
        observer.record_latency(LATENCIES[0], started_ns=0, ended_ns=1)
    observer.abort()


def test_missing_producers_rejected_before_source_start(tmp_path):
    with pytest.raises(SoakObservabilityError):
        SoakObservability(root=tmp_path, sample_metrics=metrics, utc_now_text=lambda: "",
            evidence_mode="production", expected_boot_id=BOOT, declared_latency_producers=[])


def test_source_fatal_is_not_promoted_to_pass(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    kwargs["sample_readiness"] = lambda _: replace(ready(), state="FATAL", status=GateStatus.FATAL, ready_read_only=False)
    result = run(observer, kwargs)
    assert result.terminal_manifest["safety_invariant_status"] == "FAIL"
    assert result.terminal_manifest["measurement_complete"] is False


def test_shutdown_exception_is_hard_failure_and_time_excluded(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    def fail_on_stop(stop):
        stop.wait()
        clock.ns += 10_000_000_000
        raise OSError("shutdown persistence failed")
    kwargs["run_coinbase_supervisor"] = fail_on_stop
    result = run(observer, kwargs)
    assert result.terminal_manifest["safety_invariant_status"] == "FAIL"
    assert result.runner.run.evaluated_monotonic_ns == 3600_000_000_000
    assert result.runner.source_failure == "COINBASE_SUPERVISOR_EXCEPTION:OSError"


def test_real_raw_segments_closed_verified_and_in_manifest(tmp_path):
    from src.kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore, ARCHIVE_SOURCES
    from src.kxbtcd_candidate_e_soak_manifest import validate_soak_run_manifest
    core = SoakSourceRuntimeCore(runtime_session_id="offline_archive_test", archive_root=tmp_path / "raw")
    observer, clock, kwargs = setup_run(tmp_path)
    def sample(now):
        if now == 0:
            for source in ARCHIVE_SOURCES:
                core.manager(source).append(transport="fixture", raw_text='{"offline":true}',
                    received_monotonic_ns=0, received_utc="2026-09-06T00:00:00Z")
        return ready()
    kwargs["sample_readiness"] = sample
    result = run(observer, kwargs, lambda: close_verified_runtime_archives(core))
    roles = [d["logical_role"] for d in result.terminal_manifest["artifact_descriptors"]]
    assert len(roles) == 14
    assert sum(role.startswith("raw_compressed_") for role in roles) == 4
    validate_soak_run_manifest(tmp_path / "run.json", artifact_root=tmp_path, verify_artifacts=True)


def test_concurrent_producer_and_post_close_rejection(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    done = threading.Event()
    def source(stop):
        for i in range(100):
            observer.record_latency("rest_request_duration", started_ns=0, ended_ns=i)
        done.set()
        stop.wait()
    kwargs["run_coinbase_supervisor"] = source
    kwargs["sample_readiness"] = lambda _: (done.wait(5), ready())[1]
    run(observer, kwargs)
    report = json.loads((observer.root / "summary.json").read_text())
    assert report["latency"]["rest_request_duration"]["count"] == 100
    assert report["latency"]["rest_request_duration"]["p99"] == 98
    with pytest.raises(SoakObservabilityError):
        observer.record_latency("rest_request_duration", started_ns=0, ended_ns=1)


def test_high_volume_latency_uses_a_bounded_deterministic_reservoir(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path, latency_sample_cap=3)
    def source(stop):
        for value in range(10):
            observer.record_latency("rest_request_duration", started_ns=0, ended_ns=value)
        stop.wait()
    kwargs["run_coinbase_supervisor"] = source
    result = run(observer, kwargs)
    report = json.loads((observer.root / "summary.json").read_text())
    assert result.terminal_manifest["measurement_complete"] is True
    assert report["latency"]["rest_request_duration"]["count"] == 10
    assert report["latency"]["rest_request_duration"]["sample_count"] == 3
    assert sum(1 for _ in (observer.root / "latency.jsonl").open("rb")) <= len(LATENCIES) * 3
    assert observer.db is None


def test_secret_marker_not_persisted(tmp_path):
    observer, clock, kwargs = setup_run(tmp_path)
    kwargs["sample_readiness"] = lambda _: replace(ready(), reason="PRIVATE_KEY_MARKER")
    with pytest.raises(SoakObservabilityError):
        run(observer, kwargs)
    assert b"PRIVATE_KEY_MARKER" not in (observer.root / "readiness.jsonl").read_bytes()

"""Offline proof that runtime activity, rather than fixture metrics, drives telemetry."""
from datetime import datetime, timezone
import json

from src.kxbtcd_candidate_e_soak_coinbase_rest_transport import fetch_exact_seed_candle
from src.kxbtcd_candidate_e_soak_coinbase_worker import CoinbaseReadOnlyWorkerSession
from src.kxbtcd_candidate_e_soak_metric_producers import RuntimeMetricProducers
from src.kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus


class Sink:
    def __init__(self): self.latencies = []
    def record_latency(self, name, *, started_ns, ended_ns): self.latencies.append((name, started_ns, ended_ns))
    def record_source_event(self, **kwargs): pass


class Identity:
    status = type("S", (), {"value": "PASS"})()
    boot_id = "boot"
    time_namespace_id = "time:[1]"


def test_fake_ws_and_rest_transport_activity_updates_core_producers(tmp_path):
    producer = RuntimeMetricProducers(archive_root=tmp_path / "raw", clock_evidence_path=tmp_path / "clock")
    sink = Sink()
    core = SoakSourceRuntimeCore(runtime_session_id="offline_metrics", archive_root=tmp_path / "raw",
        metric_producers=producer, observability=sink)
    core.open_coinbase_generation(opened_monotonic_ns=1)
    core.ingest_coinbase_ws_frame(raw_text=json.dumps({"type":"heartbeat", "product_id":"BTC-USD", "last_trade_id":1, "sequence":1, "time":"2026-09-06T00:00:00Z"}),
        received_monotonic_ns=2, received_utc="2026-09-06T00:00:00Z")
    assert producer.counters["coinbase_message_count"] == 1
    assert producer.counters["coinbase_heartbeat_count"] == 1
    assert producer.generations["coinbase"] == 1
    assert {entry[0] for entry in sink.latencies} >= {"receive_to_raw_persist_duration", "raw_persist_to_parse_apply_duration"}
    core.close()


def test_production_sampler_uses_injected_linux_bridge_and_real_archive_bytes(tmp_path):
    raw = tmp_path / "raw" / "source"
    raw.mkdir(parents=True)
    (raw / "x.jsonl").write_bytes(b"raw")
    (raw / "x.jsonl.zst").write_bytes(b"compressed")
    identity = type("Identity", (), {"status": GateStatus.PASS, "boot_id": "boot", "time_namespace_id": "time:[1]"})()
    chrony = type("Chrony", (), {"signed_system_time_offset_ms": -1.0, "absolute_system_time_offset_ms": 1.0, "leap_status": "Normal"})()
    clock = type("Clock", (), {"status": GateStatus.PASS, "evidence_age_ns": 1, "chrony": chrony})()
    sampler = RuntimeMetricProducers(archive_root=tmp_path / "raw", clock_evidence_path=tmp_path / "clock",
        identity_resolver=lambda: identity, clock_file_evaluator=lambda *args, **kwargs: clock,
        getrusage=lambda _: type("Usage", (), {"ru_utime": 1.0, "ru_stime": 2.0, "ru_maxrss": 3})(),
        getloadavg=lambda: (1.0, 2.0, 3.0), disk_usage=lambda _: type("Disk", (), {"free": 9})(),
        sysconf=lambda key: {"SC_AVPHYS_PAGES": 4, "SC_PAGE_SIZE": 5}[key])
    sampler.generation_opened("coinbase", 1)
    sampler.generation_opened("kalshi", 1)
    sample = sampler.sample(7)
    assert sample["raw_bytes_written"] == 3
    assert sample["compressed_bytes_written"] == 10
    assert sample["clock_status"] == "PASS"


def test_production_sampler_retries_one_clock_file_replacement_race(tmp_path):
    identity = type("Identity", (), {"status": GateStatus.PASS, "boot_id": "boot", "time_namespace_id": "time:[1]"})()
    chrony = type("Chrony", (), {"signed_system_time_offset_ms": -1.0, "absolute_system_time_offset_ms": 1.0, "leap_status": "Normal"})()
    passed = type("Clock", (), {"status": GateStatus.PASS, "reason": "PASS", "evidence_age_ns": 1, "chrony": chrony})()
    negative_age = type("Clock", (), {"reason": "CLOCK_EVIDENCE_NEGATIVE_AGE"})()
    calls = []

    def clock_evaluator(*_args, **kwargs):
        calls.append(kwargs["now_monotonic_ns"])
        return negative_age if len(calls) == 1 else passed

    monotonic_values = iter((10, 20))
    sampler = RuntimeMetricProducers(
        archive_root=tmp_path / "raw", clock_evidence_path=tmp_path / "clock",
        identity_resolver=lambda: identity, clock_file_evaluator=clock_evaluator,
        monotonic_ns=lambda: next(monotonic_values),
        getrusage=lambda _: type("Usage", (), {"ru_utime": 1.0, "ru_stime": 2.0, "ru_maxrss": 3})(),
        getloadavg=lambda: (1.0, 2.0, 3.0), disk_usage=lambda _: type("Disk", (), {"free": 9})(),
        sysconf=lambda key: {"SC_AVPHYS_PAGES": 4, "SC_PAGE_SIZE": 5}[key],
    )
    sampler.generation_opened("coinbase", 1)
    sampler.generation_opened("kalshi", 1)
    assert sampler.sample(7)["clock_status"] == "PASS"
    assert calls == [10, 20]

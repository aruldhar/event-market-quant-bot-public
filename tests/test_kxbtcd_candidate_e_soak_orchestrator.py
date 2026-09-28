import pytest

from src.kxbtcd_candidate_e_soak_orchestrator import SoakOrchestratorError, run_packaged_observed_soak
from src.kxbtcd_candidate_e_soak_observability import COUNTERS, GAUGES, LATENCIES, SoakObservability, close_verified_runtime_archives
from src.kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore
from src.kxbtcd_candidate_e_soak_metric_producers import RuntimeMetricProducers
from src.kxbtcd_candidate_e_soak_readiness import SoakReadinessResult
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from src.kxbtcd_candidate_e_soak_manifest import DESIGN_FINGERPRINT


def test_orchestrator_rejects_missing_required_observed_components():
    with pytest.raises(SoakOrchestratorError, match="required"):
        run_packaged_observed_soak(core=None, producers=None, observability=None,
            close_runtime_artifacts=lambda: [], run_coinbase_supervisor=lambda _: None,
            run_kalshi_supervisor=lambda _: None)


def test_orchestrator_requires_core_to_use_same_producer_and_observer():
    core = type("Core", (), {"metric_producers": object(), "observability": object()})()
    with pytest.raises(SoakOrchestratorError, match="not bound"):
        run_packaged_observed_soak(core=core, producers=object(), observability=object(),
            close_runtime_artifacts=lambda: [], run_coinbase_supervisor=lambda _: None,
            run_kalshi_supervisor=lambda _: None)


def test_orchestrator_seals_closed_raw_archive_in_terminal_manifest(tmp_path):
    boot = "11111111-2222-3333-4444-555555555555"
    clock = {"ns": 0}
    class Producers:
        def __init__(self): self.values = dict.fromkeys(COUNTERS, 0) | dict.fromkeys(GAUGES, 1)
        def sample(self, now):
            return self.values | {"coinbase_connection_generation": 1, "kalshi_connection_generation": 1,
                "chrony_signed_offset_ms": 0.0, "chrony_absolute_offset_ms": 0.0, "chrony_leap_status": "Normal",
                "clock_status": "PASS", "clock_evidence_age_ns": 0, "linux_boot_id": boot, "time_namespace_id": "time:[1]"}
    producers = Producers()
    observer = SoakObservability(root=tmp_path / "telemetry", sample_metrics=producers.sample,
        utc_now_text=lambda: "2026-09-06T00:00:00Z", evidence_mode="offline_fixture", expected_boot_id=boot,
        declared_latency_producers=LATENCIES, readiness_interval_seconds=5, monotonic_ns=lambda: clock["ns"])
    core = SoakSourceRuntimeCore(runtime_session_id="orchestrator-test", archive_root=tmp_path / "raw",
        metric_producers=producers, observability=observer)
    # This is genuine core archive activity, not an artifact fixture.
    core.manager("coinbase_exchange_ws").append(transport="fixture", raw_text="{}", received_monotonic_ns=0,
        received_utc="2026-09-06T00:00:00Z")
    ready = SoakReadinessResult("READY_READ_ONLY", GateStatus.PASS, "PASS", True, boot, boot, "time:[1]", "PASS", "PASS", "PASS", "PASS")
    def sleep(seconds): clock["ns"] += int(seconds * 1_000_000_000)
    result = run_packaged_observed_soak(core=core, producers=producers, observability=observer,
        close_runtime_artifacts=lambda: close_verified_runtime_archives(core), manifest_path=tmp_path / "run.json",
        run_id="orchestrator_test", run_role="AWS_SHAKEDOWN", design_fingerprint=DESIGN_FINGERPRINT,
        git_head="a" * 40, docker_image_digest="sha256:" + "b" * 64, host_boot_id=boot,
        requested_active_duration_seconds=3600, initial_filesystem_free_bytes=1_000_000,
        expected_boot_id=boot, run_coinbase_supervisor=lambda stop: stop.wait(), run_kalshi_supervisor=lambda stop: stop.wait(),
        sample_readiness=lambda _: ready, readiness_evaluation_interval_seconds=5, monotonic_ns=lambda: clock["ns"],
        sleep_seconds=sleep, utc_now_text=lambda: "2026-09-06T00:00:00Z", artifact_root=tmp_path)
    assert result.terminal_manifest["lifecycle_state"] == "TERMINAL"
    assert any(item["logical_role"].startswith("raw_compressed_coinbase_exchange_ws")
        for item in result.terminal_manifest["artifact_descriptors"])

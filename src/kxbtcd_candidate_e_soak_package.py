"""Fail-closed packaging preflight for the read-only soak runtime.

This module constructs the mandatory observed components but deliberately does
not start transports.  Production orchestration must pass these objects to the
already-tested supervisor/lifecycle path; a bare CLI can never start an
unobserved collector.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import time

from .kxbtcd_candidate_e_soak_linux_runtime_identity import resolve_production_runtime_identity
from .kxbtcd_candidate_e_soak_metric_producers import RuntimeMetricProducers
from .kxbtcd_candidate_e_soak_observability import LATENCIES, SoakObservability
from .kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore


class SoakPackageError(RuntimeError):
    pass


def build_observed_components(*, runtime_session_id, archive_root, telemetry_root,
                              clock_evidence_path, utc_now_text):
    """Build the required observed runtime without opening a socket."""
    identity = resolve_production_runtime_identity()
    if identity.status.value != "PASS" or not identity.boot_id:
        raise SoakPackageError("production Linux identity is required")
    archive = Path(archive_root)
    telemetry = Path(telemetry_root)
    clock = Path(clock_evidence_path)
    if not clock.is_file():
        raise SoakPackageError("host clock evidence file is required")
    producer = RuntimeMetricProducers(archive_root=archive, clock_evidence_path=clock)
    # Evaluate the real bridge before a source-capable runtime can be built.
    # This rejects stale, malformed, or host/container identity-mismatched
    # evidence rather than merely proving the bind mount exists.
    preflight_sample = producer.sample(time.monotonic_ns())
    if preflight_sample.get("clock_status") != "PASS":
        raise SoakPackageError("host clock evidence is not PASS")
    observer = SoakObservability(root=telemetry, sample_metrics=producer.sample,
        utc_now_text=utc_now_text, evidence_mode="production", expected_boot_id=identity.boot_id,
        declared_latency_producers=LATENCIES, required_generation_sources=("kalshi",),
        readiness_input_contract="v2_exact_rest_candle_and_kalshi")
    core = SoakSourceRuntimeCore(runtime_session_id=runtime_session_id, archive_root=archive,
        metric_producers=producer, observability=observer)
    return core, producer, observer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate required read-only soak packaging.")
    parser.add_argument("--runtime-session-id", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--telemetry-root", required=True)
    parser.add_argument("--clock-evidence-path", required=True)
    args = parser.parse_args(argv)
    from datetime import datetime, timezone
    core, _, _ = build_observed_components(runtime_session_id=args.runtime_session_id,
        archive_root=args.archive_root, telemetry_root=args.telemetry_root,
        clock_evidence_path=args.clock_evidence_path,
        utc_now_text=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    core.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

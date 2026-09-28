"""Real-adapter readiness sampler for the observed read-only soak."""
from __future__ import annotations

import time

from .kxbtcd_candidate_e_soak_readiness import SoakReadinessCoordinator
from .kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from .kxbtcd_candidate_e_restart_source_readiness import KalshiReadinessEvidence
from .kxbtcd_candidate_e_soak_runtime_core import SoakRuntimeCoreError


def build_live_readiness_sampler(*, core, producers, expected_boot_id,
                                 epoch_seconds=time.time, monotonic_ns=time.monotonic_ns):
    coordinator = SoakReadinessCoordinator(expected_boot_id=expected_boot_id)

    def sample(now_monotonic_ns):
        identity = producers.identity_resolver()
        clock = producers.clock_file_evaluator(
            producers.clock_evidence_path, now_monotonic_ns=int(now_monotonic_ns),
            current_boot_id=identity.boot_id, current_time_namespace_id=identity.time_namespace_id)
        # The Coinbase and Kalshi worker threads each record their own
        # monotonic timestamps (a fetched REST candle's availability, a WS
        # pong) concurrently with this sampling cycle. Identity/clock
        # evaluation above takes real wall-clock time, so the cycle's initial
        # now_monotonic_ns snapshot can go stale relative to a timestamp one
        # of those threads just recorded -- tripping
        # V2_REST_CANDLE_MONOTONIC_INVARIANT_FAILURE or
        # KALSHI_TRANSPORT_MONOTONIC_INVARIANT_FAILURE as a false positive.
        # Re-sample immediately before each source's own evaluation so "now"
        # is never older than what it is compared against.
        coinbase = core.evaluate_v2_coinbase_rest_candle(
            decision_epoch_s=int(epoch_seconds()), now_monotonic_ns=int(monotonic_ns()))
        try:
            kalshi = core.evaluate_kalshi(now_timestamp_ms=int(epoch_seconds() * 1000), now_monotonic_ns=int(monotonic_ns()))
        except SoakRuntimeCoreError as exc:
            if str(exc) not in {"Kalshi readiness lacks generation/event", "Kalshi readiness lacks discovery session"}:
                raise
            kalshi = KalshiReadinessEvidence(GateStatus.BLOCKED, "KALSHI_GENERATION_NOT_OPEN", "", (), 0,
                None, None, None, "GENERATION_NOT_OPEN")
        return coordinator.evaluate(evaluated_monotonic_ns=int(now_monotonic_ns), execution_mode_disabled=True,
            identity=identity, clock=clock, coinbase=coinbase, kalshi=kalshi)
    return sample

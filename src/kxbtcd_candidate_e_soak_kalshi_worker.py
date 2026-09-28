"""Checkpoint 21N-Z-F Kalshi read-only worker session policy.

This module contains NO network calls.

It converts the already-tested Kalshi runtime core into explicit actions for
the later authenticated WebSocket/REST transport layer:

- READY
- BLOCKED
- RECONNECT_REQUIRED
- ROLLOVER_REQUIRED

Safety:
- initial snapshot acquisition is BLOCKED, not treated as a gap;
- a real sequence gap invalidates the complete selected ladder and requires
  a fresh connection generation / authoritative snapshots;
- stale transport Pong requires reconnect;
- an expired selected event requires rediscovery/rollover;
- readiness resets reconnect backoff only after actual PASS;
- no Candidate-E signal, settlement, P&L, order, or write behavior exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_soak_runtime_core import (
    SoakSourceRuntimeCore,
)


class KalshiWorkerSessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class KalshiWorkerAction:
    kind: str
    reason: str
    connection_generation: int
    event_ticker: str
    expected_tickers: tuple[str, ...]
    last_seq: int | None = None
    sequence_gap_count: int = 0


class KalshiReadOnlyWorkerSession:
    """Deterministic policy for one Kalshi transport generation."""

    def __init__(
        self,
        core: SoakSourceRuntimeCore,
    ) -> None:
        if not isinstance(
            core,
            SoakSourceRuntimeCore,
        ):
            raise KalshiWorkerSessionError(
                "worker session requires SoakSourceRuntimeCore"
            )

        self.core = core
        self.binding = None

    def start_generation(
        self,
        *,
        opened_monotonic_ns: int,
    ):
        current = (
            self.core.connections.current_kalshi
        )

        if (
            current is not None
            and current.connected
        ):
            raise KalshiWorkerSessionError(
                "Kalshi generation already open"
            )

        if self.core.current_event is None:
            raise KalshiWorkerSessionError(
                "Kalshi generation requires current event"
            )

        self.binding = (
            self.core.open_kalshi_generation(
                opened_monotonic_ns=(
                    opened_monotonic_ns
                )
            )
        )

        return self.binding

    def _require_binding(self):
        binding = self.binding

        if (
            binding is None
            or not binding.connected
        ):
            raise KalshiWorkerSessionError(
                "Kalshi worker generation is not open"
            )

        current = (
            self.core.connections.current_kalshi
        )

        if (
            current is None
            or current.generation
            != binding.generation
        ):
            raise KalshiWorkerSessionError(
                "Kalshi worker binding is stale"
            )

        return binding

    def _base_action(
        self,
        *,
        kind: str,
        reason: str,
    ) -> KalshiWorkerAction:
        binding = self._require_binding()
        event = self.core.current_event

        if event is None:
            raise KalshiWorkerSessionError(
                "current Kalshi event disappeared"
            )

        return KalshiWorkerAction(
            kind=kind,
            reason=reason,
            connection_generation=(
                binding.generation
            ),
            event_ticker=(
                event.event_ticker
            ),
            expected_tickers=tuple(
                market.market_ticker
                for market in event.markets
            ),
            last_seq=(
                binding.cache.last_seq
            ),
            sequence_gap_count=(
                binding.cache.sequence_gap_count
            ),
        )

    def evaluate(
        self,
        *,
        now_timestamp_ms: int,
        now_monotonic_ns: int,
    ) -> KalshiWorkerAction:
        binding = self._require_binding()
        self.core.fsync_due_raw_segments(now_monotonic_ns=now_monotonic_ns)
        event = self.core.current_event

        if event is None:
            raise KalshiWorkerSessionError(
                "Kalshi readiness lacks current event"
            )

        # Event expiry is a planned source transition, not a generic socket
        # failure. Rediscovery must happen before a new generation can arm.
        if (
            int(event.close_timestamp_ms)
            <= int(now_timestamp_ms)
        ):
            return self._base_action(
                kind="ROLLOVER_REQUIRED",
                reason="SELECTED_EVENT_CLOSED",
            )

        # Initial cache state is also resync_required=True. Distinguish that
        # normal snapshot-acquisition state from an observed sequence gap.
        if (
            binding.cache.sequence_gap_count > 0
            and binding.cache.resync_required
        ):
            return self._base_action(
                kind="RECONNECT_REQUIRED",
                reason="KALSHI_SEQUENCE_GAP",
            )

        evidence = self.core.evaluate_kalshi(
            now_timestamp_ms=(
                now_timestamp_ms
            ),
            now_monotonic_ns=(
                now_monotonic_ns
            ),
        )

        if evidence.status == GateStatus.FATAL:
            raise KalshiWorkerSessionError(
                f"fatal Kalshi readiness: {evidence.reason}"
            )

        if evidence.status == GateStatus.PASS:
            self.core.mark_source_ready(
                "kalshi"
            )

            return self._base_action(
                kind="READY",
                reason="PASS",
            )

        # Once a current connection had a proven Pong, allowing that proof
        # to age past the frozen liveness window means the transport can no
        # longer be trusted. A fresh generation is required.
        if evidence.reason == "KALSHI_PONG_STALE":
            return self._base_action(
                kind="RECONNECT_REQUIRED",
                reason=evidence.reason,
            )

        return self._base_action(
            kind="BLOCKED",
            reason=evidence.reason,
        )

    def ingest_ws_frame(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        now_timestamp_ms: int,
    ) -> KalshiWorkerAction:
        binding = self._require_binding()

        # Runtime core owns the raw-before-parse/apply invariant.
        result = self.core.ingest_kalshi_ws_frame(
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
        )

        # Detect a genuine sequence gap immediately rather than waiting for
        # the next periodic readiness evaluation.
        if (
            bool(result.get("gap"))
            and binding.cache.resync_required
        ):
            return self._base_action(
                kind="RECONNECT_REQUIRED",
                reason="KALSHI_SEQUENCE_GAP",
            )

        return self.evaluate(
            now_timestamp_ms=(
                now_timestamp_ms
            ),
            now_monotonic_ns=(
                received_monotonic_ns
            ),
        )

    def record_pong(
        self,
        *,
        pong_monotonic_ns: int,
        now_timestamp_ms: int,
    ) -> KalshiWorkerAction:
        self._require_binding()

        self.core.record_kalshi_pong(
            pong_monotonic_ns=(
                pong_monotonic_ns
            )
        )

        return self.evaluate(
            now_timestamp_ms=(
                now_timestamp_ms
            ),
            now_monotonic_ns=(
                pong_monotonic_ns
            ),
        )

    def reconnect_for_unproven_pong(
        self,
    ) -> KalshiWorkerAction:
        """Require a fresh generation after a first-Ping timeout.

        A connection with no successful Pong has no liveness proof and cannot
        become ready. The transport has already recorded the failed Ping/Pong
        evidence before calling this method; this action only routes the
        recoverable source failure through the existing reconnect backoff.
        """
        return self._base_action(
            kind="RECONNECT_REQUIRED",
            reason="KALSHI_PONG_UNPROVEN",
        )

    def disconnect(
        self,
        *,
        closed_monotonic_ns: int,
        count_as_failure: bool = True,
        reconnect_reason: str | None = None,
    ):
        binding = self._require_binding()

        self.core.connections.close_kalshi(
            generation=binding.generation,
            closed_monotonic_ns=(
                closed_monotonic_ns
            ),
        )

        if not count_as_failure:
            return None

        return self.core.record_source_failure(
            "kalshi",
            observed_monotonic_ns=(
                closed_monotonic_ns
            ),
            reconnect_reason=reconnect_reason,
        )

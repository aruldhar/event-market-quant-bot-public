"""Checkpoint 21N-Z-F Coinbase read-only worker session policy.

This module contains NO network calls.

It converts the already-tested Coinbase runtime core into explicit actions for
the later thin transport loop:

- READY
- BLOCKED
- REST_CANDLE_SEED_REQUIRED
- REST_GAP_RECOVERY_REQUIRED

The actual HTTP/WebSocket adapter will only execute those actions.

No Candidate-E signal, settlement, P&L, order, or write behavior exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .kxbtcd_candidate_e_coinbase_rest_recovery import (
    CoinbaseRestRecoveryEvidence,
)
from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_soak_runtime_core import (
    SoakRuntimeCoreError,
    SoakSourceRuntimeCore,
)


class CoinbaseWorkerSessionError(RuntimeError):
    pass


COINBASE_RECOVERY_BACKOFF_RESET_STABLE_NS = 30 * 1_000_000_000


@dataclass(frozen=True)
class CoinbaseWorkerAction:
    kind: str
    reason: str
    connection_generation: int
    target_minute_start_s: int | None = None
    target_minute_end_s: int | None = None
    recovery_from_trade_id: int | None = None
    recovery_target_trade_id: int | None = None


class CoinbaseReadOnlyWorkerSession:
    """Deterministic policy for one Coinbase transport generation."""

    def __init__(
        self,
        core: SoakSourceRuntimeCore,
    ) -> None:
        if not isinstance(
            core,
            SoakSourceRuntimeCore,
        ):
            raise CoinbaseWorkerSessionError(
                "worker session requires SoakSourceRuntimeCore"
            )

        self.core = core
        self.binding = None

    def start_generation(
        self,
        *,
        opened_monotonic_ns: int,
    ):
        current = self.core.connections.current_coinbase

        if (
            current is not None
            and current.connected
        ):
            raise CoinbaseWorkerSessionError(
                "Coinbase generation already open"
            )

        # Explicitly discard any prior-generation candle reference.
        # Generation identity already prevents reuse, but clearing it makes
        # the intended restart semantics visible and auditable.
        self.core.coinbase_rest_seed = None

        self.binding = (
            self.core.open_coinbase_generation(
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
            raise CoinbaseWorkerSessionError(
                "Coinbase worker generation is not open"
            )

        current = (
            self.core.connections.current_coinbase
        )

        if (
            current is None
            or current.generation
            != binding.generation
        ):
            raise CoinbaseWorkerSessionError(
                "Coinbase worker binding is stale"
            )

        return binding

    def evaluate(
        self,
        *,
        decision_epoch_s: int,
        now_monotonic_ns: int,
    ) -> CoinbaseWorkerAction:
        binding = self._require_binding()
        self.core.fsync_due_raw_segments(now_monotonic_ns=now_monotonic_ns)

        builder = binding.builder

        if builder.recovery_required:
            start = builder.recovery_from_trade_id
            target = builder.recovery_target_trade_id

            if start is None or target is None:
                raise CoinbaseWorkerSessionError(
                    "recovery-required builder lacks frozen interval"
                )

            return CoinbaseWorkerAction(
                kind="REST_GAP_RECOVERY_REQUIRED",
                reason="COINBASE_RECOVERY_REQUIRED",
                connection_generation=(
                    binding.generation
                ),
                recovery_from_trade_id=start,
                recovery_target_trade_id=target,
            )

        evidence = self.core.evaluate_coinbase(
            decision_epoch_s=decision_epoch_s,
            now_monotonic_ns=now_monotonic_ns,
        )

        if evidence.status == GateStatus.FATAL:
            raise CoinbaseWorkerSessionError(
                f"fatal Coinbase readiness: {evidence.reason}"
            )

        if evidence.status == GateStatus.PASS:
            # A heartbeat can make a newly reconnected socket appear ready in
            # under a second. Do not erase accumulated retry pressure until
            # that recovered generation has remained ready long enough to be
            # meaningful evidence of recovery.
            if (
                self.core.coinbase_backoff.consecutive_failures == 0
                or now_monotonic_ns - binding.opened_monotonic_ns
                >= COINBASE_RECOVERY_BACKOFF_RESET_STABLE_NS
            ):
                self.core.mark_source_ready("coinbase")

            return CoinbaseWorkerAction(
                kind="READY",
                reason="PASS",
                connection_generation=(
                    binding.generation
                ),
                target_minute_start_s=(
                    evidence.target_minute_start_s
                ),
                target_minute_end_s=(
                    evidence.target_minute_end_s
                ),
            )

        if (
            evidence.builder_status
            == "NO_TRADES_IN_MINUTE"
        ):
            return CoinbaseWorkerAction(
                kind="REST_CANDLE_SEED_REQUIRED",
                reason=evidence.reason,
                connection_generation=(
                    binding.generation
                ),
                target_minute_start_s=(
                    evidence.target_minute_start_s
                ),
                target_minute_end_s=(
                    evidence.target_minute_end_s
                ),
            )

        return CoinbaseWorkerAction(
            kind="BLOCKED",
            reason=evidence.reason,
            connection_generation=(
                binding.generation
            ),
            target_minute_start_s=(
                evidence.target_minute_start_s
            ),
            target_minute_end_s=(
                evidence.target_minute_end_s
            ),
        )

    def ingest_ws_frame(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        decision_epoch_s: int,
    ) -> CoinbaseWorkerAction:
        self._require_binding()

        # Core owns the required raw-first ordering.
        self.core.ingest_coinbase_ws_frame(
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
        )

        return self.evaluate(
            decision_epoch_s=(
                decision_epoch_s
            ),
            now_monotonic_ns=(
                received_monotonic_ns
            ),
        )

    def apply_persisted_rest_candle_seed(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        decision_epoch_s: int,
    ) -> CoinbaseWorkerAction:
        """Bind a successful candle response already persisted by transport."""

        self._require_binding()

        self.core.bind_persisted_coinbase_rest_seed_candle(
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            decision_epoch_s=(
                decision_epoch_s
            ),
        )

        return self.evaluate(
            decision_epoch_s=(
                decision_epoch_s
            ),
            now_monotonic_ns=(
                received_monotonic_ns
            ),
        )

    def apply_rest_candle_seed(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        decision_epoch_s: int,
        request_identity: Mapping[
            str, Any
        ] | None = None,
    ) -> CoinbaseWorkerAction:
        self._require_binding()

        self.core.ingest_coinbase_rest_seed_candle(
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            decision_epoch_s=(
                decision_epoch_s
            ),
            request_identity=(
                request_identity
            ),
        )

        return self.evaluate(
            decision_epoch_s=(
                decision_epoch_s
            ),
            now_monotonic_ns=(
                received_monotonic_ns
            ),
        )

    def apply_rest_gap_recovery(
        self,
        *,
        evidence: CoinbaseRestRecoveryEvidence,
        decision_epoch_s: int,
        now_monotonic_ns: int,
    ) -> CoinbaseWorkerAction:
        binding = self._require_binding()

        result = (
            binding.builder.apply_rest_recovery(
                evidence
            )
        )

        status = str(
            result.get("status", "")
        )

        if status not in {
            "RECOVERY_COMPLETE",
            "RECOVERY_INCOMPLETE",
            "RECOVERY_EVIDENCE_STALE",
            "NO_RECOVERY_REQUIRED",
        }:
            raise CoinbaseWorkerSessionError(
                "unexpected Coinbase REST recovery result"
            )

        return self.evaluate(
            decision_epoch_s=(
                decision_epoch_s
            ),
            now_monotonic_ns=(
                now_monotonic_ns
            ),
        )

    def disconnect(
        self,
        *,
        closed_monotonic_ns: int,
        count_as_failure: bool = True,
    ):
        binding = self._require_binding()

        self.core.connections.close_coinbase(
            generation=binding.generation,
            closed_monotonic_ns=(
                closed_monotonic_ns
            ),
        )

        if not count_as_failure:
            return None

        return self.core.record_source_failure(
            "coinbase",
            observed_monotonic_ns=(
                closed_monotonic_ns
            ),
        )

"""Pure offline lifecycle model for the frozen V2 hybrid micro probe.

The model deliberately represents confirmation facts and eligibility states,
not order API calls.  It contains no network, credentials, durable outbox, or
venue write capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable

from .kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import (
    BidLevel,
    HybridExitAssessment,
    HybridExitPhase,
    ReconciledPosition,
    assess_hybrid_exit,
    reassess_after_handoff_reconciliation,
)


class HybridProbeState(str, Enum):
    FLAT = "FLAT"
    LONG_RESTING_EXIT = "LONG_RESTING_EXIT"
    CANCEL_RECONCILIATION_REQUIRED = "CANCEL_RECONCILIATION_REQUIRED"
    FOK_EVALUATION_ALLOWED = "FOK_EVALUATION_ALLOWED"
    RESTING_EXIT_REPLACEMENT_REQUIRED = "RESTING_EXIT_REPLACEMENT_REQUIRED"
    CLOSED = "CLOSED"


class HybridProbeStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class OfflineHybridProbe:
    state: HybridProbeState
    entry_attempts: int
    maximum_entry_attempts: int
    required_total_net_proceeds: Decimal | None
    latest_assessment: HybridExitAssessment | None

    @classmethod
    def new(cls, *, maximum_entry_attempts: int = 5) -> "OfflineHybridProbe":
        if maximum_entry_attempts < 1:
            raise HybridProbeStateError("maximum entry attempts must be positive")
        return cls(
            state=HybridProbeState.FLAT,
            entry_attempts=0,
            maximum_entry_attempts=maximum_entry_attempts,
            required_total_net_proceeds=None,
            latest_assessment=None,
        )

    def record_unfilled_entry_attempt(self) -> "OfflineHybridProbe":
        if self.state is not HybridProbeState.FLAT:
            raise HybridProbeStateError("entry attempt requires flat state")
        if self.entry_attempts >= self.maximum_entry_attempts:
            raise HybridProbeStateError("maximum entry attempts reached")
        return self.__class__(
            state=self.state,
            entry_attempts=self.entry_attempts + 1,
            maximum_entry_attempts=self.maximum_entry_attempts,
            required_total_net_proceeds=None,
            latest_assessment=None,
        )

    def record_confirmed_entry(
        self, *, required_total_net_proceeds: Decimal
    ) -> "OfflineHybridProbe":
        if self.state is not HybridProbeState.FLAT:
            raise HybridProbeStateError("confirmed entry requires flat state")
        if self.entry_attempts >= self.maximum_entry_attempts:
            raise HybridProbeStateError("maximum entry attempts reached")
        if required_total_net_proceeds <= Decimal("0"):
            raise HybridProbeStateError("required target must be positive")
        return self.__class__(
            state=HybridProbeState.LONG_RESTING_EXIT,
            entry_attempts=self.entry_attempts + 1,
            maximum_entry_attempts=self.maximum_entry_attempts,
            required_total_net_proceeds=required_total_net_proceeds,
            latest_assessment=None,
        )

    def observe_fresh_ladder(
        self,
        *,
        position: ReconciledPosition,
        bids: Iterable[BidLevel],
        supplied_exit_fee: Decimal,
    ) -> "OfflineHybridProbe":
        if self.state is not HybridProbeState.LONG_RESTING_EXIT:
            raise HybridProbeStateError("fresh ladder requires resting exit state")
        assessment = assess_hybrid_exit(
            position=position,
            bids=bids,
            supplied_exit_fee=supplied_exit_fee,
            required_total_net_proceeds=self.required_total_net_proceeds,
        )
        if assessment.phase is HybridExitPhase.CLOSED:
            next_state = HybridProbeState.CLOSED
        elif assessment.phase is HybridExitPhase.HANDOFF_REQUIRED:
            next_state = HybridProbeState.CANCEL_RECONCILIATION_REQUIRED
        else:
            next_state = HybridProbeState.LONG_RESTING_EXIT
        return self.__class__(
            state=next_state,
            entry_attempts=self.entry_attempts,
            maximum_entry_attempts=self.maximum_entry_attempts,
            required_total_net_proceeds=self.required_total_net_proceeds,
            latest_assessment=assessment,
        )

    def record_cancel_reconciliation(
        self,
        *,
        position: ReconciledPosition,
        bids: Iterable[BidLevel],
        supplied_exit_fee: Decimal,
    ) -> "OfflineHybridProbe":
        if self.state is not HybridProbeState.CANCEL_RECONCILIATION_REQUIRED:
            raise HybridProbeStateError("cancel reconciliation is not currently required")
        assessment = reassess_after_handoff_reconciliation(
            prior=self.latest_assessment,
            reconciled_position=position,
            bids=bids,
            supplied_exit_fee=supplied_exit_fee,
        )
        next_state = {
            HybridExitPhase.CLOSED: HybridProbeState.CLOSED,
            HybridExitPhase.HANDOFF_REQUIRED: HybridProbeState.FOK_EVALUATION_ALLOWED,
            HybridExitPhase.RESTING_EXIT_RECALCULATION_REQUIRED:
                HybridProbeState.RESTING_EXIT_REPLACEMENT_REQUIRED,
        }[assessment.phase]
        return self.__class__(
            state=next_state,
            entry_attempts=self.entry_attempts,
            maximum_entry_attempts=self.maximum_entry_attempts,
            required_total_net_proceeds=self.required_total_net_proceeds,
            latest_assessment=assessment,
        )

    def record_fok_reconciliation(
        self, *, position: ReconciledPosition
    ) -> "OfflineHybridProbe":
        if self.state is not HybridProbeState.FOK_EVALUATION_ALLOWED:
            raise HybridProbeStateError("FOK reconciliation is not currently allowed")
        if position.remaining_quantity == Decimal("0"):
            next_state = HybridProbeState.CLOSED
        else:
            next_state = HybridProbeState.RESTING_EXIT_REPLACEMENT_REQUIRED
        return self.__class__(
            state=next_state,
            entry_attempts=self.entry_attempts,
            maximum_entry_attempts=self.maximum_entry_attempts,
            required_total_net_proceeds=self.required_total_net_proceeds,
            latest_assessment=self.latest_assessment,
        )

    def record_resting_exit_replaced(self) -> "OfflineHybridProbe":
        if self.state is not HybridProbeState.RESTING_EXIT_REPLACEMENT_REQUIRED:
            raise HybridProbeStateError("resting exit replacement is not required")
        return self.__class__(
            state=HybridProbeState.LONG_RESTING_EXIT,
            entry_attempts=self.entry_attempts,
            maximum_entry_attempts=self.maximum_entry_attempts,
            required_total_net_proceeds=self.required_total_net_proceeds,
            latest_assessment=self.latest_assessment,
        )

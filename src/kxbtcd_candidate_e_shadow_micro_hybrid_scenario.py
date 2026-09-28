"""Run the frozen micro hybrid-exit policy against reconstructed raw books.

This module is intentionally an offline scenario evaluator.  It receives
already verified/reconstructed frames and returns eligibility observations; it
does not open connections, create orders, or persist an order intent.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Iterator

from .kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import (
    BidLevel,
    ReconciledPosition,
)
from .kxbtcd_candidate_e_v2_micro_hybrid_state_machine_offline import (
    HybridProbeState,
    OfflineHybridProbe,
)
from .kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook


class ShadowMicroHybridScenarioError(ValueError):
    pass


@dataclass(frozen=True)
class ShadowHybridExitObservation:
    market_ticker: str
    received_utc: str
    received_monotonic_ns: int
    state: HybridProbeState
    full_exit_eligible: bool
    worst_price_required: Decimal | None
    total_net_proceeds_if_filled: Decimal | None


def evaluate_shadow_hybrid_exit(
    books: Iterable[ReconstructedKalshiBook], *, market_ticker: str,
    position: ReconciledPosition, supplied_exit_fee: Decimal,
    required_total_net_proceeds: Decimal,
) -> Iterator[ShadowHybridExitObservation]:
    """Evaluate every reconstructed book for one already-confirmed position.

    The evaluator starts at the post-entry resting-exit state.  Its first
    eligible book marks the exact offline point at which a later live
    cancel/reconcile workflow would be allowed; it does not model that venue
    workflow or emit any side effect.
    """
    if not market_ticker:
        raise ShadowMicroHybridScenarioError("market ticker is required")
    if required_total_net_proceeds <= Decimal("0"):
        raise ShadowMicroHybridScenarioError("required target must be positive")

    probe = OfflineHybridProbe.new().record_confirmed_entry(
        required_total_net_proceeds=required_total_net_proceeds
    )
    for reconstructed in books:
        if reconstructed.market_ticker != market_ticker:
            continue
        bids = tuple(
            BidLevel(price=level.price, quantity=level.quantity)
            for level in reconstructed.book_state.yes_bids
        )
        probe = probe.observe_fresh_ladder(
            position=position, bids=bids, supplied_exit_fee=supplied_exit_fee
        )
        assessment = probe.latest_assessment
        yield ShadowHybridExitObservation(
            market_ticker=market_ticker,
            received_utc=reconstructed.received_utc,
            received_monotonic_ns=reconstructed.received_monotonic_ns,
            state=probe.state,
            full_exit_eligible=(
                probe.state is HybridProbeState.CANCEL_RECONCILIATION_REQUIRED
            ),
            worst_price_required=assessment.worst_price_required,
            total_net_proceeds_if_filled=assessment.total_net_proceeds_if_filled,
        )
        if probe.state is HybridProbeState.CANCEL_RECONCILIATION_REQUIRED:
            return

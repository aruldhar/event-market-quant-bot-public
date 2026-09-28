"""Read-only selection of frozen V2 entry candidates from evaluations."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    V2MarketEvaluation,
    V2SideEvaluation,
    signal_from_evaluation,
)


FROZEN_PRIMARY_NET_EDGE_THRESHOLD = Decimal("0.02")
SIDE_TIE_BREAK = {"YES": 0, "NO": 1}


@dataclass(frozen=True)
class ShadowV2Selection:
    market_ticker: str
    side: str
    net_edge_per_contract: Decimal
    signal: object


def select_candidates(
    evaluations: Iterable[V2MarketEvaluation],
    *,
    net_edge_threshold: Decimal,
) -> tuple[ShadowV2Selection, ...]:
    """Return candidates meeting one predeclared V2 net-edge threshold.

    This selector has no fill assumption and emits no order. It retains the
    frozen depth condition and deterministic market/side tie-break so every
    scenario differs only by its explicitly declared threshold.
    """
    if not isinstance(net_edge_threshold, Decimal) or not net_edge_threshold.is_finite():
        raise ValueError("net edge threshold must be a finite Decimal")
    selected: list[ShadowV2Selection] = []
    for evaluation in evaluations:
        if evaluation.status != "EVALUABLE":
            continue
        for side in evaluation.sides:
            if not side.depth_qualifies or side.net_edge < net_edge_threshold:
                continue
            selected.append(ShadowV2Selection(
                market_ticker=evaluation.market_ticker,
                side=side.side,
                net_edge_per_contract=side.net_edge,
                signal=signal_from_evaluation(evaluation, side),
            ))
    return tuple(sorted(
        selected,
        key=lambda item: (
            -item.net_edge_per_contract,
            item.market_ticker,
            SIDE_TIE_BREAK.get(item.side, 99),
        ),
    ))


def select_frozen_primary_candidates(
    evaluations: Iterable[V2MarketEvaluation],
) -> tuple[ShadowV2Selection, ...]:
    """Compatibility wrapper for the retained V2 $0.02 primary rule."""
    return select_candidates(
        evaluations,
        net_edge_threshold=FROZEN_PRIMARY_NET_EDGE_THRESHOLD,
    )

"""Build read-only event-level frozen V2 decisions from causal evaluations."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby
from typing import Iterable, Iterator

from .kxbtcd_candidate_e_shadow_v2_selection import (
    ShadowV2Selection,
    select_frozen_primary_candidates,
)
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    V2MarketEvaluation,
)


class ShadowV2EventReportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShadowV2DecisionReport:
    event_ticker: str
    decision_timestamp_ms: int
    evaluation_count: int
    qualified_candidate_count: int
    selected: ShadowV2Selection | None


def iter_frozen_v2_event_decisions(
    evaluations: Iterable[V2MarketEvaluation],
) -> Iterator[ShadowV2DecisionReport]:
    """Report one deterministic frozen V2 candidate (or none) per timestamp.

    Inputs must be globally ordered by event then timestamp.  The function does
    not infer missing markets: a report describes only the supplied causal,
    reconstructed evaluations and remains unsuitable as an execution command.
    """
    prior_key: tuple[str, int] | None = None
    for key, grouped in groupby(
        evaluations, key=lambda item: (item.event_ticker, item.decision_timestamp_ms)
    ):
        if prior_key is not None and key < prior_key:
            raise ShadowV2EventReportError("evaluations are not event-time ordered")
        prior_key = key
        rows = tuple(grouped)
        if any(item.event_ticker != key[0] or item.decision_timestamp_ms != key[1] for item in rows):
            raise ShadowV2EventReportError("evaluation group identity mismatch")
        qualified = select_frozen_primary_candidates(rows)
        yield ShadowV2DecisionReport(
            event_ticker=key[0], decision_timestamp_ms=key[1],
            evaluation_count=len(rows), qualified_candidate_count=len(qualified),
            selected=qualified[0] if qualified else None,
        )

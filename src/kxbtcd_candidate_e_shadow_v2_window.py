"""Complete causal ATM-window evaluation for archived Candidate-E V2 evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator

from .kxbtcd_candidate_e_prospective_live_collector import EventLadder
from .kxbtcd_candidate_e_shadow_causal_join import CausalShadowBookPoint
from .kxbtcd_candidate_e_shadow_v2_evaluator import evaluate_causal_v2_market
from .kxbtcd_candidate_e_shadow_v2_event_report import iter_frozen_v2_event_decisions
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import spot_window


class ShadowV2WindowError(RuntimeError):
    pass


def _receipt_epoch_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowV2WindowError("book receipt UTC is invalid") from exc
    if parsed.tzinfo is None:
        raise ShadowV2WindowError("book receipt UTC lacks timezone")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


@dataclass(frozen=True)
class ShadowV2WindowReport:
    decision_timestamp_ms: int
    status: str
    required_market_tickers: tuple[str, ...]
    missing_market_tickers: tuple[str, ...]
    selected_market_ticker: str | None
    selected_side: str | None


def iter_complete_causal_v2_windows(
    *, event_ladder: EventLadder, points: Iterable[CausalShadowBookPoint],
) -> Iterator[ShadowV2WindowReport]:
    """Evaluate only complete current ATM ±5 windows, never inferred books."""
    latest = {}
    previous_ns = -1
    for point in points:
        if point.book.received_monotonic_ns < previous_ns:
            raise ShadowV2WindowError("causal points are not receipt ordered")
        previous_ns = point.book.received_monotonic_ns
        if point.book.market_ticker not in {row.market_ticker for row in event_ladder.markets}:
            raise ShadowV2WindowError("book market is outside archived event ladder")
        latest[point.book.market_ticker] = point.book
        window = spot_window(
            event_ticker=event_ladder.event_ticker,
            btc_spot=point.completed_candle.close,
            event_ladder=event_ladder.markets,
        )
        required = tuple(row.market_ticker for row in window)
        missing = tuple(ticker for ticker in required if ticker not in latest)
        decision_ms = _receipt_epoch_ms(point.book.received_utc)
        if missing:
            yield ShadowV2WindowReport(
                decision_timestamp_ms=decision_ms, status="INCOMPLETE_WINDOW",
                required_market_tickers=required, missing_market_tickers=missing,
                selected_market_ticker=None, selected_side=None,
            )
            continue
        evaluations = tuple(evaluate_causal_v2_market(
            event_ladder=event_ladder,
            point=CausalShadowBookPoint(book=latest[ticker], completed_candle=point.completed_candle),
            decision_timestamp_ms=decision_ms,
        ) for ticker in required)
        report = next(iter_frozen_v2_event_decisions(evaluations))
        yield ShadowV2WindowReport(
            decision_timestamp_ms=report.decision_timestamp_ms, status="COMPLETE_WINDOW",
            required_market_tickers=required, missing_market_tickers=(),
            selected_market_ticker=None if report.selected is None else report.selected.market_ticker,
            selected_side=None if report.selected is None else report.selected.side,
        )

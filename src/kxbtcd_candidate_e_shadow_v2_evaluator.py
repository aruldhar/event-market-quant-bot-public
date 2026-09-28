"""Evaluate one causal archived market point with the frozen Candidate-E V2 code."""
from __future__ import annotations

from datetime import datetime, timezone

from .kxbtcd_candidate_e_continuous_btc_materialization import ContinuousBtcRow
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    VerifiedSegmentTimeline,
    VerifiedTickerTimeline,
)
from .kxbtcd_candidate_e_prospective_live_collector import EventLadder
from .kxbtcd_candidate_e_shadow_causal_join import CausalShadowBookPoint
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    V2MarketEvaluation,
    WindowMarket,
    evaluate_market,
    spot_window,
)


class ShadowV2EvaluatorError(RuntimeError):
    pass


def _utc_epoch_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowV2EvaluatorError("archive book receipt UTC is invalid") from exc
    if parsed.tzinfo is None:
        raise ShadowV2EvaluatorError("archive book receipt UTC lacks timezone")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _utc_text(epoch_s: int) -> str:
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_causal_v2_market(
    *, event_ladder: EventLadder, point: CausalShadowBookPoint,
    decision_timestamp_ms: int | None = None,
    selected_market: WindowMarket | None = None,
) -> V2MarketEvaluation:
    """Apply the retained V2 evaluator to a single verified causal book point.

    No model coefficient, threshold, fee, or depth rule is reimplemented here.
    Without ``selected_market``, a point outside the dynamic ATM ±5 window is
    refused rather than scored.  The explicit selected-market path is reserved
    for the separately labelled frozen-ATM-five live-shadow challenger.
    """
    book = point.book
    candle = point.completed_candle
    book_receipt_ms = _utc_epoch_ms(book.received_utc)
    if decision_timestamp_ms is None:
        decision_timestamp_ms = book_receipt_ms
    if decision_timestamp_ms < book_receipt_ms:
        raise ShadowV2EvaluatorError("decision precedes archived book receipt")
    if event_ladder.close_timestamp_ms <= decision_timestamp_ms:
        raise ShadowV2EvaluatorError("book receipt is after event close")
    windows = (
        (selected_market,)
        if selected_market is not None
        else spot_window(
            event_ticker=event_ladder.event_ticker,
            btc_spot=candle.close,
            event_ladder=event_ladder.markets,
        )
    )
    if selected_market is not None and selected_market.event_ticker != event_ladder.event_ticker:
        raise ShadowV2EvaluatorError("selected market belongs to another event")
    selected = [row for row in windows if row.market_ticker == book.market_ticker]
    if len(selected) != 1:
        raise ShadowV2EvaluatorError("book market is outside causal ATM window")
    state = book.book_state
    timeline = VerifiedTickerTimeline(
        ticker=book.market_ticker,
        segments=(VerifiedSegmentTimeline(
            segment_index=0, start_timestamp_ms=decision_timestamp_ms,
            end_timestamp_ms=decision_timestamp_ms,
            states=(state.__class__(
                timestamp_ms=decision_timestamp_ms,
                yes_bids=state.yes_bids,
                yes_asks=state.yes_asks,
            ),),
        ),),
    )
    btc_row = ContinuousBtcRow(
        event_ticker=event_ladder.event_ticker,
        event_close_time_utc=event_ladder.close_time_utc,
        minute_start_utc=_utc_text(candle.minute_start_epoch_s),
        minute_end_utc=_utc_text(candle.minute_start_epoch_s + 60),
        close_price=candle.close,
    )
    return evaluate_market(
        market=selected[0], decision_timestamp_ms=decision_timestamp_ms,
        event_close_timestamp_ms=event_ladder.close_timestamp_ms,
        timeline=timeline, btc_row=btc_row,
    )

from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_continuous_btc_materialization import ContinuousBtcRow
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState
from src.kxbtcd_candidate_e_prospective_live_collector import EventLadder, LadderMarket
from src.kxbtcd_candidate_e_shadow_causal_join import CausalShadowBookPoint
from src.kxbtcd_candidate_e_shadow_coinbase_candle_replay import ReconstructedCoinbaseCandle
from src.kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook
from src.kxbtcd_candidate_e_shadow_v2_evaluator import ShadowV2EvaluatorError, evaluate_causal_v2_market


def ladder():
    return EventLadder(
        event_ticker="KXBTCD-TEST", close_time_utc="2026-09-08T00:10:00Z",
        close_timestamp_ms=1788826200000,
        markets=(LadderMarket("KXBTCD-TEST", "T1", Decimal("100000"), 0, 1, None),),
    )


def point(ticker="T1"):
    return CausalShadowBookPoint(
        book=ReconstructedKalshiBook(
            market_ticker=ticker, received_utc="2026-09-08T00:02:00Z",
            received_monotonic_ns=2,
            book_state=BookState(1, (BookLevel(Decimal("0.50"), Decimal("2")),),
                                 (BookLevel(Decimal("0.60"), Decimal("2")),)),
        ),
        completed_candle=ReconstructedCoinbaseCandle(
            minute_start_epoch_s=1788825600, close=Decimal("100000"),
            received_utc="2026-09-08T00:01:01Z", received_monotonic_ns=1,
        ),
    )


def test_adapter_reuses_frozen_v2_evaluator_for_causal_archived_point():
    result = evaluate_causal_v2_market(event_ladder=ladder(), point=point())
    assert result.status == "EVALUABLE"
    assert result.q_market == Decimal("0.55")
    assert result.btc_spot == Decimal("100000")
    assert {side.side for side in result.sides} == {"YES", "NO"}


def test_adapter_rejects_book_not_in_full_ladder_or_causal_window():
    with pytest.raises(ShadowV2EvaluatorError, match="outside causal"):
        evaluate_causal_v2_market(event_ladder=ladder(), point=point("OTHER"))
    with pytest.raises(ShadowV2EvaluatorError, match="precedes"):
        evaluate_causal_v2_market(
            event_ladder=ladder(), point=point(), decision_timestamp_ms=1
        )

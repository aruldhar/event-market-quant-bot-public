from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel,
    BookState,
)
from src.kxbtcd_candidate_e_shadow_causal_join import (
    ShadowCausalJoinError,
    iter_causal_book_points,
)
from src.kxbtcd_candidate_e_shadow_coinbase_candle_replay import ReconstructedCoinbaseCandle
from src.kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook


def candle(*, minute, receipt):
    return ReconstructedCoinbaseCandle(
        minute_start_epoch_s=minute, close=Decimal("100000"),
        received_utc="2026-09-08T00:01:01Z", received_monotonic_ns=receipt,
    )


def book(*, receipt, utc="2026-09-08T00:02:00Z"):
    return ReconstructedKalshiBook(
        market_ticker="T1", received_utc=utc, received_monotonic_ns=receipt,
        book_state=BookState(1, (BookLevel(Decimal("0.5"), Decimal("1")),), ()),
    )


def test_join_uses_only_completed_candle_received_before_book():
    points = list(iter_causal_book_points(
        (candle(minute=1788825600, receipt=5),
         candle(minute=1788825660, receipt=15)),
        (book(receipt=10), book(receipt=20, utc="2026-09-08T00:03:00Z")),
    ))
    assert [point.completed_candle.minute_start_epoch_s for point in points] == [
        1788825600, 1788825660
    ]


def test_join_skips_future_or_incomplete_candle_and_rejects_out_of_order_books():
    assert list(iter_causal_book_points(
        (candle(minute=1788825720, receipt=5),), (book(receipt=10),)
    )) == []
    with pytest.raises(ShadowCausalJoinError, match="not receipt ordered"):
        list(iter_causal_book_points((), (book(receipt=2), book(receipt=1))))

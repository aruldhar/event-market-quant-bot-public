from decimal import Decimal

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState
from src.kxbtcd_candidate_e_prospective_live_collector import EventLadder, LadderMarket
from src.kxbtcd_candidate_e_shadow_causal_join import CausalShadowBookPoint
from src.kxbtcd_candidate_e_shadow_coinbase_candle_replay import ReconstructedCoinbaseCandle
from src.kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook
from src.kxbtcd_candidate_e_shadow_v2_window import iter_complete_causal_v2_windows


def ladder():
    return EventLadder("KXBTCD-TEST", "2026-09-08T00:10:00Z", 1788826200000, (
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 2, None),
        LadderMarket("KXBTCD-TEST", "T2", Decimal("100000"), 1, 2, None),
    ))


def point(ticker, *, ns, utc):
    return CausalShadowBookPoint(
        ReconstructedKalshiBook(ticker, utc, ns, BookState(
            1, (BookLevel(Decimal("0.50"), Decimal("2")),),
            (BookLevel(Decimal("0.60"), Decimal("2")),),
        )),
        ReconstructedCoinbaseCandle(1788825600, Decimal("100000"),
                                   "2026-09-08T00:01:01Z", 1),
    )


def test_window_requires_every_current_atm_market_before_selection():
    reports = list(iter_complete_causal_v2_windows(
        event_ladder=ladder(), points=(
            point("T1", ns=2, utc="2026-09-08T00:02:00Z"),
            point("T2", ns=3, utc="2026-09-08T00:02:01Z"),
        ),
    ))
    assert reports[0].status == "INCOMPLETE_WINDOW"
    assert reports[0].missing_market_tickers == ("T2",)
    assert reports[1].status == "COMPLETE_WINDOW"
    assert reports[1].missing_market_tickers == ()

from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel,
    BookState,
)
from src.kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook
from src.kxbtcd_candidate_e_shadow_micro_hybrid_scenario import (
    ShadowMicroHybridScenarioError,
    evaluate_shadow_hybrid_exit,
)
from src.kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import ReconciledPosition
from src.kxbtcd_candidate_e_v2_micro_hybrid_state_machine_offline import HybridProbeState


TICKER = "KXBTCD-TEST-T100"


def book(*, bid_price: str, quantity: str, ns: int) -> ReconstructedKalshiBook:
    return ReconstructedKalshiBook(
        market_ticker=TICKER,
        received_utc="2026-09-08T00:00:00Z",
        received_monotonic_ns=ns,
        book_state=BookState(
            timestamp_ms=ns,
            yes_bids=(BookLevel(Decimal(bid_price), Decimal(quantity)),),
            yes_asks=(BookLevel(Decimal("0.90"), Decimal("1")),),
        ),
    )


def test_shadow_scenario_waits_for_full_depth_then_reports_first_eligible_book():
    observations = list(evaluate_shadow_hybrid_exit(
        (book(bid_price="0.70", quantity="0.005", ns=1),
         book(bid_price="0.80", quantity="0.01", ns=2),
         book(bid_price="0.90", quantity="0.01", ns=3)),
        market_ticker=TICKER,
        position=ReconciledPosition(Decimal("0.01"), Decimal("0")),
        supplied_exit_fee=Decimal("0.0001"),
        required_total_net_proceeds=Decimal("0.0079"),
    ))
    assert [item.state for item in observations] == [
        HybridProbeState.LONG_RESTING_EXIT,
        HybridProbeState.CANCEL_RECONCILIATION_REQUIRED,
    ]
    assert observations[-1].full_exit_eligible is True
    assert observations[-1].worst_price_required == Decimal("0.80")


def test_shadow_scenario_ignores_other_tickers_and_rejects_invalid_target():
    other = ReconstructedKalshiBook(
        market_ticker="OTHER", received_utc="2026-09-08T00:00:00Z",
        received_monotonic_ns=1, book_state=book(bid_price="0.90", quantity="1", ns=1).book_state,
    )
    assert list(evaluate_shadow_hybrid_exit(
        (other,), market_ticker=TICKER,
        position=ReconciledPosition(Decimal("0.01"), Decimal("0")),
        supplied_exit_fee=Decimal("0"), required_total_net_proceeds=Decimal("0.001"),
    )) == []
    with pytest.raises(ShadowMicroHybridScenarioError, match="target"):
        list(evaluate_shadow_hybrid_exit(
            (), market_ticker=TICKER,
            position=ReconciledPosition(Decimal("0.01"), Decimal("0")),
            supplied_exit_fee=Decimal("0"), required_total_net_proceeds=Decimal("0"),
        ))

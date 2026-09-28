from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_dashboard_shadow_projection import (
    EXACT_OBSERVED_DEPTH_IOC,
    SHADOW_EVENT_SCHEMA_VERSION,
    project_shadow_ledger_events,
)
from src.kxbtcd_candidate_e_live_shadow_micro_simulator import LiveShadowMicroState
from src.kxbtcd_candidate_e_live_shadow_settlement import (
    OfficialKalshiSettlement,
    LiveShadowSettlementError,
    settle_live_shadow_micro_for_scenario,
)
from src.kxbtcd_candidate_e_live_shadow_settlement_feed import (
    CANONICAL_SETTLEMENT_FEED_FILENAME,
    LiveShadowSettlementPublisher,
    read_live_shadow_settlements,
)
from src.kxbtcd_candidate_e_shadow_v2_scenarios import PRIMARY_SHADOW_V2_SCENARIO


def _open_state():
    return LiveShadowMicroState(
        event_ticker="KXBTCD-TEST", position_id="position-1", market_ticker="T1", side="YES",
        remaining_quantity=Decimal("200"), entry_cost=Decimal("100"),
        required_total_net_proceeds=Decimal("104"), entry_attempts=1, closed_event_tickers=frozenset(),
    )


def _entry_fill():
    return {
        "schema_version": SHADOW_EVENT_SCHEMA_VERSION, "run_id": "run-1",
        "event_sequence": 1, "event_type": "shadow_simulated_fill", "position_id": "position-1",
        "market_ticker": "T1", "side": "buy", "simulated_quantity": "200",
        "simulated_price": "0.50", "simulated_fee": "0", "fill_assumption": EXACT_OBSERVED_DEPTH_IOC,
        "observed_book_received_utc": "2026-09-09T01:00:00Z",
    }


def _settle(result="no"):
    return settle_live_shadow_micro_for_scenario(
        prior=_open_state(), run_id="run-1", scenario=PRIMARY_SHADOW_V2_SCENARIO,
        first_event_sequence=2, input_snapshot_sequence=9,
        settlement=OfficialKalshiSettlement("T1", "finalized", result, "2026-09-09T02:00:00Z"),
    )


def test_final_official_loss_closes_position_at_actual_entry_outlay():
    step = _settle("no")
    assert step.state.remaining_quantity == 0
    settlement, closed = step.events
    assert settlement["event_type"] == "shadow_simulated_settlement"
    assert settlement["simulated_settlement_payout"] == "0"
    assert closed["event_type"] == "shadow_position_closed"
    projection = project_shadow_ledger_events((_entry_fill(), *step.events))
    assert projection.trades[0].simulated_flat is True
    assert projection.trades[0].simulated_net_pnl == Decimal("-100")


def test_final_official_win_credits_one_dollar_per_open_contract():
    step = _settle("yes")
    assert step.events[0]["simulated_settlement_payout"] == "200"
    projection = project_shadow_ledger_events((_entry_fill(), *step.events))
    assert projection.trades[0].simulated_net_pnl == Decimal("100")


@pytest.mark.parametrize("settlement", [
    OfficialKalshiSettlement("T1", "determined", "yes", "2026-09-09T02:00:00Z"),
    OfficialKalshiSettlement("T1", "finalized", "", "2026-09-09T02:00:00Z"),
    OfficialKalshiSettlement("T2", "finalized", "yes", "2026-09-09T02:00:00Z"),
])
def test_settlement_rejects_nonfinal_ambiguous_or_wrong_market_evidence(settlement):
    with pytest.raises(LiveShadowSettlementError):
        settle_live_shadow_micro_for_scenario(
            prior=_open_state(), run_id="run-1", scenario=PRIMARY_SHADOW_V2_SCENARIO,
            first_event_sequence=2, input_snapshot_sequence=9, settlement=settlement,
        )


def test_final_settlement_feed_is_atomic_deduplicated_and_run_bound(tmp_path):
    path = tmp_path / CANONICAL_SETTLEMENT_FEED_FILENAME
    publisher = LiveShadowSettlementPublisher(run_id="run-1", output_path=path)
    settlement = OfficialKalshiSettlement("T1", "finalized", "yes", "2026-09-09T02:00:00Z")
    assert publisher.publish(settlement) is True
    assert publisher.publish(settlement) is False
    assert read_live_shadow_settlements(path=path, run_id="run-1") == (settlement,)
    restarted = LiveShadowSettlementPublisher(run_id="run-1", output_path=path)
    assert restarted.publish(settlement) is False

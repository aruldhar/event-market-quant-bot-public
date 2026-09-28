from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_dashboard_projection import (
    DashboardProjectionError,
    EVENT_SCHEMA_VERSION,
    project_confirmed_ledger_events,
)


def event(event_sequence, event_type, **fields):
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "run_id": "micro-probe-1",
        "event_sequence": event_sequence,
        "event_type": event_type,
        **fields,
    }


def closed_trade_events():
    return (
        event(1, "decision_recorded", decision_record_id="decision-1"),
        event(2, "confirmed_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
              side="buy", filled_quantity="0.01", fill_price="0.40", venue_fee="0.0001"),
        event(3, "order_status", client_order_id="exit-1", status="resting"),
        event(4, "confirmed_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
              side="sell", filled_quantity="0.01", fill_price="0.60", venue_fee="0.0001"),
        event(5, "position_reconciled", position_id="position-1",
              venue_state_confirmed=True, position_quantity="0"),
    )


def test_projection_uses_confirmed_fills_and_fees_for_realized_pnl():
    projection = project_confirmed_ledger_events(closed_trade_events())
    row = projection.trades[0]
    assert row.reconciled_flat is True
    assert row.entry_filled_quantity == row.exit_filled_quantity == Decimal("0.01")
    assert row.net_position_quantity == 0
    assert row.realized_net_pnl == Decimal("0.0018")
    assert projection.total_realized_net_pnl == Decimal("0.0018")
    assert projection.closed_trade_count == 1


def test_projection_keeps_unreconciled_position_out_of_realized_pnl():
    projection = project_confirmed_ledger_events(closed_trade_events()[:-1])
    row = projection.trades[0]
    assert row.realized_net_pnl is None
    assert projection.total_realized_net_pnl == 0
    assert projection.open_position_count == 1


@pytest.mark.parametrize("events", [
    (event(2, "runtime_metric"), event(1, "runtime_metric")),
    (event(1, "confirmed_fill", position_id="p", market_ticker="T", side="buy",
           filled_quantity="0.01", fill_price="0.4", venue_fee="0"),
     event(2, "position_reconciled", position_id="p", venue_state_confirmed=False, position_quantity="0")),
    (event(1, "confirmed_fill", position_id="p", market_ticker="T", side="buy",
           filled_quantity="0.01", fill_price="0.4", venue_fee="0"),
     event(2, "position_reconciled", position_id="p", venue_state_confirmed=True, position_quantity="0")),
    (event(1, "estimated_fill", position_id="p"),),
])
def test_projection_rejects_noncausal_unconfirmed_or_estimated_trade_facts(events):
    with pytest.raises(DashboardProjectionError):
        project_confirmed_ledger_events(events)

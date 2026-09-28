from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_dashboard_shadow_projection import (
    DashboardShadowProjectionError,
    EXACT_OBSERVED_DEPTH_IOC,
    SHADOW_EVENT_SCHEMA_VERSION,
    project_shadow_ledger_events,
)


def event(sequence, kind, **fields):
    return {"schema_version": SHADOW_EVENT_SCHEMA_VERSION, "run_id": "soak-24h-shadow-1",
            "event_sequence": sequence, "event_type": kind, **fields}


def shadow_fill(sequence, side, **fields):
    payload = {
        "position_id": "shadow-position-1", "market_ticker": "KXBTCD-TEST",
        "side": side, "simulated_quantity": "0.01",
        "simulated_price": "0.40" if side == "buy" else "0.60", "simulated_fee": "0.0001",
        "fill_assumption": EXACT_OBSERVED_DEPTH_IOC,
        "observed_book_received_utc": "2026-09-09T00:00:00Z",
    }
    payload.update(fields)
    return event(sequence, "shadow_simulated_fill", **payload)


def test_shadow_projection_never_calls_book_walk_pnl_realized():
    projection = project_shadow_ledger_events((
        event(1, "shadow_decision", decision_record_id="decision-1"),
        shadow_fill(2, "buy"), shadow_fill(3, "sell"),
        event(4, "shadow_position_closed", position_id="shadow-position-1"),
    ))
    row = projection.trades[0]
    assert row.simulated_flat is True
    assert row.simulated_net_pnl == Decimal("0.0018")
    assert projection.total_simulated_net_pnl == Decimal("0.0018")
    assert not hasattr(row, "realized_net_pnl")


@pytest.mark.parametrize("events", [
    (shadow_fill(1, "sell"),),
    (shadow_fill(1, "buy", fill_assumption="RESTING_ORDER_ASSUMED"),),
    (shadow_fill(2, "buy"), shadow_fill(1, "buy")),
    (shadow_fill(1, "buy"), event(2, "shadow_position_closed", position_id="shadow-position-1")),
])
def test_shadow_projection_rejects_unproven_or_inconsistent_simulation(events):
    with pytest.raises(DashboardShadowProjectionError):
        project_shadow_ledger_events(events)

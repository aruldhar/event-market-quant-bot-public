import json

import pytest

from src.kxbtcd_candidate_e_dashboard_export import DashboardExportError
from src.kxbtcd_candidate_e_dashboard_shadow_export import (
    SHADOW_DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
    export_shadow_dashboard_snapshot,
)
from src.kxbtcd_candidate_e_dashboard_shadow_projection import (
    EXACT_OBSERVED_DEPTH_IOC,
    SHADOW_EVENT_SCHEMA_VERSION,
)


def event(sequence, kind, **fields):
    return {"schema_version": SHADOW_EVENT_SCHEMA_VERSION, "run_id": "soak-24h-shadow-1",
            "event_sequence": sequence, "event_type": kind, **fields}


def fill(sequence, side):
    return event(sequence, "shadow_simulated_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
                 side=side, simulated_quantity="0.01", simulated_price="0.4" if side == "buy" else "0.6",
                 simulated_fee="0.0001", fill_assumption=EXACT_OBSERVED_DEPTH_IOC,
                 observed_book_received_utc="2026-09-09T00:00:00Z")


def test_shadow_export_labels_all_pnl_and_fill_limits_as_simulation(tmp_path):
    output = tmp_path / "shadow_dashboard_snapshot.json"
    snapshot = export_shadow_dashboard_snapshot(events=(
        fill(1, "buy"), fill(2, "sell"), event(3, "shadow_position_closed", position_id="position-1"),
    ), generated_utc="2026-09-09T00:00:00Z", output_path=output)
    assert snapshot["schema_version"] == SHADOW_DASHBOARD_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["pnl_basis"] == "SIMULATED_OBSERVED_DEPTH_NOT_VENUE_REALIZED"
    assert snapshot["summary"]["total_simulated_net_pnl"] == "0.0018"
    assert "does_not_prove_queue_priority" in snapshot["fill_limitations"]
    assert json.loads(output.read_text(encoding="utf-8")) == snapshot


def test_shadow_export_rejects_noncanonical_filename(tmp_path):
    with pytest.raises(DashboardExportError):
        export_shadow_dashboard_snapshot(events=(), generated_utc="2026-09-09T00:00:00Z",
                                         output_path=tmp_path / "dashboard_snapshot.json")

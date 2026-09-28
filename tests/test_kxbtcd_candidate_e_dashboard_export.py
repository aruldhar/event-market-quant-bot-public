import json

import pytest

from src.kxbtcd_candidate_e_dashboard_export import (
    DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
    DashboardExportError,
    export_dashboard_snapshot,
)
from src.kxbtcd_candidate_e_dashboard_projection import EVENT_SCHEMA_VERSION


def event(sequence, kind, **fields):
    return {"schema_version": EVENT_SCHEMA_VERSION, "run_id": "probe-1",
            "event_sequence": sequence, "event_type": kind, **fields}


def closed_events():
    return (
        event(1, "confirmed_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
              side="buy", filled_quantity="0.01", fill_price="0.40", venue_fee="0.0001"),
        event(2, "confirmed_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
              side="sell", filled_quantity="0.01", fill_price="0.60", venue_fee="0.0001"),
        event(3, "position_reconciled", position_id="position-1",
              venue_state_confirmed=True, position_quantity="0"),
    )


def test_export_is_atomic_and_serializes_only_sanitized_projection(tmp_path):
    output = tmp_path / "dashboard_snapshot.json"
    snapshot = export_dashboard_snapshot(events=closed_events(), generated_utc="2026-09-09T00:00:00Z",
                                         output_path=output)
    assert snapshot["schema_version"] == DASHBOARD_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["summary"]["total_realized_net_pnl"] == "0.0018"
    assert json.loads(output.read_text(encoding="utf-8")) == snapshot
    assert not (tmp_path / "dashboard_snapshot.json.tmp").exists()


@pytest.mark.parametrize("events, output_name", [
    (closed_events(), "other.json"),
    ((event(1, "confirmed_fill", position_id="api_key_here", market_ticker="KXBTCD-TEST",
            side="buy", filled_quantity="0.01", fill_price="0.40", venue_fee="0"),), "dashboard_snapshot.json"),
])
def test_export_rejects_noncanonical_output_or_credential_like_projection(tmp_path, events, output_name):
    with pytest.raises(DashboardExportError):
        export_dashboard_snapshot(events=events, generated_utc="2026-09-09T00:00:00Z",
                                  output_path=tmp_path / output_name)

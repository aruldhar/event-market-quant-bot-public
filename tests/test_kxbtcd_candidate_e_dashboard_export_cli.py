import json

import pytest

from src.kxbtcd_candidate_e_dashboard_export_cli import main
from src.kxbtcd_candidate_e_dashboard_export import DashboardExportError
from src.kxbtcd_candidate_e_dashboard_projection import EVENT_SCHEMA_VERSION


def event(sequence, kind, **fields):
    return {"schema_version": EVENT_SCHEMA_VERSION, "run_id": "probe-1",
            "event_sequence": sequence, "event_type": kind, **fields}


def ledger(path):
    rows = (
        event(1, "confirmed_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
              side="buy", filled_quantity="0.01", fill_price="0.40", venue_fee="0.0001"),
        event(2, "confirmed_fill", position_id="position-1", market_ticker="KXBTCD-TEST",
              side="sell", filled_quantity="0.01", fill_price="0.60", venue_fee="0.0001"),
        event(3, "position_reconciled", position_id="position-1",
              venue_state_confirmed=True, position_quantity="0"),
    )
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_cli_exports_snapshot_from_normalized_ledger(tmp_path, capsys):
    source = tmp_path / "ledger.jsonl"
    output = tmp_path / "dashboard_snapshot.json"
    ledger(source)
    assert main(["--ledger", str(source), "--generated-utc", "2026-09-09T00:00:00Z",
                 "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["closed_trade_count"] == 1
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["total_realized_net_pnl"] == "0.0018"


def test_cli_rejects_blank_or_invalid_jsonl_records(tmp_path):
    source = tmp_path / "ledger.jsonl"
    output = tmp_path / "dashboard_snapshot.json"
    source.write_text("\n", encoding="utf-8")
    with pytest.raises(DashboardExportError, match="blank"):
        main(["--ledger", str(source), "--generated-utc", "2026-09-09T00:00:00Z",
              "--output", str(output)])

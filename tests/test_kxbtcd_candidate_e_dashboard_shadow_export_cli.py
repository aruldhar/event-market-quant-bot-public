import json

from src.kxbtcd_candidate_e_dashboard_shadow_export_cli import main
from src.kxbtcd_candidate_e_dashboard_shadow_projection import (
    EXACT_OBSERVED_DEPTH_IOC,
    SHADOW_EVENT_SCHEMA_VERSION,
)


def event(sequence, kind, **fields):
    return {"schema_version": SHADOW_EVENT_SCHEMA_VERSION, "run_id": "soak-24h-shadow-1",
            "event_sequence": sequence, "event_type": kind, **fields}


def test_cli_exports_explicitly_simulated_snapshot(tmp_path, capsys):
    ledger = tmp_path / "shadow_ledger.jsonl"
    output = tmp_path / "shadow_dashboard_snapshot.json"
    fill = lambda n, side: event(n, "shadow_simulated_fill", position_id="position-1",
        market_ticker="KXBTCD-TEST", side=side, simulated_quantity="0.01",
        simulated_price="0.4" if side == "buy" else "0.6", simulated_fee="0.0001",
        fill_assumption=EXACT_OBSERVED_DEPTH_IOC,
        observed_book_received_utc="2026-09-09T00:00:00Z")
    ledger.write_text("".join(json.dumps(row) + "\n" for row in (
        fill(1, "buy"), fill(2, "sell"),
        event(3, "shadow_position_closed", position_id="position-1"),
    )), encoding="utf-8")
    assert main(["--ledger", str(ledger), "--generated-utc", "2026-09-09T00:00:00Z",
                 "--output", str(output)]) == 0
    output_summary = json.loads(capsys.readouterr().out)
    assert output_summary["pnl_basis"] == "SIMULATED_OBSERVED_DEPTH_NOT_VENUE_REALIZED"
    assert json.loads(output.read_text(encoding="utf-8"))["trades"][0]["simulated_net_pnl"] == "0.0018"

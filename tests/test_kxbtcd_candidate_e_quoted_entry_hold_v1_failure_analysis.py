from decimal import Decimal
from src.kxbtcd_candidate_e_quoted_entry_hold_v1_failure_analysis import (
    EXPECTED_PREDECLARATION_FINGERPRINT, build_analysis, metrics,
    primary_trade_rows, validate_predeclaration,
)

def _row(event, stage, block, side, p, price, fee, payout, pnl, edge, role="q50", ttc="55"):
    return {
        "threshold_dollars":"0.03","stress_dollars":"0","action":"ENTER",
        "scenario_valid":"true","event_ticker":event,"event_close_time_utc":"2026-01-01T00:00:00Z",
        "stage":stage,"block_id":block,"market_ticker":event+"-M",
        "structural_role":role,"ttc_target_minutes":ttc,"side":side,
        "candidate_probability":str(p),"scenario_purchase_price":str(price),
        "scenario_standard_entry_fee":str(fee),"scenario_realized_pnl":str(pnl),
        "side_payout":str(payout),"quoted_net_edge_per_contract":str(edge),
        "outcome":"1" if payout == 1 and side == "YES" else "0",
    }

def test_predeclaration_valid():
    doc = validate_predeclaration()
    assert doc["failure_analysis_predeclaration_fingerprint"] == EXPECTED_PREDECLARATION_FINGERPRINT

def test_metrics_decompose_fee_and_calibration():
    rows = [
        {**_row("E1","H2","B3","YES",0.8,0.7,0.02,1,0.28,0.08), "_price":Decimal("0.7"),"_fee":Decimal("0.02"),"_pnl":Decimal("0.28"),"_payout":Decimal("1"),"_fair":Decimal("0.8"),"_edge":Decimal("0.08"),"_win":1,"_gross":Decimal("0.3")},
        {**_row("E2","H2","B3","YES",0.8,0.7,0.02,0,-0.72,0.08), "_price":Decimal("0.7"),"_fee":Decimal("0.02"),"_pnl":Decimal("-0.72"),"_payout":Decimal("0"),"_fair":Decimal("0.8"),"_edge":Decimal("0.08"),"_win":0,"_gross":Decimal("-0.7")},
    ]
    m = metrics(rows)
    assert m["entry_count"] == 2
    assert m["win_rate"] == 0.5
    assert m["gross_pnl_before_fee"] == "-0.4"
    assert m["total_fee"] == "0.04"
    assert m["total_net_pnl"] == "-0.44"
    assert m["calibration_gap_win_rate_minus_fair"] == "-0.3"

def test_primary_trade_rows_rejects_wrong_count():
    try:
        primary_trade_rows([])
    except Exception as exc:
        assert "entry count changed" in str(exc)
    else:
        raise AssertionError("expected fail closed")


def test_build_analysis_end_to_end_159():
    from src.kxbtcd_candidate_e_quoted_entry_hold_v1_failure_analysis import build_analysis, validate_predeclaration
    rows = []
    stages = ["H1_OOF","H2","H3"]
    blocks = ["B0","B1","B2","B3","B4"]
    roles = ["q10","q30","q50","q70","q90"]
    ttcs = ["55","50","45","40","35","30"]
    for i in range(159):
        side = "YES" if i % 2 == 0 else "NO"
        # Keep selected-side fair probability at 0.8 on both sides.
        p = 0.8 if side == "YES" else 0.2
        win = (i % 7) != 0
        payout = 1 if win else 0
        price = [0.2,0.4,0.6,0.8][i % 4]
        fee = 0.02
        pnl = payout - price - fee
        rows.append(_row(
            f"E{i:03d}", stages[i % 3], blocks[i % 5], side, p, price, fee,
            payout, pnl, [0.035,0.045,0.06,0.08][i % 4],
            role=roles[i % 5], ttc=ttcs[i % 6],
        ))
    config = validate_predeclaration()
    summary, slices, tails, comparisons = build_analysis(
        rows, config, {"event_pnl_scenarios":"synthetic"}
    )
    assert summary["primary_population"]["entry_count"] == 159
    assert summary["interpretation"]["successor_selected"] is False
    assert len(tails) == 30
    assert any(r["comparison"] == "H2_vs_H3" for r in comparisons)
    assert any(r["slice_dimension"] == "quoted_net_edge_bucket" for r in slices)

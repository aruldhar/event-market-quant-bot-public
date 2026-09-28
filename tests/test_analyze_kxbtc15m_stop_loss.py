from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot, simulate_policy
from analyze_kxbtc15m_stop_loss import percentile, summarize_stop_rows
from audit_kxbtc15m_raw_depth import ParsedBook


def book(yes_bid: str, no_bid: str) -> ParsedBook:
    return ParsedBook(
        ((Decimal(yes_bid), Decimal("10000")),),
        ((Decimal(no_bid), Decimal("10000")),),
    )


def falling_then_recovering_snapshots():
    start = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    values = [
        (0, ".20", ".70"),
        (1, ".20", ".70"),
        (2, ".10", ".70"),
        (3, ".08", ".70"),
        (4, ".40", ".59"),
        (5, ".40", ".59"),
    ]
    return start, [
        Snapshot(start + timedelta(seconds=seconds), str(seconds), book(yes, no))
        for seconds, yes, no in values
    ]


def test_executable_loss_stop_waits_for_delayed_book():
    start, snapshots = falling_then_recovering_snapshots()
    result = simulate_policy(
        snapshots=snapshots,
        decision_index=0,
        close_time=start + timedelta(minutes=15),
        winning_side="YES",
        tranche_count=3,
        net_loss_stop=Decimal("5"),
    )
    assert result["exit_reason"] == "loss_stop"
    assert result["exit_time"] == (start + timedelta(seconds=3)).isoformat()
    assert result["pnl"] < -5


def test_no_stop_counterfactual_can_recover():
    start, snapshots = falling_then_recovering_snapshots()
    result = simulate_policy(
        snapshots=snapshots,
        decision_index=0,
        close_time=start + timedelta(minutes=15),
        winning_side="YES",
        tranche_count=3,
    )
    assert result["exit_reason"] == "profit_target"
    assert result["profitable"] is True


def test_percentile_uses_observed_lower_tail():
    assert percentile([1.0, -10.0, 3.0, -2.0], 0.25) == -10.0


def test_summary_reports_false_stop_recovery():
    row = {
        "stop_label": "minus_5", "status": "completed", "ticker": "T",
        "pnl": -6.0, "profitable": False, "target_achieved_after_latency": False,
        "loss_stop_executed": True, "baseline_profitable": True,
        "pnl_delta_vs_no_stop": -7.0, "total_fees": 2.0, "budget_utilization": 0.5,
    }
    # Include minimal rows for every frozen stop so the summary remains well formed.
    rows = [row]
    for label in ("no_stop", "minus_10", "minus_15", "minus_20"):
        rows.append({**row, "stop_label": label, "loss_stop_executed": False})
    summary = summarize_stop_rows(rows)
    minus_five = next(item for item in summary if item["stop_label"] == "minus_5")
    assert minus_five["stopped_then_baseline_recovered_rate"] == 1.0

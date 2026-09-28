from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot, simulate_policy
from analyze_kxbtc15m_recovery_stop import policy_label, summarize
from audit_kxbtc15m_raw_depth import ParsedBook


def book(yes_bid: str, no_bid: str) -> ParsedBook:
    return ParsedBook(
        ((Decimal(yes_bid), Decimal("10000")),),
        ((Decimal(no_bid), Decimal("10000")),),
    )


def snapshots(values):
    start = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    return start, [
        Snapshot(start + timedelta(seconds=second), str(second), book(yes, no))
        for second, yes, no in values
    ]


def test_grace_delays_stop_from_latest_fill():
    start, values = snapshots([
        (0, ".20", ".70"), (1, ".20", ".70"),
        (2, ".08", ".76"), (3, ".08", ".76"),
        (4, ".08", ".76"), (11, ".08", ".76"),
        (12, ".08", ".76"), (13, ".08", ".76"),
        (14, ".08", ".76"),
    ])
    result = simulate_policy(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(minutes=15),
        winning_side="NO",
        tranche_count=3,
        net_loss_stop=Decimal("5"),
        loss_stop_grace_seconds=10,
        loss_stop_confirmation_seconds=2,
        additions_before_stop=True,
    )
    # Addition fills at t=3, so grace arms at t=13; confirmation then needs t=15,
    # which is absent. The position cannot stop at the earlier t=11/t=12 books.
    assert result["loss_stop_executed"] is False


def test_two_second_confirmation_and_one_second_execution():
    start, values = snapshots([
        (0, ".20", ".70"), (1, ".20", ".70"),
        (2, ".08", ".70"), (3, ".08", ".70"),
        (4, ".08", ".70"), (5, ".08", ".70"),
    ])
    result = simulate_policy(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(minutes=15),
        winning_side="NO",
        tranche_count=1,
        net_loss_stop=Decimal("5"),
        loss_stop_confirmation_seconds=2,
    )
    assert result["exit_reason"] == "loss_stop"
    assert result["exit_time"] == (start + timedelta(seconds=5)).isoformat()


def test_addition_precedes_stop_and_resets_clock():
    start, values = snapshots([
        (0, ".20", ".70"), (1, ".20", ".70"),
        (2, ".08", ".76"), (3, ".08", ".76"),
        (4, ".40", ".59"), (5, ".40", ".59"),
    ])
    result = simulate_policy(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(minutes=15),
        winning_side="YES",
        tranche_count=3,
        net_loss_stop=Decimal("5"),
        loss_stop_grace_seconds=10,
        loss_stop_confirmation_seconds=2,
        additions_before_stop=True,
    )
    assert result["tranches_filled"] >= 2
    assert result["exit_reason"] == "profit_target"


def test_policy_labels_are_stable():
    assert policy_label(None, None) == "no_stop"
    assert policy_label(20.0, Decimal("10")) == "grace_20s_stop_10"


def test_summary_reports_all_seven_policies():
    base = {
        "status": "completed", "ticker": "T", "pnl": -1.0,
        "profitable": False, "target_achieved_after_latency": False,
        "loss_stop_executed": False, "baseline_profitable": False,
        "pnl_delta_vs_no_stop": 0.0, "total_fees": 1.0,
    }
    labels = ["no_stop"] + [
        f"grace_{grace}s_stop_{stop}"
        for grace in (10, 20, 30) for stop in (5, 10)
    ]
    rows = [{**base, "policy_label": label} for label in labels]
    assert len(summarize(rows)) == 7

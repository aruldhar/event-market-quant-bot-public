from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_bounded_reentry import (
    find_strict_reentry,
    simulate_market_policies,
    summarize,
    verify_baseline_rows,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
OPEN = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
CLOSE = OPEN + timedelta(seconds=900)
TICKER = "KXBTC15M-26AUG131515-15"


def book(yes_bid: str, yes_ask: str) -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal("1000")),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal("1000")),),
    )


def snapshot(elapsed: float, yes_bid: str, yes_ask: str) -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask),
    )


def two_cycle_path():
    return [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(610.0, "0.98", "0.99"),
        snapshot(611.1, "0.98", "0.99"),
        snapshot(620.0, "0.98", "0.99"),
        snapshot(625.0, "0.90", "0.92"),
        snapshot(626.1, "0.90", "0.92"),
        snapshot(630.0, "0.98", "0.99"),
        snapshot(631.1, "0.98", "0.99"),
    ]


def test_strict_reentry_requires_outside_then_fresh_same_side_band_entry():
    snapshots = two_cycle_path()
    context, diagnostics = find_strict_reentry(
        snapshots=snapshots,
        close_time=CLOSE,
        first_exit_time=snapshots[3].observed_at,
        original_side="YES",
    )
    assert diagnostics["reentry_search_available"] is True
    assert diagnostics["reentry_armed_after_outside_band"] is True
    assert diagnostics["reentry_signal_seen"] is True
    assert context is not None
    assert context[0] == 5
    assert context[1] == 6


def test_already_in_band_after_exit_does_not_trigger_reentry():
    snapshots = [
        snapshot(620.0, "0.90", "0.92"),
        snapshot(625.0, "0.91", "0.93"),
        snapshot(626.1, "0.91", "0.93"),
    ]
    context, diagnostics = find_strict_reentry(
        snapshots=snapshots,
        close_time=CLOSE,
        first_exit_time=OPEN + timedelta(seconds=611),
        original_side="YES",
    )
    assert context is None
    assert diagnostics["reentry_armed_after_outside_band"] is False
    assert diagnostics["reentry_signal_seen"] is False


def test_delayed_reentry_fill_must_precede_four_minute_cutoff():
    snapshots = [
        snapshot(650.0, "0.98", "0.99"),
        snapshot(659.5, "0.90", "0.92"),
        snapshot(660.6, "0.90", "0.92"),
    ]
    context, diagnostics = find_strict_reentry(
        snapshots=snapshots,
        close_time=CLOSE,
        first_exit_time=OPEN + timedelta(seconds=640),
        original_side="YES",
    )
    assert context is None
    assert diagnostics["reentry_signal_seen"] is True
    assert diagnostics["reentry_rejected_after_cutoff"] is True


def test_two_cycles_never_overlap_and_do_not_compound_budget():
    rows, first = simulate_market_policies(
        snapshots=two_cycle_path(),
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        segment="earlier_64",
    )
    baseline, reentry = rows
    assert first["exit_reason"] == "protected_profit_target"
    assert reentry["status"] == "completed_two_cycles"
    assert reentry["second_cycle_completed"] is True
    assert reentry["profit_compounded"] is False
    assert Decimal(reentry["second_cash_deployed"]) <= Decimal("100")
    assert reentry["second_entry_execution_time"] > first["exit_execution_time"]
    assert Decimal(reentry["total_pnl"]) == (
        Decimal(reentry["first_cycle_pnl"]) + Decimal(reentry["second_cycle_pnl"])
    )
    verify_baseline_rows(rows)


def test_summary_reports_incremental_second_cycle_pnl():
    rows = []
    for ticker, second in ((TICKER, True), ("KXBTC15M-26AUG131530-30", False)):
        baseline = {
            "ticker": ticker,
            "diagnostic_segment": "earlier_64",
            "policy": "single_cycle_baseline",
            "first_cycle_completed": True,
            "second_cycle_completed": False,
            "total_pnl": "4",
        }
        reentry = {
            **baseline,
            "policy": "one_strict_bounded_reentry",
            "second_cycle_completed": second,
            "second_cycle_pnl": "2" if second else "",
            "second_cycle_profitable": True if second else "",
            "second_cycle_full_capital_loss": False if second else "",
            "total_pnl": "6" if second else "4",
            "reentry_search_available": True,
            "reentry_armed_after_outside_band": second,
            "reentry_signal_seen": second,
        }
        rows.extend((baseline, reentry))
    verify_baseline_rows(rows)
    result = summarize(rows)
    policy = next(
        row for row in result
        if row["segment"] == "all_96"
        and row["policy"] == "one_strict_bounded_reentry"
    )
    assert policy["second_entries"] == 1
    assert policy["mean_incremental_pnl_vs_single_cycle"] == 1
    assert policy["mean_second_cycle_pnl"] == 2

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_frequency import TARGET_FRACTION
from analyze_kxbtc15m_h3_native_exit_policies import find_native_entry, simulate_policy
from analyze_kxbtc15m_h3_native_target_protection import (
    normalize_protected,
    simulate_unprotected,
    summarize,
    verify_matched_entries,
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


def policies(snapshots):
    context = find_native_entry(snapshots, CLOSE)
    unprotected = simulate_unprotected(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        segment="earlier_64",
        entry_context=context,
    )
    protected = normalize_protected(simulate_policy(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        segment="earlier_64",
        policy="protected_50pct_max",
        kind="fraction",
        value=TARGET_FRACTION,
        entry_context=context,
    ))
    return unprotected, protected


def test_unprotected_sells_after_slippage_while_protected_keeps_monitoring():
    snapshots = [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(602.0, "0.98", "0.99"),
        snapshot(603.1, "0.93", "0.94"),
        snapshot(604.0, "0.98", "0.99"),
        snapshot(605.1, "0.98", "0.99"),
    ]
    unprotected, protected = policies(snapshots)
    verify_matched_entries(unprotected, protected)
    assert unprotected["exit_execution_time"] == snapshots[3].observed_at.isoformat()
    assert unprotected["target_achieved_after_latency"] is False
    assert Decimal(unprotected["pnl"]) < Decimal(unprotected["target_amount"])
    assert protected["exit_execution_time"] == snapshots[5].observed_at.isoformat()
    assert protected["target_achieved_after_latency"] is True
    assert Decimal(protected["pnl"]) >= Decimal(protected["target_amount"])


def test_modes_are_identical_when_delayed_target_still_holds():
    snapshots = [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(602.0, "0.98", "0.99"),
        snapshot(603.1, "0.98", "0.99"),
    ]
    unprotected, protected = policies(snapshots)
    assert unprotected["pnl"] == protected["pnl"]
    assert unprotected["exit_execution_time"] == protected["exit_execution_time"]
    assert unprotected["target_achieved_after_latency"] is True


def test_no_trigger_rows_remain_matched():
    snapshots = [
        snapshot(600.0, "0.80", "0.82"),
        snapshot(659.9, "0.80", "0.82"),
    ]
    unprotected, protected = policies(snapshots)
    verify_matched_entries(unprotected, protected)
    assert unprotected["status"] == protected["status"] == "no_trigger"


def test_summary_pairs_protection_modes_and_counts_no_trade_as_zero():
    rows = []
    for ticker, filled in ((TICKER, True), ("KXBTC15M-26AUG131530-30", False)):
        for policy, pnl in (("unprotected_50pct_max", "2"), ("protected_50pct_max", "4")):
            row = {
                "ticker": ticker,
                "diagnostic_segment": "earlier_64",
                "exit_policy": policy,
                "status": "completed" if filled else "no_trigger",
                "triggered": filled,
                "pnl": pnl if filled else "",
            }
            if filled:
                row.update({
                    "profitable": True,
                    "target_filled": True,
                    "target_achieved_after_latency": policy == "protected_50pct_max",
                    "fallback_used": False,
                    "exit_reason": (
                        "protected_profit_target" if policy == "protected_50pct_max"
                        else "unprotected_profit_target_signal"
                    ),
                    "full_capital_loss": False,
                    "exposure_seconds": "20",
                })
            rows.append(row)
    result = summarize(rows)
    unprotected = next(
        row for row in result
        if row["segment"] == "all_96"
        and row["exit_policy"] == "unprotected_50pct_max"
    )
    assert unprotected["mean_pnl_per_eligible_market"] == 1
    assert unprotected["mean_paired_difference_vs_protected"] == -1
    assert unprotected["unprotected_below_target_exit_rate"] == 1

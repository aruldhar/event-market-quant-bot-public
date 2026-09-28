from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_frequency import simulate_market as simulate_frequency_market
from analyze_kxbtc15m_h3_time_windows import (
    coverage_rate,
    native_points,
    simulate_window,
    summarize,
    verify_frequency_baseline,
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


def snapshot(elapsed: float, yes_bid: str = "0.98", yes_ask: str = "0.99") -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask),
    )


def simulate(snapshots, scenario, start, end):
    return simulate_window(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        scenario=scenario,
        start_seconds=start,
        end_seconds=end,
        segment="earlier_64",
    )


def test_native_windows_are_disjoint_at_boundaries():
    snapshots = [snapshot(elapsed) for elapsed in (0, 299.9, 300, 449.9, 450, 599.9, 600, 659.9, 660)]
    assert native_points(snapshots, CLOSE, 900, 600) == [0, 1]
    assert native_points(snapshots, CLOSE, 600, 450) == [2, 3]
    assert native_points(snapshots, CLOSE, 450, 300) == [4, 5]
    assert native_points(snapshots, CLOSE, 300, 240) == [6, 7]


def test_coverage_reports_missing_first_fifteen_seconds():
    snapshots = [snapshot(15), snapshot(899)]
    assert coverage_rate(snapshots, CLOSE, 900, 600) == pytest.approx(285 / 300)
    assert coverage_rate(snapshots, CLOSE, 600, 450) == 1.0


def test_expanded_policy_uses_earliest_trigger_while_4_5m_uses_later_trigger():
    snapshots = [
        snapshot(10, "0.98", "0.99"),
        snapshot(100, "0.97", "0.98"),
        snapshot(101, "0.97", "0.98"),
        snapshot(102, "0.99", "1.00"),
        snapshot(103, "0.99", "1.00"),
        snapshot(610, "0.97", "0.98"),
        snapshot(611, "0.97", "0.98"),
        snapshot(612, "0.99", "1.00"),
        snapshot(613, "0.99", "1.00"),
    ]
    expanded = simulate(snapshots, "expanded_first_240_900s", 900, 240)
    baseline = simulate(snapshots, "04_240_300s", 300, 240)
    assert expanded["status"] == "completed"
    assert baseline["status"] == "completed"
    assert expanded["decision_time"] == (OPEN + timedelta(seconds=100)).isoformat()
    assert baseline["decision_time"] == (OPEN + timedelta(seconds=610)).isoformat()


def test_4_5m_window_exactly_reproduces_frequency_native_scenario():
    snapshots = [
        snapshot(600, "0.98", "0.99"),
        snapshot(601, "0.97", "0.98"),
        snapshot(602, "0.97", "0.98"),
        snapshot(603, "0.99", "1.00"),
        snapshot(604, "0.99", "1.00"),
    ]
    window = simulate(snapshots, "04_240_300s", 300, 240)
    frequency = simulate_frequency_market(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        frequency="native",
        entry_mode="unprotected",
        clock_basis="causal_response_receipt",
        diagnostic_segment="earlier_64",
    )
    verify_frequency_baseline(window, frequency)


def test_summary_paired_difference_counts_no_trade_as_zero():
    baseline = {
        "ticker": TICKER,
        "diagnostic_segment": "earlier_64",
        "scenario": "04_240_300s",
        "window_start_seconds_remaining": 300,
        "window_end_seconds_remaining_exclusive": 240,
        "window_coverage_rate": "1",
        "status": "completed",
        "triggered": True,
        "pnl": "2",
        "profitable": True,
        "target_filled": True,
        "fallback_used": False,
        "favored_side_won": True,
        "full_capital_loss": False,
        "seconds_remaining": "280",
        "entry_average_price": "0.95",
    }
    rows = []
    scenarios = (
        "04_240_300s", "05_300_450s", "06_450_600s",
        "07_600_900s", "expanded_first_240_900s",
    )
    for scenario in scenarios:
        row = dict(baseline)
        row["scenario"] = scenario
        if scenario == "05_300_450s":
            row.update({"status": "no_trigger", "triggered": False, "pnl": ""})
        rows.append(row)
    result = summarize(rows)
    earlier = next(
        row for row in result
        if row["segment"] == "all_96" and row["scenario"] == "05_300_450s"
    )
    assert earlier["mean_pnl_per_eligible_market"] == 0
    assert earlier["mean_paired_difference_vs_4_5m_per_market"] == -2

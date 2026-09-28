from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_frequency import simulate_market as simulate_frequency_market
from analyze_kxbtc15m_h3_last_five_minutes import (
    BASELINE,
    EXPANDED,
    WINDOWS,
    scenario_names,
    summarize,
)
from analyze_kxbtc15m_h3_time_windows import (
    native_points,
    simulate_window,
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


def snapshot(
    elapsed: float, yes_bid: str = "0.98", yes_ask: str = "0.99"
) -> Snapshot:
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
        entry_deadline_seconds_before_close=10,
    )


def test_final_five_minute_windows_are_disjoint_and_stop_at_ten_seconds():
    elapsed = (599.9, 600, 659.9, 660, 719.9, 720, 779.9, 780, 839.9, 840, 889.9, 890)
    snapshots = [snapshot(value) for value in elapsed]
    points = [
        native_points(snapshots, CLOSE, start, end)
        for _name, _label, start, end in WINDOWS
    ]
    assert points == [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]
    assert all(11 not in indices for indices in points)


def test_delayed_entry_at_or_after_preclose_cutoff_is_rejected():
    snapshots = [
        snapshot(889.2, "0.97", "0.98"),
        snapshot(890.3, "0.97", "0.98"),
        snapshot(891.0, "0.99", "1.00"),
    ]
    row = simulate(snapshots, "00_010_060s", 60, 10)
    assert row["triggered"] is True
    assert row["entry_filled"] is False
    assert row["status"] == "entry_after_preclose_cutoff"
    assert row["pnl"] == ""


def test_expanded_policy_preserves_4_5m_trigger_before_later_trigger():
    snapshots = [
        snapshot(610, "0.97", "0.98"),
        snapshot(611, "0.97", "0.98"),
        snapshot(612, "0.99", "1.00"),
        snapshot(700, "0.97", "0.98"),
        snapshot(701, "0.97", "0.98"),
        snapshot(702, "0.99", "1.00"),
    ]
    baseline = simulate(snapshots, BASELINE, 300, 240)
    expanded = simulate(snapshots, EXPANDED[0], 300, 10)
    assert baseline["status"] == "completed"
    assert expanded["status"] == "completed"
    assert expanded["decision_time"] == baseline["decision_time"]
    assert expanded["pnl"] == baseline["pnl"]


def test_4_5m_row_reproduces_native_frequency_baseline():
    snapshots = [
        snapshot(600, "0.98", "0.99"),
        snapshot(601, "0.97", "0.98"),
        snapshot(602, "0.97", "0.98"),
        snapshot(603, "0.99", "1.00"),
        snapshot(604, "0.99", "1.00"),
    ]
    window = simulate(snapshots, BASELINE, 300, 240)
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


def test_summary_reports_incremental_expanded_fill_and_counts_no_trade_as_zero():
    rows = []
    for scenario in scenario_names():
        row = {
            "ticker": TICKER,
            "diagnostic_segment": "earlier_64",
            "scenario": scenario,
            "window_start_seconds_remaining": 300,
            "window_end_seconds_remaining_exclusive": 10,
            "window_coverage_rate": "1",
            "status": "no_trigger",
            "triggered": False,
            "pnl": "",
        }
        if scenario == EXPANDED[0]:
            row.update({
                "status": "completed",
                "triggered": True,
                "pnl": "2",
                "profitable": True,
                "target_filled": True,
                "fallback_used": False,
                "favored_side_won": True,
                "full_capital_loss": False,
                "seconds_remaining": "150",
                "entry_average_price": "0.95",
            })
        rows.append(row)
    result = summarize(rows)
    expanded = next(
        row for row in result
        if row["segment"] == "all_96" and row["scenario"] == EXPANDED[0]
    )
    baseline = next(
        row for row in result
        if row["segment"] == "all_96" and row["scenario"] == BASELINE
    )
    assert expanded["additional_filled_markets_vs_4_5m"] == 1
    assert expanded["mean_pnl_per_eligible_market"] == 2
    assert expanded["mean_paired_difference_vs_4_5m_per_market"] == 2
    assert baseline["mean_pnl_per_eligible_market"] == 0

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_frequency import simulate_market as simulate_frequency_market
from analyze_kxbtc15m_h3_probability_bands import (
    BASELINE,
    SCENARIOS,
    summarize,
)
from analyze_kxbtc15m_h3_time_windows import (
    TimeWindowError,
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
    elapsed: float, yes_bid: str = "0.90", yes_ask: str = "0.92"
) -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask),
    )


def simulate(snapshots, scenario, low, high):
    return simulate_window(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="YES",
        ticker=TICKER,
        scenario=scenario,
        start_seconds=300,
        end_seconds=240,
        segment="earlier_64",
        band_low=Decimal(low),
        band_high_exclusive=Decimal(high),
    )


@pytest.mark.parametrize(
    "midpoint,expected_scenario",
    (("0.85", "band_080_090"), ("0.90", "band_090_095"), ("0.95", "band_095_098")),
)
def test_probability_band_boundaries_are_half_open(midpoint, expected_scenario):
    mid = Decimal(midpoint)
    snapshots = [
        snapshot(601, format(mid - Decimal("0.005"), "f"), format(mid + Decimal("0.005"), "f")),
        snapshot(602, format(mid - Decimal("0.005"), "f"), format(mid + Decimal("0.005"), "f")),
        snapshot(603, "0.99", "1.00"),
        snapshot(604, "0.99", "1.00"),
    ]
    statuses = {}
    for scenario, _label, low, high in SCENARIOS[1:]:
        statuses[scenario] = simulate(
            snapshots, scenario, format(low, "f"), format(high, "f")
        )["status"]
    assert statuses[expected_scenario] == "completed"
    assert sum(status == "completed" for status in statuses.values()) == 1


def test_generic_band_origin_identifies_below_band_transition():
    snapshots = [
        snapshot(600, "0.78", "0.80"),
        snapshot(601, "0.84", "0.86"),
        snapshot(602, "0.84", "0.86"),
        snapshot(603, "0.99", "1.00"),
        snapshot(604, "0.99", "1.00"),
    ]
    row = simulate(snapshots, "band_080_090", "0.80", "0.90")
    assert row["status"] == "completed"
    assert row["signal_origin"] == "below_band_to_band"


def test_invalid_probability_band_fails_closed():
    with pytest.raises(TimeWindowError):
        simulate([snapshot(601)], "invalid", "0.95", "0.90")


def test_combined_90_98_row_reproduces_native_frequency_baseline():
    snapshots = [
        snapshot(600, "0.98", "0.99"),
        snapshot(601, "0.97", "0.98"),
        snapshot(602, "0.97", "0.98"),
        snapshot(603, "0.99", "1.00"),
        snapshot(604, "0.99", "1.00"),
    ]
    baseline = simulate(snapshots, BASELINE, "0.90", "0.98")
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
    verify_frequency_baseline(baseline, frequency)


def test_summary_reports_band_overlap_new_and_missed_markets():
    second_ticker = "KXBTC15M-26AUG131530-30"
    rows = []
    for ticker in (TICKER, second_ticker):
        for scenario, _label, _low, _high in SCENARIOS:
            completed = (
                (scenario == BASELINE and ticker == TICKER)
                or (scenario == "band_080_090" and ticker == second_ticker)
            )
            row = {
                "ticker": ticker,
                "diagnostic_segment": "earlier_64",
                "scenario": scenario,
                "window_coverage_rate": "1",
                "status": "completed" if completed else "no_trigger",
                "triggered": completed,
                "pnl": "2" if completed else "",
            }
            if completed:
                row.update({
                    "profitable": True,
                    "target_filled": True,
                    "fallback_used": False,
                    "favored_side_won": True,
                    "full_capital_loss": False,
                    "seconds_remaining": "280",
                    "entry_average_price": "0.85",
                    "maximum_settlement_profit": "15",
                })
            rows.append(row)
    result = summarize(rows)
    band = next(
        row for row in result
        if row["segment"] == "all_96" and row["scenario"] == "band_080_090"
    )
    assert band["overlap_filled_with_90_98"] == 0
    assert band["new_filled_vs_90_98"] == 1
    assert band["missed_filled_vs_90_98"] == 1
    assert band["mean_pnl_per_eligible_market"] == 1
    assert band["mean_paired_difference_vs_90_98_per_market"] == 0

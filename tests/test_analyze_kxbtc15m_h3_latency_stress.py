from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_latency_stress import (
    LatencyStressError,
    find_preclose_exit,
    find_protected_target_exit,
    scenario_grid,
    scenario_name,
    verify_one_second_reproduction,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
BASE = datetime(2026, 8, 13, tzinfo=UTC)


def snapshot(second: int, yes_bid: str, quantity: str = "1000") -> Snapshot:
    return Snapshot(
        observed_at=BASE + timedelta(seconds=second),
        request_id=str(second),
        book=ParsedBook(
            yes_levels=((Decimal(yes_bid), Decimal(quantity)),),
            no_levels=((Decimal("0.02"), Decimal("1000")),),
        ),
    )


def protected(snapshots, latency):
    return find_protected_target_exit(
        snapshots=snapshots,
        start_index=0,
        stop_time=BASE + timedelta(seconds=20),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target=Decimal("1"),
        latency_seconds=latency,
    )


def test_scenario_grid_has_eight_unique_matched_settings():
    grid = scenario_grid()
    assert len(grid) == 8
    assert len({row[0] for row in grid}) == 8
    assert ("combined_5s", "combined", 5.0, 5.0) in grid
    assert ("exit_only_5s", "exit_only", 1.0, 5.0) in grid


def test_scenario_name_rejects_unplanned_search_values():
    with pytest.raises(LatencyStressError):
        scenario_name("combined", 4.0)
    with pytest.raises(LatencyStressError):
        scenario_name("entry_only", 1.0)


def test_two_second_target_fill_uses_first_snapshot_at_or_after_delay():
    execution, when, signal, signals, rejected = protected([
        snapshot(0, "0.97"), snapshot(1, "0.97"), snapshot(2, "0.97")
    ], 2.0)
    assert execution is not None
    assert signal == BASE
    assert when == BASE + timedelta(seconds=2)
    assert signals == 1
    assert rejected == 0


def test_rejected_attempt_gets_a_new_full_delay_before_retry_fill():
    execution, when, signal, signals, rejected = protected([
        snapshot(0, "0.97"),
        snapshot(1, "0.97"),
        snapshot(2, "0.94"),
        snapshot(3, "0.97"),
        snapshot(4, "0.97"),
        snapshot(5, "0.97"),
    ], 2.0)
    assert execution is not None
    assert signal == BASE + timedelta(seconds=3)
    assert when == BASE + timedelta(seconds=5)
    assert signals == 2
    assert rejected == 1


def test_preclose_exit_uses_configured_delay_and_requires_full_depth():
    execution, when, signal = find_preclose_exit(
        snapshots=[
            snapshot(10, "0.95"),
            snapshot(12, "0.95", quantity="50"),
            snapshot(13, "0.95"),
            snapshot(15, "0.95"),
        ],
        start_index=0,
        start_time=BASE + timedelta(seconds=10),
        close_time=BASE + timedelta(seconds=20),
        side="YES",
        quantity=Decimal("100"),
        latency_seconds=2.0,
    )
    assert execution is not None
    assert signal == BASE + timedelta(seconds=13)
    assert when == BASE + timedelta(seconds=15)


def test_nonpositive_latency_fails_closed():
    with pytest.raises(LatencyStressError):
        protected([snapshot(0, "0.97")], 0.0)


def test_one_second_reproduction_checks_both_stress_modes():
    baseline = {"A": 1.25, "B": 2.50}
    rows = [
        {"ticker": ticker, "scenario": scenario_name(mode, 1.0), "pnl": pnl}
        for mode in ("combined", "exit_only")
        for ticker, pnl in baseline.items()
    ]
    verify_one_second_reproduction(baseline, rows)


def test_one_second_reproduction_rejects_economic_drift():
    baseline = {"A": 1.25}
    rows = [
        {"ticker": "A", "scenario": "combined_1s", "pnl": 1.25},
        {"ticker": "A", "scenario": "exit_only_1s", "pnl": 1.24},
    ]
    with pytest.raises(LatencyStressError):
        verify_one_second_reproduction(baseline, rows)

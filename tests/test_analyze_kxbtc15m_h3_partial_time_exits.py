from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_partial_time_exits import (
    BASELINE_KEY,
    CASHOUT_FRACTIONS,
    FULL_90_KEY,
    POLICIES,
    TIMEOUT_SECONDS,
    cumulative_pnl,
    execute_tranche,
    mark_pareto_frontier,
    tranche_quantity,
)
from audit_kxbtc15m_raw_depth import ParsedBook


START = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def book(*, bid: str, quantity: str = "1000") -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(bid), Decimal(quantity)),),
        no_levels=((Decimal("0.05"), Decimal("1000")),),
    )


def snapshot(seconds: float, *, bid: str, quantity: str = "1000") -> Snapshot:
    return Snapshot(
        START + timedelta(seconds=seconds),
        f"r-{seconds}",
        book(bid=bid, quantity=quantity),
    )


def test_surface_is_three_times_four_plus_original() -> None:
    assert TIMEOUT_SECONDS == (75, 90, 105)
    assert CASHOUT_FRACTIONS == (
        Decimal("0.25"), Decimal("0.50"),
        Decimal("0.75"), Decimal("1.00"),
    )
    assert len(POLICIES) == 13
    assert POLICIES[0].key == BASELINE_KEY
    assert any(policy.key == FULL_90_KEY for policy in POLICIES)
    assert len({policy.key for policy in POLICIES}) == len(POLICIES)


def test_tranche_quantity_rounds_up_to_whole_contracts() -> None:
    assert tranche_quantity(Decimal("101"), Decimal("0.25")) == Decimal("26")
    assert tranche_quantity(Decimal("101"), Decimal("0.50")) == Decimal("51")
    assert tranche_quantity(Decimal("101"), Decimal("1.00")) == Decimal("101")


def test_cumulative_target_includes_realized_partial_loss() -> None:
    pnl = cumulative_pnl(
        realized_net_inflow=Decimal("30"),
        remaining_net_inflow=Decimal("72"),
        original_outflow=Decimal("100"),
    )
    assert pnl == Decimal("2")
    assert cumulative_pnl(
        realized_net_inflow=Decimal("20"),
        remaining_net_inflow=Decimal("72"),
        original_outflow=Decimal("100"),
    ) == Decimal("-8")


def test_execute_tranche_waits_one_second_and_sells_across_attempts() -> None:
    snapshots = [
        snapshot(0.0, bid="0.80", quantity="1000"),
        snapshot(1.1, bid="0.80", quantity="4"),
        snapshot(1.2, bid="0.80", quantity="0"),
        snapshot(2.3, bid="0.75", quantity="6"),
    ]
    result = execute_tranche(
        snapshots=snapshots,
        signal_index=0,
        close_time=START + timedelta(seconds=10),
        side="YES",
        quantity=Decimal("10"),
    )
    assert result.attempts == 2
    assert result.fill_events == 2
    assert result.quantity_sold == Decimal("10")
    assert result.fully_sold is True
    assert result.first_execution_time == START + timedelta(seconds=1.1)
    assert result.last_execution_time == START + timedelta(seconds=2.3)
    assert result.next_index == 4
    assert result.net_inflow < result.gross


def test_pareto_frontier_uses_total_pnl_and_worst_loss() -> None:
    rows = [
        {
            "group": "combined_122",
            "partial_time_policy": "high_return_bad_tail",
            "total_pnl": 180.0,
            "worst_pnl_per_filled_entry": -100.0,
            "pareto_frontier_total_vs_worst": False,
        },
        {
            "group": "combined_122",
            "partial_time_policy": "balanced",
            "total_pnl": 170.0,
            "worst_pnl_per_filled_entry": -60.0,
            "pareto_frontier_total_vs_worst": False,
        },
        {
            "group": "combined_122",
            "partial_time_policy": "dominated",
            "total_pnl": 160.0,
            "worst_pnl_per_filled_entry": -70.0,
            "pareto_frontier_total_vs_worst": False,
        },
    ]
    mark_pareto_frontier(rows)
    assert rows[0]["pareto_frontier_total_vs_worst"] is True
    assert rows[1]["pareto_frontier_total_vs_worst"] is True
    assert rows[2]["pareto_frontier_total_vs_worst"] is False

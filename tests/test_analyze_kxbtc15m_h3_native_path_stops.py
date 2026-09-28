from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import (
    Snapshot,
    buy_with_budget,
)
from analyze_kxbtc15m_h3_native_path_stops import (
    POLICIES,
    _path_category,
    build_executable_path,
    progressive_liquidation,
    simulate_stop_overlay,
)
from audit_kxbtc15m_raw_depth import ParsedBook


START = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)
CLOSE = START + timedelta(minutes=5)


def book(
    *, yes_bid: str, yes_bid_qty: str = "1000", yes_ask: str = "0.95",
    yes_ask_qty: str = "1000",
) -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal(yes_bid_qty)),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal(yes_ask_qty)),),
    )


def snapshot(seconds: float, value: ParsedBook) -> Snapshot:
    return Snapshot(START + timedelta(seconds=seconds), f"r-{seconds}", value)


def entry_context(snapshots: list[Snapshot]):
    entry = buy_with_budget(snapshots[0].book.ask_levels("YES"), Decimal("100"))
    assert entry.quantity > 0
    return 0, 0, "YES", Decimal("0.95"), Decimal("0.95"), entry


def test_path_category_boundaries() -> None:
    assert _path_category(None) == "no_full_depth_mark"
    assert _path_category(0) == "never_negative"
    assert _path_category(-1.99) == "dip_0_to_2"
    assert _path_category(-2) == "dip_2_to_5"
    assert _path_category(-7) == "dip_5_to_10"
    assert _path_category(-15) == "dip_10_to_20"
    assert _path_category(-20) == "dip_20_or_more"


def test_build_path_detects_dip_and_recovery() -> None:
    snapshots = [
        snapshot(0, book(yes_bid="0.94")),
        snapshot(2, book(yes_bid="0.93")),
        snapshot(4, book(yes_bid="0.90")),
        snapshot(6, book(yes_bid="0.99")),
    ]
    context = entry_context(snapshots)
    baseline = {
        "exit_execution_time": snapshots[-1].observed_at.isoformat(),
        "pnl": "3.50",
    }

    points, row = build_executable_path(
        snapshots=snapshots,
        close_time=CLOSE,
        ticker="T",
        segment="earlier_64",
        entry_context=context,
        baseline=baseline,
    )

    assert len(points) == 3
    assert row["ever_negative_full_liquidation_pnl"] is True
    assert row["recovered_after_negative_pnl"] is True
    assert row["minimum_full_liquidation_pnl"] < -5
    assert row["path_category"] == "dip_5_to_10"
    assert row["full_mark_path_nondecreasing"] is False


def test_build_path_records_missing_full_depth() -> None:
    snapshots = [
        snapshot(0, book(yes_bid="0.94")),
        snapshot(2, book(yes_bid="0.90", yes_bid_qty="10")),
        snapshot(4, book(yes_bid="0.99")),
    ]
    context = entry_context(snapshots)
    baseline = {
        "exit_execution_time": snapshots[-1].observed_at.isoformat(),
        "pnl": "3.50",
    }

    points, row = build_executable_path(
        snapshots=snapshots,
        close_time=CLOSE,
        ticker="T",
        segment="earlier_64",
        entry_context=context,
        baseline=baseline,
    )

    assert points[0]["full_liquidation_available"] is False
    assert points[0]["full_liquidation_pnl"] == ""
    assert row["ever_full_depth_unavailable"] is True
    assert row["minimum_liquidatable_fraction"] < 1


def test_progressive_liquidation_sells_across_multiple_delayed_attempts() -> None:
    snapshots = [
        snapshot(0.0, book(yes_bid="0.80", yes_bid_qty="0")),
        snapshot(1.1, book(yes_bid="0.80", yes_bid_qty="4")),
        snapshot(1.2, book(yes_bid="0.80", yes_bid_qty="0")),
        snapshot(2.3, book(yes_bid="0.75", yes_bid_qty="6")),
    ]

    result = progressive_liquidation(
        snapshots=snapshots,
        signal_index=0,
        close_time=CLOSE,
        side="YES",
        quantity=Decimal("10"),
        outflow=Decimal("9.50"),
        winning_side="NO",
    )

    assert result.attempts == 2
    assert result.fill_events == 2
    assert result.quantity_sold == Decimal("10")
    assert result.remaining_quantity == 0
    assert result.settled_residual is False
    assert result.pnl < 0


def test_progressive_liquidation_marks_losing_residual_at_zero() -> None:
    snapshots = [
        snapshot(0.0, book(yes_bid="0.80", yes_bid_qty="0")),
        snapshot(1.1, book(yes_bid="0.80", yes_bid_qty="4")),
    ]

    result = progressive_liquidation(
        snapshots=snapshots,
        signal_index=0,
        close_time=START + timedelta(seconds=2),
        side="YES",
        quantity=Decimal("10"),
        outflow=Decimal("9.50"),
        winning_side="NO",
    )

    assert result.quantity_sold == Decimal("4")
    assert result.remaining_quantity == Decimal("6")
    assert result.settled_residual is True
    assert result.pnl == result.gross - result.fee - Decimal("9.50")


def test_loss_overlay_triggers_then_uses_progressive_exit() -> None:
    snapshots = [
        snapshot(0.0, book(yes_bid="0.94")),
        snapshot(1.0, book(yes_bid="0.90")),
        snapshot(2.1, book(yes_bid="0.85", yes_bid_qty="50")),
        snapshot(2.2, book(yes_bid="0.84", yes_bid_qty="1000")),
        snapshot(3.3, book(yes_bid="0.84", yes_bid_qty="1000")),
    ]
    context = entry_context(snapshots)
    baseline = {
        "ticker": "T",
        "status": "completed",
        "triggered": True,
        "entry_filled": True,
        "target_filled": True,
        "fallback_used": False,
        "exit_reason": "protected_profit_target",
        "exit_execution_time": (START + timedelta(seconds=10)).isoformat(),
        "pnl": "3.50",
        "profitable": True,
        "full_capital_loss": False,
    }

    row = simulate_stop_overlay(
        snapshots=snapshots,
        close_time=CLOSE,
        winning_side="NO",
        baseline=baseline,
        entry_context=context,
        policy="stop_2usd",
        mode="loss",
        threshold=Decimal("2"),
    )

    assert row["stop_signal"] is True
    assert row["target_filled"] is False
    assert row["progressive_quantity_sold"] != "0"
    assert float(row["pnl"]) < 0


def test_policy_surface_is_bounded_and_contains_liquidity_guard() -> None:
    assert len(POLICIES) == 7
    assert [row[0] for row in POLICIES] == [
        "baseline_no_stop", "stop_2usd", "stop_5usd", "stop_10usd",
        "stop_15usd", "stop_20usd", "liquidity_guard",
    ]

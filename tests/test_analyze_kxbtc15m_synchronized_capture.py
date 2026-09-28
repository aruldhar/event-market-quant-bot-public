from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot, buy_with_budget
from analyze_kxbtc15m_synchronized_capture import (
    ClockCorrection,
    find_h3_decision,
    parse_clock_offsets,
    protected_target_exit,
    validate_lineage_times,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc


def book(*, yes_bid: str, no_bid: str, quantity: str = "1000") -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal(quantity)),),
        no_levels=((Decimal(no_bid), Decimal(quantity)),),
    )


def test_clock_correction_interpolates_positive_reference_minus_local_offset() -> None:
    correction = ClockCorrection(
        first_epoch_ms=1_000,
        last_epoch_ms=3_000,
        before_seconds=0.300,
        after_seconds=0.200,
    )

    assert correction.corrected_epoch_ms(1_000) == 1_300
    assert correction.corrected_epoch_ms(2_000) == 2_250
    assert correction.corrected_epoch_ms(3_000) == 3_200


def test_clock_offsets_accept_windows_powershell_utf16(tmp_path) -> None:
    clock_file = tmp_path / "clock_before.txt"
    clock_file.write_text(
        "Tracking time.windows.com [40.119.6.228:123].\n"
        "14:03:29, +00.3084211s\n"
        "14:03:31, +00.3078345s\n",
        encoding="utf-16",
    )

    assert parse_clock_offsets(clock_file) == [0.3084211, 0.3078345]


def test_lineage_uses_request_id_and_causal_time_order_not_timestamp_equality() -> None:
    observed = datetime(2026, 8, 13, 19, 3, 47, 500000, tzinfo=UTC)
    started = observed + timedelta(milliseconds=12)
    received = started + timedelta(milliseconds=406)

    gap_ms = validate_lineage_times(
        request_id="request-1",
        csv_observed=observed,
        started=started,
        received=received,
    )

    assert gap_ms == 12.0


def test_h3_decision_is_first_qualifying_five_second_anchor() -> None:
    close = datetime(2026, 8, 13, 19, 30, tzinfo=UTC)
    snapshots = [
        Snapshot(close - timedelta(seconds=299.5), "first", book(yes_bid="0.90", no_bid="0.09")),
        Snapshot(close - timedelta(seconds=294.5), "second", book(yes_bid="0.92", no_bid="0.07")),
    ]

    decision = find_h3_decision(snapshots, close)

    assert decision is not None
    index, anchor, lag = decision
    assert index == 0
    assert anchor == close - timedelta(seconds=300)
    assert lag == 0.5


def test_protected_target_rejects_delayed_slippage_then_fills_later() -> None:
    start = datetime(2026, 8, 13, 19, 25, tzinfo=UTC)
    entry_book = book(yes_bid="0.90", no_bid="0.09")
    entry = buy_with_budget(entry_book.ask_levels("YES"), Decimal("100"))
    outflow = entry.buy_outflow
    target = (entry.quantity - outflow) * Decimal("0.50")
    snapshots = [
        Snapshot(start, "entry", entry_book),
        Snapshot(start + timedelta(seconds=1.1), "signal-1", book(yes_bid="0.97", no_bid="0.02")),
        Snapshot(start + timedelta(seconds=2.2), "reject-1", book(yes_bid="0.91", no_bid="0.08")),
        Snapshot(start + timedelta(seconds=3.3), "signal-2", book(yes_bid="0.97", no_bid="0.02")),
        Snapshot(start + timedelta(seconds=4.4), "fill-2", book(yes_bid="0.97", no_bid="0.02")),
    ]

    execution, exit_time, signals, rejected = protected_target_exit(
        snapshots,
        start_index=1,
        stop_time=start + timedelta(seconds=10),
        side="YES",
        quantity=entry.quantity,
        outflow=outflow,
        target=target,
    )

    assert execution is not None
    assert exit_time == start + timedelta(seconds=4.4)
    assert execution.quantity == entry.quantity
    assert execution.sell_inflow - outflow >= target
    assert signals == 2
    assert rejected == 1

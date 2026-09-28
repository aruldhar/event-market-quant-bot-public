from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_exit_policies import (
    CONDITIONAL_BID_THRESHOLDS,
    PERCENTAGE_TARGETS,
    ExitPolicyError,
    _find_target_exit,
    percentage_target,
    policy_names,
    preclose_executable_average_bid,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc


def book(*, yes_bid: str, no_bid: str, quantity: str = "1000") -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal(quantity)),),
        no_levels=((Decimal(no_bid), Decimal(quantity)),),
    )


def snap(second: int, *, yes_bid: str, no_bid: str) -> Snapshot:
    return Snapshot(
        observed_at=datetime(2026, 8, 13, tzinfo=UTC) + timedelta(seconds=second),
        request_id=str(second),
        book=book(yes_bid=yes_bid, no_bid=no_bid),
    )


def test_percentage_target_uses_maximum_net_profit():
    assert percentage_target(Decimal("5.00"), Decimal("0.25")) == Decimal("1.2500")
    assert percentage_target(Decimal("5.00"), Decimal("0.75")) == Decimal("3.7500")


def test_percentage_target_rejects_invalid_inputs():
    with pytest.raises(ExitPolicyError):
        percentage_target(Decimal("0"), Decimal("0.25"))
    with pytest.raises(ExitPolicyError):
        percentage_target(Decimal("5"), Decimal("1"))


def test_policy_set_contains_twelve_matched_rules():
    names = policy_names()
    assert len(names) == 12
    assert len(set(names)) == 12
    assert "baseline_1usd_or_preclose" in names
    assert "hold_to_settlement" in names
    assert "target_25pct_max_or_preclose" in names
    assert "target_25pct_max_or_settlement" in names


def test_percentage_and_conditional_grids_are_frozen():
    assert PERCENTAGE_TARGETS == (
        Decimal("0.25"), Decimal("0.50"), Decimal("0.75")
    )
    assert CONDITIONAL_BID_THRESHOLDS == (
        Decimal("0.90"), Decimal("0.95"), Decimal("0.98")
    )


def test_target_requires_delayed_execution_and_can_be_achieved():
    snapshots = [
        snap(0, yes_bid="0.94", no_bid="0.05"),
        snap(1, yes_bid="0.97", no_bid="0.02"),
        snap(2, yes_bid="0.97", no_bid="0.02"),
    ]
    execution, when, signal, achieved, missed = _find_target_exit(
        snapshots=snapshots,
        start_index=1,
        stop_time=datetime(2026, 8, 13, tzinfo=UTC) + timedelta(seconds=10),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target=Decimal("1"),
    )
    assert execution is not None
    assert when == snapshots[2].observed_at
    assert signal and achieved and missed == 0


def test_target_signal_can_disappear_during_latency():
    snapshots = [
        snap(0, yes_bid="0.94", no_bid="0.05"),
        snap(1, yes_bid="0.97", no_bid="0.02"),
        snap(2, yes_bid="0.94", no_bid="0.05"),
    ]
    execution, _, signal, achieved, _ = _find_target_exit(
        snapshots=snapshots,
        start_index=1,
        stop_time=datetime(2026, 8, 13, tzinfo=UTC) + timedelta(seconds=10),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target=Decimal("1"),
    )
    assert execution is not None
    assert signal
    assert not achieved


def test_preclose_reference_uses_full_position_average_bid():
    snapshots = [snap(9, yes_bid="0.96", no_bid="0.03")]
    average, index = preclose_executable_average_bid(
        snapshots=snapshots,
        start_index=0,
        preclose_time=snapshots[0].observed_at,
        side="YES",
        quantity=Decimal("100"),
    )
    assert average == Decimal("0.96")
    assert index == 0


def test_preclose_reference_rejects_partial_liquidity():
    snapshots = [Snapshot(
        observed_at=datetime(2026, 8, 13, tzinfo=UTC),
        request_id="x",
        book=book(yes_bid="0.96", no_bid="0.03", quantity="50"),
    )]
    average, index = preclose_executable_average_bid(
        snapshots=snapshots,
        start_index=0,
        preclose_time=snapshots[0].observed_at,
        side="YES",
        quantity=Decimal("100"),
    )
    assert average is None
    assert index == 0

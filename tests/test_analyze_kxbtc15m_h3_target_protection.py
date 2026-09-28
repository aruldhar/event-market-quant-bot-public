from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_target_protection import (
    find_protected_target_exit,
    policy_name,
    policy_names,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
BASE = datetime(2026, 8, 13, tzinfo=UTC)


def snapshot(second: int, yes_bid: str) -> Snapshot:
    return Snapshot(
        observed_at=BASE + timedelta(seconds=second),
        request_id=str(second),
        book=ParsedBook(
            yes_levels=((Decimal(yes_bid), Decimal("1000")),),
            no_levels=((Decimal("0.02"), Decimal("1000")),),
        ),
    )


def protected(snapshots):
    return find_protected_target_exit(
        snapshots=snapshots,
        start_index=0,
        stop_time=BASE + timedelta(seconds=20),
        side="YES",
        quantity=Decimal("100"),
        outflow=Decimal("95"),
        target=Decimal("1"),
    )


def test_policy_grid_has_twelve_unique_matched_policies():
    names = policy_names()
    assert len(names) == 12
    assert len(set(names)) == 12


def test_policy_name_keeps_mode_target_and_fallback_explicit():
    assert policy_name("protected", Decimal("0.50"), "settlement") == (
        "protected_target_50pct_max_or_settlement"
    )


def test_protected_target_executes_when_target_survives_latency():
    execution, when, signals, rejected = protected([
        snapshot(0, "0.97"), snapshot(1, "0.97")
    ])
    assert execution is not None
    assert when == BASE + timedelta(seconds=1)
    assert signals == 1
    assert rejected == 0


def test_protected_target_rejects_disappearing_signal_then_recovers():
    execution, when, signals, rejected = protected([
        snapshot(0, "0.97"),
        snapshot(1, "0.94"),
        snapshot(2, "0.97"),
        snapshot(3, "0.97"),
    ])
    assert execution is not None
    assert when == BASE + timedelta(seconds=3)
    assert signals == 2
    assert rejected == 1


def test_protected_target_does_not_sell_below_target():
    execution, when, signals, rejected = protected([
        snapshot(0, "0.97"), snapshot(1, "0.94"), snapshot(2, "0.94")
    ])
    assert execution is None
    assert when is None
    assert signals == 1
    assert rejected == 1


def test_no_target_signal_returns_without_rejection():
    execution, when, signals, rejected = protected([
        snapshot(0, "0.94"), snapshot(1, "0.94")
    ])
    assert execution is None
    assert when is None
    assert signals == 0
    assert rejected == 0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_h3_velocity_stops import (
    DROP_RATES,
    FALLBACK_90_KEY,
    LOOKBACK_SECONDS,
    LOSS_FLOORS,
    POLICIES,
    ExecutableMark,
    VelocityPolicy,
    _adjacent,
    calculate_velocity,
    latest_reference_mark,
    mark_neighbor_robustness,
    velocity_trigger,
)


START = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def mark(seconds: float, pnl: str) -> ExecutableMark:
    return ExecutableMark(START + timedelta(seconds=seconds), Decimal(pnl))


def test_surface_has_four_horizons_and_two_fallback_modes() -> None:
    assert LOOKBACK_SECONDS == (5, 10, 20, 30)
    assert len(DROP_RATES) == 3
    assert len(LOSS_FLOORS) == 2
    assert len(POLICIES) == 2 + 4 * 3 * 2 * 2
    assert POLICIES[1].key == FALLBACK_90_KEY


def test_reference_is_latest_mark_at_or_before_irregular_boundary() -> None:
    marks = [mark(0, "0"), mark(7, "-3"), mark(11, "-8")]
    assert latest_reference_mark(marks, START + timedelta(seconds=10)) == marks[1]
    assert latest_reference_mark(marks, START - timedelta(seconds=1)) is None


def test_velocity_uses_actual_elapsed_time() -> None:
    measure = calculate_velocity(
        marks=[mark(0, "-2"), mark(7, "-5"), mark(11, "-7")],
        current_time=START + timedelta(seconds=20),
        current_pnl=Decimal("-15"),
        lookback_seconds=10,
    )
    assert measure is not None
    assert measure.reference_time == START + timedelta(seconds=7)
    assert measure.elapsed_seconds == 13
    assert measure.drop_dollars == Decimal("10")
    assert measure.drop_rate_dollars_per_second == Decimal("10") / Decimal("13")


def test_velocity_requires_both_rate_and_current_loss_floor() -> None:
    policy = VelocityPolicy(
        "v", "v", "velocity_only", 20, Decimal("0.75"), Decimal("10"), False
    )
    fast = calculate_velocity(
        marks=[mark(0, "2")],
        current_time=START + timedelta(seconds=20),
        current_pnl=Decimal("-14"),
        lookback_seconds=20,
    )
    assert fast is not None
    assert velocity_trigger(policy, current_pnl=Decimal("-14"), measure=fast)
    assert not velocity_trigger(policy, current_pnl=Decimal("-9"), measure=fast)
    slow = calculate_velocity(
        marks=[mark(0, "-1")],
        current_time=START + timedelta(seconds=20),
        current_pnl=Decimal("-11"),
        lookback_seconds=20,
    )
    assert slow is not None
    assert not velocity_trigger(policy, current_pnl=Decimal("-11"), measure=slow)


def summary_row(
    *, lookback: int, rate: float, floor: float, fallback: bool,
    passing: bool,
) -> dict:
    return {
        "group": "combined_122",
        "velocity_policy": f"{lookback}-{rate}-{floor}-{fallback}",
        "lookback_seconds": lookback,
        "drop_rate_threshold": rate,
        "loss_floor_dollars": floor,
        "fallback_90_seconds": fallback,
        "basic_velocity_screen": passing,
        "passing_adjacent_neighbors": 0,
        "robust_velocity_screen": False,
    }


def test_adjacency_changes_exactly_one_neighboring_dimension() -> None:
    center = summary_row(lookback=10, rate=0.75, floor=10, fallback=False, passing=True)
    assert _adjacent(
        center, summary_row(lookback=20, rate=0.75, floor=10, fallback=False, passing=True)
    )
    assert _adjacent(
        center, summary_row(lookback=10, rate=1.0, floor=10, fallback=False, passing=True)
    )
    assert _adjacent(
        center, summary_row(lookback=10, rate=0.75, floor=15, fallback=False, passing=True)
    )
    assert not _adjacent(
        center, summary_row(lookback=20, rate=1.0, floor=10, fallback=False, passing=True)
    )
    assert not _adjacent(
        center, summary_row(lookback=10, rate=0.75, floor=10, fallback=True, passing=True)
    )


def test_robust_screen_requires_a_passing_neighbor() -> None:
    rows = [
        summary_row(lookback=10, rate=0.75, floor=10, fallback=False, passing=True),
        summary_row(lookback=20, rate=0.75, floor=10, fallback=False, passing=True),
        summary_row(lookback=30, rate=1.0, floor=15, fallback=False, passing=True),
    ]
    mark_neighbor_robustness(rows)
    assert rows[0]["robust_velocity_screen"] is True
    assert rows[1]["robust_velocity_screen"] is True
    assert rows[2]["robust_velocity_screen"] is False

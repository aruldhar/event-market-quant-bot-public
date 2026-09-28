from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_h3_gated_acceleration_stops import (
    ACCELERATION_INCREASES,
    ACTIVATION_AGES,
    BASELINE_KEY,
    FALLBACK_90_KEY,
    POLICIES,
    AccelerationMeasure,
    GatedPolicy,
    GatedSignalState,
    _adjacent,
    calculate_acceleration,
    gated_signal,
    mark_neighbor_robustness,
)
from analyze_kxbtc15m_h3_velocity_stops import ExecutableMark, VelocityMeasure


START = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def mark(seconds: float, pnl: str) -> ExecutableMark:
    return ExecutableMark(START + timedelta(seconds=seconds), Decimal(pnl))


def velocity(rate: str) -> VelocityMeasure:
    return VelocityMeasure(
        reference_time=START,
        reference_pnl=Decimal("0"),
        elapsed_seconds=20,
        drop_dollars=Decimal(rate) * Decimal("20"),
        drop_rate_dollars_per_second=Decimal(rate),
    )


def acceleration(increase: str) -> AccelerationMeasure:
    return AccelerationMeasure(
        previous_reference_time=START,
        recent_reference_time=START + timedelta(seconds=10),
        previous_adverse_rate=Decimal("0.25"),
        recent_adverse_rate=Decimal("0.25") + Decimal(increase),
        adverse_rate_increase=Decimal(increase),
    )


def test_surface_is_bounded_to_sixteen_candidates_and_two_comparators() -> None:
    assert ACTIVATION_AGES == (45, 60)
    assert ACCELERATION_INCREASES == (Decimal("0.25"), Decimal("0.50"))
    assert len(POLICIES) == 18
    assert POLICIES[0].key == BASELINE_KEY
    assert POLICIES[1].key == FALLBACK_90_KEY
    assert sum(policy.family == "age_persistent_velocity" for policy in POLICIES) == 12
    assert sum(policy.family == "acceleration_confirmed" for policy in POLICIES) == 4


def test_acceleration_uses_nonoverlapping_causal_slopes() -> None:
    result = calculate_acceleration(
        marks=[mark(0, "0"), mark(9, "-1"), mark(19, "-4")],
        current_time=START + timedelta(seconds=30),
        current_pnl=Decimal("-10"),
        window_seconds=10,
    )
    assert result is not None
    assert result.previous_reference_time == START + timedelta(seconds=9)
    assert result.recent_reference_time == START + timedelta(seconds=19)
    assert result.previous_adverse_rate == Decimal("0.3")
    assert result.recent_adverse_rate == Decimal("6") / Decimal("11")
    assert result.adverse_rate_increase == Decimal("6") / Decimal("11") - Decimal("0.3")


def test_age_and_velocity_must_qualify_continuously_for_persistence() -> None:
    policy = GatedPolicy(
        "p", "p", "age_persistent_velocity",
        activation_age_seconds=45,
        drop_rate=Decimal("0.50"),
        persistence_seconds=10,
    )
    state = GatedSignalState()
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=44),
        seconds_since_entry=44,
        current_pnl=Decimal("-20"),
        velocity=velocity("0.75"),
        acceleration=None,
    ) == (False, "")
    assert state.qualifying_since is None
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=45),
        seconds_since_entry=45,
        current_pnl=Decimal("-20"),
        velocity=velocity("0.75"),
        acceleration=None,
    ) == (False, "")
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=50),
        seconds_since_entry=50,
        current_pnl=Decimal("-14"),
        velocity=velocity("0.75"),
        acceleration=None,
    ) == (False, "")
    assert state.qualifying_since is None
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=51),
        seconds_since_entry=51,
        current_pnl=Decimal("-16"),
        velocity=velocity("0.75"),
        acceleration=None,
    ) == (False, "")
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=61),
        seconds_since_entry=61,
        current_pnl=Decimal("-18"),
        velocity=velocity("0.75"),
        acceleration=None,
    ) == (True, "age_persistent_velocity")


def test_acceleration_rule_requires_rate_increase_after_persistence() -> None:
    policy = GatedPolicy(
        "a", "a", "acceleration_confirmed",
        activation_age_seconds=45,
        drop_rate=Decimal("0.50"),
        persistence_seconds=10,
        acceleration_increase=Decimal("0.25"),
    )
    state = GatedSignalState()
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=45),
        seconds_since_entry=45,
        current_pnl=Decimal("-16"),
        velocity=velocity("0.60"),
        acceleration=acceleration("0.50"),
    ) == (False, "")
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=55),
        seconds_since_entry=55,
        current_pnl=Decimal("-18"),
        velocity=velocity("0.60"),
        acceleration=acceleration("0.20"),
    ) == (False, "")
    assert gated_signal(
        policy, state,
        observed_at=START + timedelta(seconds=56),
        seconds_since_entry=56,
        current_pnl=Decimal("-19"),
        velocity=velocity("0.60"),
        acceleration=acceleration("0.25"),
    ) == (True, "acceleration_confirmed_velocity")


def summary(
    *, key: str, family: str, age: int, rate: float = 0.5,
    persistence: int = 10, accel: float | str = "", passing: bool,
) -> dict:
    return {
        "group": "combined_122",
        "gated_policy": key,
        "gated_family": family,
        "activation_age_seconds": age,
        "velocity_threshold": rate,
        "persistence_seconds": persistence,
        "acceleration_threshold": accel,
        "basic_screen": passing,
        "passing_adjacent_neighbors": 0,
        "robust_screen": False,
    }


def test_adjacency_and_robustness_stay_within_candidate_family() -> None:
    first = summary(
        key="p45", family="age_persistent_velocity", age=45,
        persistence=10, passing=True,
    )
    neighbor = summary(
        key="p60", family="age_persistent_velocity", age=60,
        persistence=10, passing=True,
    )
    other_family = summary(
        key="a45", family="acceleration_confirmed", age=45,
        accel=0.25, passing=True,
    )
    assert _adjacent(first, neighbor)
    assert not _adjacent(first, other_family)
    rows = [first, neighbor, other_family]
    mark_neighbor_robustness(rows)
    assert first["robust_screen"] is True
    assert neighbor["robust_screen"] is True
    assert other_family["robust_screen"] is False

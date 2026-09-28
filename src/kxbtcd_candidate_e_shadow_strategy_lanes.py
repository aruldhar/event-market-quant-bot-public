"""Bounded, comparable Candidate-E shadow strategy lanes.

One public-data collector feeds every lane.  A lane changes only the edge
scenario, stop-loss rule, retained-edge profit target, hold-duration cap, or
trailing profit lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .kxbtcd_candidate_e_live_shadow_micro_simulator import (
    DURATION_CAP_MINUTES,
    FROZEN_ATM_FIVE,
    FROZEN_ATM_ONE,
    MOVING_ATM_ELEVEN,
    PROFIT_TARGET_MULTIPLIERS,
    STOP_LOSS_FRACTIONS,
    TRAILING_ACTIVATION_MARGINS,
)
from .kxbtcd_candidate_e_shadow_v2_scenarios import (
    SHADOW_V2_SCENARIOS,
    ShadowV2Scenario,
)


class ShadowStrategyLaneError(ValueError):
    pass


@dataclass(frozen=True)
class ShadowStrategyLane:
    lane_id: str
    policy_id: str
    scenario: ShadowV2Scenario
    stop_loss_fraction: Decimal | None
    profit_target_multiplier: Decimal
    duration_cap_minutes: Decimal | None = None
    trailing_activation_margin: Decimal | None = None


POLICY_IDS = (MOVING_ATM_ELEVEN, FROZEN_ATM_FIVE, FROZEN_ATM_ONE)


def _lane_id(
    *, policy_id: str, scenario_id: str, stop_loss_fraction: Decimal | None,
    profit_target_multiplier: Decimal,
    duration_cap_minutes: Decimal | None,
    trailing_activation_margin: Decimal | None,
) -> str:
    stop = "none" if stop_loss_fraction is None else format(stop_loss_fraction, "f")
    target = format(profit_target_multiplier, "f")
    durcap = "none" if duration_cap_minutes is None else format(duration_cap_minutes, "f")
    trail = "none" if trailing_activation_margin is None else format(trailing_activation_margin, "f")
    return (
        f"{policy_id}:{scenario_id}:stop={stop}:target={target}"
        f":durcap={durcap}:trail={trail}"
    )


def _lane(
    *, policy_id: str, scenario: ShadowV2Scenario,
    stop_loss_fraction: Decimal | None = None,
    profit_target_multiplier: Decimal = Decimal("1.00"),
    duration_cap_minutes: Decimal | None = None,
    trailing_activation_margin: Decimal | None = None,
) -> ShadowStrategyLane:
    if policy_id not in POLICY_IDS:
        raise ShadowStrategyLaneError("strategy lane policy is invalid")
    if stop_loss_fraction is not None and stop_loss_fraction not in STOP_LOSS_FRACTIONS:
        raise ShadowStrategyLaneError("strategy lane stop loss is invalid")
    if profit_target_multiplier not in PROFIT_TARGET_MULTIPLIERS:
        raise ShadowStrategyLaneError("strategy lane profit target is invalid")
    if duration_cap_minutes is not None and duration_cap_minutes not in DURATION_CAP_MINUTES:
        raise ShadowStrategyLaneError("strategy lane duration cap is invalid")
    if (
        trailing_activation_margin is not None
        and trailing_activation_margin not in TRAILING_ACTIVATION_MARGINS
    ):
        raise ShadowStrategyLaneError("strategy lane trailing activation margin is invalid")
    if duration_cap_minutes is not None and trailing_activation_margin is not None:
        raise ShadowStrategyLaneError(
            "strategy lane may not combine duration cap and trailing lock this generation"
        )
    return ShadowStrategyLane(
        lane_id=_lane_id(
            policy_id=policy_id, scenario_id=scenario.scenario_id,
            stop_loss_fraction=stop_loss_fraction,
            profit_target_multiplier=profit_target_multiplier,
            duration_cap_minutes=duration_cap_minutes,
            trailing_activation_margin=trailing_activation_margin,
        ),
        policy_id=policy_id,
        scenario=scenario,
        stop_loss_fraction=stop_loss_fraction,
        profit_target_multiplier=profit_target_multiplier,
        duration_cap_minutes=duration_cap_minutes,
        trailing_activation_margin=trailing_activation_margin,
    )


THIRD_GENERATION_POLICY_ID = MOVING_ATM_ELEVEN
THIRD_GENERATION_PROFIT_TARGET_MULTIPLIER = Decimal("2.00")
THIRD_GENERATION_DURATION_CAP_MINUTES = (Decimal("15"), Decimal("20"), Decimal("25"))
THIRD_GENERATION_TRAILING_ACTIVATION_MARGINS = (Decimal("0.02"), Decimal("0.05"), Decimal("0.08"))


def build_shadow_strategy_lanes() -> tuple[ShadowStrategyLane, ...]:
    """Return the pre-registered 35-lane 24-hour comparison matrix.

    Third generation: the second generation's core bet (a wide price-based
    stop-loss) underperformed no-stop lanes in 4 of 5 edges on
    ``kxbtcd_soak_20260915_24h_6`` -- wider stops meant fewer but much bigger
    losses, net worse. That run's real driver of catastrophic losses turned
    out to be hold duration, not entry timing or price-stop level: outcomes
    were roughly breakeven-to-positive under 20 minutes held and fell off a
    cliff past that, uniformly regardless of when in the window a position
    entered. So this generation drops price-based stop-loss entirely and
    replaces it with two new, mutually exclusive exit mechanisms, each
    isolated (not crossed) so their individual effect can be read cleanly:
    a hold-duration cap, and a trailing profit lock that only protects gains
    after a position has gone favorable and then reversed, so a position
    climbing straight to its target is never affected. Both are fixed at
    ``profit_target=2.00`` (the stronger structural performer in both prior
    24h runs) to keep the matrix lean while introducing this much new,
    untested exit-logic surface area for the first time.
    """
    lanes = [
        _lane(
            policy_id=THIRD_GENERATION_POLICY_ID, scenario=scenario,
            profit_target_multiplier=THIRD_GENERATION_PROFIT_TARGET_MULTIPLIER,
        )
        for scenario in SHADOW_V2_SCENARIOS
    ]
    for duration_cap_minutes in THIRD_GENERATION_DURATION_CAP_MINUTES:
        for scenario in SHADOW_V2_SCENARIOS:
            lanes.append(_lane(
                policy_id=THIRD_GENERATION_POLICY_ID, scenario=scenario,
                profit_target_multiplier=THIRD_GENERATION_PROFIT_TARGET_MULTIPLIER,
                duration_cap_minutes=duration_cap_minutes,
            ))
    for trailing_activation_margin in THIRD_GENERATION_TRAILING_ACTIVATION_MARGINS:
        for scenario in SHADOW_V2_SCENARIOS:
            lanes.append(_lane(
                policy_id=THIRD_GENERATION_POLICY_ID, scenario=scenario,
                profit_target_multiplier=THIRD_GENERATION_PROFIT_TARGET_MULTIPLIER,
                trailing_activation_margin=trailing_activation_margin,
            ))
    result = tuple(lanes)
    if len(result) != 35 or len({item.lane_id for item in result}) != 35:
        raise ShadowStrategyLaneError("strategy lane catalog is incomplete")
    return result


SHADOW_STRATEGY_LANES = build_shadow_strategy_lanes()

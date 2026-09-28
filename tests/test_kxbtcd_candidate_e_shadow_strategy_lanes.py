from decimal import Decimal

from src.kxbtcd_candidate_e_live_shadow_micro_simulator import MOVING_ATM_ELEVEN
from src.kxbtcd_candidate_e_shadow_strategy_lanes import SHADOW_STRATEGY_LANES
from src.kxbtcd_candidate_e_shadow_v2_scenarios import SHADOW_V2_SCENARIOS


def test_strategy_lane_matrix_is_bounded_and_unique():
    assert len(SHADOW_STRATEGY_LANES) == 35
    assert len({lane.lane_id for lane in SHADOW_STRATEGY_LANES}) == 35
    assert sum(lane.stop_loss_fraction is not None for lane in SHADOW_STRATEGY_LANES) == 0
    assert all(lane.profit_target_multiplier == Decimal("2.00") for lane in SHADOW_STRATEGY_LANES)
    assert sum(lane.duration_cap_minutes is not None for lane in SHADOW_STRATEGY_LANES) == 15
    assert sum(lane.trailing_activation_margin is not None for lane in SHADOW_STRATEGY_LANES) == 15
    assert not any(
        lane.duration_cap_minutes is not None and lane.trailing_activation_margin is not None
        for lane in SHADOW_STRATEGY_LANES
    )


def test_strategy_lane_matrix_is_narrowed_to_the_moving_policy():
    assert all(lane.policy_id == MOVING_ATM_ELEVEN for lane in SHADOW_STRATEGY_LANES)


def test_strategy_lane_matrix_tests_every_edge_at_every_exit_combination():
    counts_by_scenario = {}
    for lane in SHADOW_STRATEGY_LANES:
        counts_by_scenario[lane.scenario.scenario_id] = (
            counts_by_scenario.get(lane.scenario.scenario_id, 0) + 1
        )
    assert set(counts_by_scenario) == {scenario.scenario_id for scenario in SHADOW_V2_SCENARIOS}
    assert set(counts_by_scenario.values()) == {7}

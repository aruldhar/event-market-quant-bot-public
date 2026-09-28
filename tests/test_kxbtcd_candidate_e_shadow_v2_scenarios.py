from decimal import Decimal

from src.kxbtcd_candidate_e_shadow_v2_scenarios import (
    EDGE_THRESHOLDS,
    EXECUTION_TIMING_BASIS,
    LATENCY_SENSITIVITY_SCOPE,
    PRIMARY_SHADOW_V2_SCENARIO,
    SHADOW_V2_SCENARIOS,
)


def test_shadow_v2_scenario_catalog_is_exact_five_edge_policy_grid():
    assert EDGE_THRESHOLDS == tuple(
        Decimal(value) for value in ("0.00", "0.01", "0.02", "0.03", "0.05")
    )
    assert len(SHADOW_V2_SCENARIOS) == 5
    assert len({scenario.scenario_id for scenario in SHADOW_V2_SCENARIOS}) == 5
    assert {scenario.edge_threshold for scenario in SHADOW_V2_SCENARIOS} == set(EDGE_THRESHOLDS)
    assert {scenario.scenario_id for scenario in SHADOW_V2_SCENARIOS} == {
        "edge_000", "edge_001", "edge_002", "edge_003", "edge_005"
    }


def test_shadow_v2_scenario_catalog_has_one_explicit_primary():
    primaries = [scenario for scenario in SHADOW_V2_SCENARIOS if scenario.is_primary]
    assert primaries == [PRIMARY_SHADOW_V2_SCENARIO]
    assert PRIMARY_SHADOW_V2_SCENARIO.edge_threshold == Decimal("0.02")
    assert PRIMARY_SHADOW_V2_SCENARIO.scenario_id == "edge_002"


def test_live_scenarios_use_observed_shadow_timing_and_keep_latency_offline_only():
    assert EXECUTION_TIMING_BASIS == "OBSERVED_SHADOW_PATH"
    assert LATENCY_SENSITIVITY_SCOPE == "OFFLINE_ONLY_NOT_LIVE_RANKED"
    assert all(
        scenario.execution_timing_basis == EXECUTION_TIMING_BASIS
        for scenario in SHADOW_V2_SCENARIOS
    )

from copy import deepcopy

import pytest

from src.kxbtcd_candidate_e_private_dashboard_design import (
    PrivateDashboardDesignError,
    validate_design,
    validate_payload,
)


def canonical():
    return dict(validate_design("."))


def rejected(mutator):
    payload = deepcopy(canonical())
    mutator(payload)
    with pytest.raises(PrivateDashboardDesignError):
        validate_payload(payload)


def test_private_dashboard_design_validates():
    payload = validate_design(".")
    assert payload["scope"]["dashboard_can_submit_orders"] is False
    assert payload["pnl_contract"]["realized_pnl_basis"] == "confirmed_fills_and_confirmed_fees_only"
    assert payload["shadow_simulation_contract"]["execution_side_effects"] is False
    assert payload["shadow_simulation_contract"]["simulated_entry_budget_dollars"] == "100.00"
    assert payload["scenario_lab_contract"]["scenario_ids"] == [
        "edge_000", "edge_001", "edge_002", "edge_003", "edge_005"
    ]
    assert payload["scenario_lab_contract"]["primary_scenario_id"] == "edge_002"
    assert payload["scenario_lab_contract"]["execution_timing_basis"] == "OBSERVED_SHADOW_PATH"
    assert payload["scenario_lab_contract"]["latency_sensitivity_scope"] == "OFFLINE_ONLY_NOT_LIVE_RANKED"
    assert payload["deployment"]["grafana_version"] == "13.2.1"
    assert payload["deployment"]["grafana_sqlite_plugin_version"] == "4.0.6"
    assert payload["deployment"]["current_shadow_read_model"] == "sqlite_query_projection_v2"
    assert payload["deployment"]["current_shadow_read_model_volume"] == "dedicated_projection_only_volume"


@pytest.mark.parametrize("mutator", [
    lambda p: p["scope"].__setitem__("dashboard_can_submit_orders", True),
    lambda p: p["isolation"].__setitem__("dashboard_credential_mounts", "kalshi_private_key"),
    lambda p: p["isolation"].__setitem__("dashboard_to_runtime_network_path", "http"),
    lambda p: p["future_ledger_contract"].__setitem__("current_phase_persists_order_fill_position_state", True),
    lambda p: p["pnl_contract"].__setitem__("realized_pnl_basis", "mark_price"),
    lambda p: p["shadow_simulation_contract"].__setitem__("execution_side_effects", True),
    lambda p: p["shadow_simulation_contract"].__setitem__("retained_exit_target", "reoptimized_each_tick"),
    lambda p: p["shadow_simulation_contract"].__setitem__("resting_exit_fill_claim", "assumed"),
    lambda p: p["shadow_simulation_contract"].__setitem__("simulated_entry_budget_dollars", "1000.00"),
    lambda p: p["scenario_lab_contract"].__setitem__("live_ranked_dimension", "edge_and_fake_latency"),
    lambda p: p["scenario_lab_contract"].__setitem__("latency_sensitivity_scope", "LIVE_RANKED"),
    lambda p: p["scenario_lab_contract"].__setitem__("execution_timing_basis", "ASSUMED_ZERO_LATENCY"),
    lambda p: p["scenario_lab_contract"].__setitem__("scenario_ids", ["edge_002"]),
    lambda p: p["operational_metrics"].__setitem__("forbidden_high_cardinality_labels", []),
    lambda p: p["deployment"].__setitem__("dashboard_platform", "custom_unreviewed_app"),
    lambda p: p["deployment"].__setitem__("current_shadow_read_model_access", "read_write"),
    lambda p: p["deployment"].__setitem__("current_shadow_read_model_volume", "shared_with_simulation_ledger"),
])
def test_private_dashboard_design_rejects_unsafe_or_unreviewed_changes(mutator):
    rejected(mutator)

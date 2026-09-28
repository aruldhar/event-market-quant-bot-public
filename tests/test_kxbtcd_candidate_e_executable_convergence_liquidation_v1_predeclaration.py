import copy
import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_predeclaration import (
    DEFAULT_CONFIG, canonical_fingerprint, load_predeclaration, validate_predeclaration,
)

def test_frozen_predeclaration_validates_and_fingerprint_reproduces():
    payload = load_predeclaration(DEFAULT_CONFIG)
    validate_predeclaration(payload)
    assert canonical_fingerprint(payload) == payload["predeclaration_fingerprint"]

def test_candidate_universe_and_execution_menu_are_exact():
    payload = load_predeclaration(DEFAULT_CONFIG)
    assert payload["candidate_universe"]["structural_roles"] == ["q10","q30","q50","q70","q90"]
    assert payload["candidate_universe"]["anchor_order_ttc_minutes"] == [55,50,45,40,35,30]
    assert payload["decision_state"]["edge_threshold_dollars"] == ["0.00","0.01","0.02","0.03","0.05"]
    assert payload["entry_execution"]["latency_ms"] == [0,500,1000]
    assert payload["decision_state"]["planned_contracts"] == "1.00"

def test_liquidation_target_is_entry_time_fair_and_single_attempt():
    payload = load_predeclaration(DEFAULT_CONFIG)
    lp = payload["liquidation_policy"]
    assert lp["frozen_target_per_contract"] == "entry_time_side_fair_probability"
    assert lp["dynamic_candidate_e_recalculation_after_entry"] is False
    assert lp["exit_attempt_count"] == 1
    assert lp["no_retry_after_partial_or_missed_exit"] is True
    assert lp["matched_control_branch"] == "hold_same_filled_quantity_to_settlement"

def test_replay_gap_is_fail_closed_not_assumed_missed_exit():
    payload = load_predeclaration(DEFAULT_CONFIG)
    lp = payload["liquidation_policy"]
    assert lp["gap_before_trigger"] == "primary_liquidation_branch_source_unavailable"
    assert lp["exit_source_invalid"] == "primary_liquidation_branch_source_unavailable_not_assumed_missed"
    assert "same_verified_segment" in payload["entry_execution"]["verified_segment_requirement"]
    assert "same_verified_segment" in lp["exit_verified_segment_requirement"]

def test_outcome_and_execution_firewalls_are_frozen():
    payload = load_predeclaration(DEFAULT_CONFIG)
    assert payload["evidence_scope"]["strategy_outcomes_accessed_before_predeclaration"] is False
    assert payload["evidence_scope"]["strategy_pnl_calculated_before_predeclaration"] is False
    assert payload["evaluation_contract"]["profitability_or_generalization_claim_allowed"] is False
    assert payload["evaluation_contract"]["advancement_gate"] == "none_on_four_event_exploratory_sandbox"
    for key in ("orders_submitted","paper_broker","demo_execution","real_money_execution",
                "predexon_purchase_authorized_by_this_checkpoint","c1_c2_c3_or_protected_reserve_access"):
        assert payload["safety"][key] is False

def test_mutation_breaks_fingerprint():
    payload = load_predeclaration(DEFAULT_CONFIG)
    mutated = copy.deepcopy(payload)
    mutated["entry_execution"]["latency_ms"] = [0,250,500]
    with pytest.raises(ValueError, match="fingerprint"):
        validate_predeclaration(mutated)

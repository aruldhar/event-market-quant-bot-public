from __future__ import annotations
from copy import deepcopy
import pytest
from src.kxbtcd_candidate_e_continuous_convergence_reentry_v1_predeclaration import (
    ContinuousConvergenceReentryPredeclarationError,
    EXPECTED_PREDECLARATION_FINGERPRINT,
    canonical_fingerprint, predeclaration_definition, validate_predeclaration,
)

def test_exact_predeclaration_validates():
    d = predeclaration_definition()
    assert validate_predeclaration(d) == EXPECTED_PREDECLARATION_FINGERPRINT
    assert canonical_fingerprint(d) == EXPECTED_PREDECLARATION_FINGERPRINT

def test_continuous_clock_and_window_are_frozen():
    d = predeclaration_definition()
    w = d["entry_scan_window"]
    assert w["start"] == "event_close_minus_55_minutes_inclusive"
    assert w["end"] == "event_close_minus_2_minutes_inclusive"
    assert w["fixed_scheduled_entry_anchors_used"] is False
    c = d["continuous_decision_clock"]
    assert c["deep_book_change_without_best_level_change_creates_entry_decision"] is False
    assert c["evaluate_all_five_structural_roles_at_each_event_timestamp"] is True

def test_candidate_e_unchanged_and_ttc_not_input():
    d = predeclaration_definition()
    assert d["retained_frozen_parents"]["candidate_e_refit_allowed"] is False
    s = d["candidate_e_decision_state"]
    assert s["model_formula_changed"] is False
    assert s["ttc_is_model_input"] is False
    assert s["requires_valid_uncrossed_two_sided_yes_book"] is True

def test_coinbase_rule_fail_closed():
    b = predeclaration_definition()["btc_state"]
    for k in ["future_or_incomplete_candle_allowed","nearest_sampling_allowed",
              "interpolation_allowed","missing_bucket_stale_carry_allowed","source_substitution_allowed"]:
        assert b[k] is False

def test_reentry_requires_full_exit_and_rearm():
    p = predeclaration_definition()["reentry_policy"]
    assert p["maximum_reentries"] == 1
    assert p["requires_prior_position_fully_exited"] is True
    assert p["rearm_required"] is True
    assert p["source_unavailable_or_invalid_reference_state_counts_as_rearm"] is False
    assert p["trade1_history_used_to_select_trade2"] is False
    assert p["third_entry_allowed"] is False

def test_missed_entry_does_not_consume_cap_partial_does():
    e = predeclaration_definition()["entry_execution"]
    assert e["missed_entry_counts_toward_two_entry_cap"] is False
    assert e["partial_entry_counts_as_filled_entry"] is True
    assert e["partial_entry_unfilled_remainder_top_up_allowed"] is False

def test_three_comparison_branches():
    b = predeclaration_definition()["comparison_branches"]
    assert b["branch_a_matched_hold"]["reentry"] is False
    assert b["branch_b_liquidate_once"]["reentry"] is False
    assert b["branch_c_primary"]["reentry"] is True

def test_mutation_rejected_even_if_refingerprinted():
    d = predeclaration_definition()
    m = deepcopy(d)
    m["reentry_policy"]["maximum_reentries"] = 2
    m["predeclaration_fingerprint"] = canonical_fingerprint(m)
    with pytest.raises(ContinuousConvergenceReentryPredeclarationError):
        validate_predeclaration(m)

def test_safety_firewall():
    s = predeclaration_definition()["safety"]
    assert s["read_only"] is True
    for k in ["orders_submitted","paper_broker","demo_execution","real_money_execution",
              "candidate_e_refit_authorized","july10_settlement_outcome_access_authorized"]:
        assert s[k] is False

def test_only_one_entry_order_can_be_pending():
    e = predeclaration_definition()["entry_execution"]
    assert e["one_entry_order_may_be_pending_at_a_time"] is True
    assert e["decision_clock_timestamps_during_entry_order_flight"] == "ignored_for_new_entry_decisions"
    assert "strictly_after_entry_arrival_time" in e["missed_entry_state_transition"]
    assert e["counterfactual_fill_rewrites_later_historical_book"] is False

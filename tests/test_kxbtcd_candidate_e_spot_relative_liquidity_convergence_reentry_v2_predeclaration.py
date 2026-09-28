from datetime import datetime, timezone

from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_predeclaration import (
    EXPECTED_PREDECLARATION_FINGERPRINT,
    canonical_fingerprint,
    validate_predeclaration,
)

def test_exact_predeclaration_fingerprint():
    p = validate_predeclaration(".")
    assert p["predeclaration_fingerprint"] == EXPECTED_PREDECLARATION_FINGERPRINT
    assert canonical_fingerprint(p) == EXPECTED_PREDECLARATION_FINGERPRINT

def test_dynamic_universe_is_exact_atm_plus_minus_five():
    p = validate_predeclaration(".")
    u = p["dynamic_tradable_universe"]
    assert u["rank_radius"] == 5
    assert u["maximum_markets_in_window"] == 11
    assert u["atm_tie_break"] == ["lower_numeric_strike", "market_ticker_ascending"]
    assert u["liquidity_used_to_define_atm_or_window_membership"] is False
    assert u["arbitrary_market_outside_window_allowed"] is False

def test_candidate_e_is_frozen_and_domain_extension_is_explicit():
    p = validate_predeclaration(".")
    c = p["candidate_e"]
    assert c["beta_distance"] == "0.014939489324405949"
    assert c["refit_allowed"] is False
    assert c["recalibration_allowed"] is False
    assert c["nonstructural_use_primary_label"] == "nonstructural_spot_window_domain_extension"

def test_fresh_targets_are_fixed_unique_and_after_champion_freeze():
    p = validate_predeclaration(".")
    f = p["fresh_nonstructural_domain_validation"]
    targets = f["target_events"]
    assert len(targets) == 24
    assert len({x["event_ticker"] for x in targets}) == 24
    assert f["replacement_events_allowed"] is False
    freeze = datetime.fromisoformat(
        p["parent_bindings"]["candidate_e_champion_final_freeze_utc"].replace("Z", "+00:00")
    )
    for target in targets:
        close = datetime.fromisoformat(target["expected_close_utc"].replace("Z", "+00:00"))
        assert close > freeze

def test_fresh_gate_is_nonstructural_and_fail_closed():
    p = validate_predeclaration(".")
    f = p["fresh_nonstructural_domain_validation"]
    g = f["source_adequacy_gate"]
    primary = f["primary_gate"]
    assert "nonstructural" in f["usable_domain_extension_cross_section_definition"]
    assert "nonstructural" in f["primary_scored_rows"]
    assert g["minimum_materialized_events"] == 20
    assert g["minimum_events_with_at_least_27_of_54_usable_domain_extension_cross_sections"] == 16
    assert g["minimum_pooled_usable_domain_extension_cross_sections"] == 778
    assert g["gate_failure"] == "stop_before_any_fresh_outcome_access"
    assert primary["minimum_date_block_log_loss_wins"] == 4
    assert primary["newest_block"] == "2026-08-29"
    assert primary["newest_block_log_loss_win_required"] is True
    assert f["fresh_strategy_pnl_authorized_by_this_predeclaration"] is False

def test_read_only_safety_and_no_21n_x_evidence_access():
    p = validate_predeclaration(".")
    s = p["safety"]
    assert s["current_phase_read_only"] is True
    assert s["candidate_e_nonstructural_scoring_performed_in_21n_x"] is False
    assert s["fresh_target_outcomes_accessed"] is False
    assert s["july10_v2_outcomes_accessed"] is False
    assert s["network_requests_in_21n_x"] == 0
    assert s["predexon_purchases_in_21n_x"] == 0
    assert s["orders_placed"] == 0

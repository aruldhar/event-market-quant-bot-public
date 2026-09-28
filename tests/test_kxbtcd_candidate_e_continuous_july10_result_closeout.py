from src.kxbtcd_candidate_e_continuous_july10_result_closeout import (
    EXPECTED_RESULT_CLOSEOUT_FINGERPRINT,
    canonical_fingerprint,
    validate_result_closeout,
)

def test_result_closeout_exact_fingerprint_and_classification():
    p = validate_result_closeout(".")
    assert p["result_closeout_fingerprint"] == EXPECTED_RESULT_CLOSEOUT_FINGERPRINT
    assert canonical_fingerprint(p) == EXPECTED_RESULT_CLOSEOUT_FINGERPRINT
    assert p["classification"] == "NON_EVALUABLE_STRUCTURAL_UNIVERSE_LIQUIDITY_MISMATCH"

def test_result_closeout_keeps_v1_closed_without_outcomes():
    p = validate_result_closeout(".")
    c = p["research_consequence"]
    s = p["safety"]
    assert c["continuous_v1_result_status"] == "CLOSED_NON_EVALUABLE"
    assert c["threshold_tuning_authorized"] is False
    assert c["open_settlement_outcomes_for_v1_authorized"] is False
    assert c["modify_v1_market_universe_authorized"] is False
    assert s["outcomes_accessed"] is False
    assert s["settlement_dependent_pnl_calculated"] is False
    assert s["orders_placed"] == 0

def test_full_ladder_diagnostic_does_not_relabel_v1_as_edge_failure():
    p = validate_result_closeout(".")
    gate = p["entry_gate_diagnostic"]
    ladder = p["full_ladder_exploratory_diagnostic"]
    assert gate["evaluable_market_state_count"] == 0
    assert ladder["ticker_count_with_any_valid_two_sided_state"] == 45
    assert ladder["frozen_structural_ticker_count_with_any_valid_two_sided_state"] == 0

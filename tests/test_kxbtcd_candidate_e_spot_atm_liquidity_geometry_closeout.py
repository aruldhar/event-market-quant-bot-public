from src.kxbtcd_candidate_e_spot_atm_liquidity_geometry_closeout import (
    EXPECTED_RESULT_CLOSEOUT_FINGERPRINT,
    canonical_fingerprint,
    validate_closeout,
)

def test_21n_w_closeout_fingerprint_and_classification():
    p = validate_closeout(".")
    assert p["result_closeout_fingerprint"] == EXPECTED_RESULT_CLOSEOUT_FINGERPRINT
    assert canonical_fingerprint(p) == EXPECTED_RESULT_CLOSEOUT_FINGERPRINT
    assert p["classification"] == "EXPLORATORY_SUPPORT_SPOT_ATM_RELATIVE_LIQUIDITY_STRUCTURE"

def test_21n_w_does_not_select_v2_or_score_candidate_e():
    p = validate_closeout(".")
    i = p["interpretation"]
    s = p["safety"]
    assert i["v2_rank_envelope_selected"] is False
    assert i["nonstructural_candidate_e_use_validated"] is False
    assert i["profitability_established"] is False
    assert i["independent_event_count"] == 4
    assert s["candidate_e_scored"] is False
    assert s["nonstructural_probability_inference"] is False
    assert s["outcomes_accessed"] is False
    assert s["orders_placed"] == 0

def test_21n_w_keeps_continuous_v1_closed():
    p = validate_closeout(".")
    c = p["research_consequence"]
    assert c["continuous_v1_remains_closed"] is True
    assert c["modify_continuous_v1_authorized"] is False
    assert c["open_v1_settlement_outcomes_authorized"] is False

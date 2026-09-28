import hashlib
import json
from pathlib import Path

PATH = Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_predeclaration.json")
EXPECTED_FP = "742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3"


def load_doc():
    return json.loads(PATH.read_text(encoding="utf-8"))


def canonical_fp(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_predeclaration_fingerprint_is_exact():
    doc = load_doc()
    supplied = doc.pop("predeclaration_fingerprint")
    assert supplied == EXPECTED_FP
    assert canonical_fp(doc) == EXPECTED_FP


def test_small_four_feature_sigmoid_model_starts_at_half():
    doc = load_doc()
    assert [x["name"] for x in doc["features"]] == [
        "abs_candidate_market_disagreement", "spread_t", "abs_r_5m", "ttc_minutes"
    ]
    alpha = doc["alpha_model"]
    assert alpha["learned_parameter_count"] == 5
    assert alpha["initial_parameters"] == [0.0] * 5
    assert alpha["initial_alpha_every_state"] == 0.5
    assert alpha["one_shared_model_for_yes_and_no"] is True
    assert alpha["between_endpoints_invariant_required"] is True


def test_fit_target_is_probability_not_pnl_and_global_alpha_search_is_closed():
    doc = load_doc()
    assert doc["fit_contract"]["direct_realized_pnl_training_target"] is False
    assert doc["probability_benchmarks"]["additional_global_alpha_search"] is False
    assert doc["probability_benchmarks"]["alpha_0_25_or_0_75_rescore_for_selection"] is False
    assert doc["fit_contract"]["regularized_parameters"] == "all_5_including_intercept"


def test_development_economics_is_oof_not_full_fit_in_sample():
    doc = load_doc()
    econ = doc["development_economic_gate"]
    assert econ["score_events"] == 1500
    assert "rolling-origin" in econ["evaluation_predictions"]
    assert "five contiguous 300-event blocks" in econ["chronological_block_rule"]
    assert doc["rolling_origin_selection"]["full_development_fit_allowed_only_after_complete_development_PASS"] is True


def test_evidence_firewall_and_historical_crossfit_are_explicit():
    doc = load_doc()
    assert doc["historical_probability_lineage"]["development_state_universe_must_match_exactly"] is True
    assert "not regenerated in-sample" in doc["historical_probability_lineage"]["principle"]
    roles = doc["evidence_roles"]
    assert roles["C1_C2"]["authorized_in_21N_I"] is False
    assert roles["C3"]["authorized_in_21N_I"] is False
    assert roles["protected_reserve"]["authorized_in_21N_I"] is False
    assert doc["next_checkpoint"]["fit_authorized_by_21N_I"] is False

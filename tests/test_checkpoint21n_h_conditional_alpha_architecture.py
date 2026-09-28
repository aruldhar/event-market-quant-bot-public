import json
from pathlib import Path

def test_conditional_alpha_is_bounded_and_not_direct_pnl_target():
    doc = json.loads(Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_architecture.json").read_text(encoding="utf-8"))
    assert "sigmoid" in doc["core_architecture"]["alpha_definition"]
    assert doc["core_architecture"]["cannot_extrapolate_beyond_market_and_candidate_e"] is True
    assert doc["research_target"]["direct_realized_pnl_training_target"] is False
    assert doc["next_checkpoint"]["fit_authorized_in_21N_H"] is False

def test_evidence_firewall_stays_closed():
    doc = json.loads(Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_architecture.json").read_text(encoding="utf-8"))
    fw = doc["evidence_firewall"]
    assert fw["C1_C2_conditional_alpha_use_authorized_now"] is False
    assert fw["C3_conditional_alpha_use_authorized_now"] is False
    assert fw["protected_reserve_use_authorized_now"] is False

def test_posthoc_repairs_are_explicitly_excluded():
    doc = json.loads(Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_architecture.json").read_text(encoding="utf-8"))
    excluded = set(doc["explicit_posthoc_exclusions"])
    assert "hardcoded_NO_only_or_YES_only_rule_from_exposed_economics" in excluded
    assert "hardcoded_avoid_T55_rule_from_exposed_economics" in excluded
    assert "intermediate_global_alpha_search" in excluded

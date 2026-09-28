"""Validate the frozen Checkpoint 21N-N-A alpha-entry diagnostic predeclaration."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "configs" / "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_predeclaration.json"
EXPECTED = "2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e"

def canonical_sha(doc):
    copy = dict(doc)
    copy.pop("predeclaration_fingerprint", None)
    return hashlib.sha256(
        json.dumps(copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

doc = json.loads(PATH.read_text(encoding="utf-8"))
assert doc["schema_version"] == "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_predeclaration.v1"
assert doc["diagnostic_id"] == "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic.v1"
assert doc["status"] == "PREDECLARED_NOT_RUN"
assert doc["predeclaration_fingerprint"] == EXPECTED
assert canonical_sha(doc) == EXPECTED
assert doc["canonical_parent_result"]["overall_status"] == "FAIL_PROBABILITY_GATE"
assert doc["canonical_parent_result"]["selected_lambda"] == 0.001
assert doc["valuation_policy"]["probability_source"] == "Candidate E candidate_probability only"
assert doc["valuation_policy"]["conditional_adjusted_probability_used_for_valuation"] is False
assert doc["alpha_ranking_policy"]["fixed_alpha_threshold_search"] is False
assert doc["evidence_scope"]["C3_allowed"] is False
assert doc["evidence_scope"]["protected_reserve_allowed"] is False
assert doc["evidence_scope"]["execution_allowed"] is False

print("Alpha-reliability entry diagnostic v1 predeclaration validation: PASS")
print("predeclaration_fingerprint=" + EXPECTED)
print("diagnostic_run_performed=false")
print("PnL_inspected=false")
print("C3_accessed=false")
print("protected_reserve_accessed=false")
print("execution_authorized=false")

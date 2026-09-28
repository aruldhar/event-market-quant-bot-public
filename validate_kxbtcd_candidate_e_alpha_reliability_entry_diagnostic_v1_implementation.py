"""Validate Checkpoint 21N-N-B implementation freeze without running real H economics."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
FREEZE = ROOT / "configs" / "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_implementation_freeze.json"
EXPECTED_FP = "2bc7d625fa7889ee071322a3d3785becc49fd66fcf409e47713de8dc2405bc0d"
EXPECTED_SOURCE_SHA = "1c5eb6af1622a38128b3dc97957d920e375150cf2affa274b3048436c8a9f15e"
EXPECTED_CLI_SHA = "6f26958b3d1ce9d9dae653fbf58e9bac4b50edcb2208f5d86a643b04b3942b00"
EXPECTED_RESULT_VALIDATOR_SHA = "d24fa94cf3cd7606a8731a44147f8740051691a75822097416e55d32512d9e11"
EXPECTED_TEST_SHA = "abcf673889879f7928ec75fa118ed11be6570ceb59f14af40ac72accf7bc9253"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

doc = json.loads(FREEZE.read_text(encoding="utf-8"))
copy = dict(doc)
supplied = copy.pop("implementation_fingerprint")
assert supplied == EXPECTED_FP
assert hashlib.sha256(json.dumps(copy, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == EXPECTED_FP
assert doc["predeclaration_fingerprint"] == "2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e"
assert sha(ROOT / "src" / "kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1.py") == EXPECTED_SOURCE_SHA
assert sha(ROOT / "evaluate_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1.py") == EXPECTED_CLI_SHA
assert sha(ROOT / "validate_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_result.py") == EXPECTED_RESULT_VALIDATOR_SHA
assert sha(ROOT / "tests" / "test_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1.py") == EXPECTED_TEST_SHA
assert doc["real_diagnostic_run_performed"] is False
assert doc["pnl_inspected_by_implementation_checkpoint"] is False
assert doc["threshold_search_performed"] is False
assert doc["C3_accessed"] is False
assert doc["protected_reserve_accessed"] is False
assert doc["execution_authorized"] is False

print("Alpha-reliability entry diagnostic v1 implementation validation: PASS")
print("implementation_fingerprint=" + EXPECTED_FP)
print("diagnostic_run_performed=false")
print("PnL_inspected=false")
print("threshold_search_performed=false")
print("C3_accessed=false")
print("protected_reserve_accessed=false")
print("execution_authorized=false")

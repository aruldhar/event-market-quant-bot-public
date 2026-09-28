"""Validate 21N-N-C-B implementation freeze without running real H economics."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
FREEZE = ROOT / "configs" / "kxbtcd_candidate_e_incremental_alpha_entry_score_v1_implementation_freeze.json"

EXPECTED_FP = "8c88bb386e0ba13b3ab8761e67a73dd7105637d3667d5fc7394d163259b5471b"
EXPECTED_SOURCE_SHA = "ec4de0809cc3cecf8fe36255659c498d23b3a888a534d0d6b5dffc150d681b8d"
EXPECTED_CLI_SHA = "a0c86581a99975be4a9e10b818de9037823fe1a3cc2bb0af6fb76dd89d6231c5"
EXPECTED_RESULT_VALIDATOR_SHA = "c30c3ef834d257458e7ba9e4147c2de38b90f69f20129b1004216bb842dbc60f"
EXPECTED_TEST_SHA = "5c7b960527b04fc93cfca970f4a63fcb4fb93d76349959a7456271717dfb6599"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

doc = json.loads(FREEZE.read_text(encoding="utf-8"))
copy = dict(doc)
supplied = copy.pop("implementation_fingerprint")
actual = hashlib.sha256(
    json.dumps(copy, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()

assert supplied == EXPECTED_FP
assert actual == EXPECTED_FP
assert doc["predeclaration_fingerprint"] == "bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa"
assert sha(ROOT / "src" / "kxbtcd_candidate_e_incremental_alpha_entry_score_v1.py") == EXPECTED_SOURCE_SHA
assert sha(ROOT / "evaluate_kxbtcd_candidate_e_incremental_alpha_entry_score_v1.py") == EXPECTED_CLI_SHA
assert sha(ROOT / "validate_kxbtcd_candidate_e_incremental_alpha_entry_score_v1_result.py") == EXPECTED_RESULT_VALIDATOR_SHA
assert sha(ROOT / "tests" / "test_kxbtcd_candidate_e_incremental_alpha_entry_score_v1.py") == EXPECTED_TEST_SHA

assert doc["real_incremental_score_run_performed"] is False
assert doc["incremental_score_pnl_inspected"] is False
assert doc["coverage_search_performed"] is False
assert doc["absolute_threshold_search_performed"] is False
assert doc["C3_accessed"] is False
assert doc["protected_reserve_accessed"] is False
assert doc["network_accessed"] is False
assert doc["execution_authorized"] is False

print("Incremental alpha entry score v1 implementation validation: PASS")
print("implementation_fingerprint=" + EXPECTED_FP)
print("real_incremental_score_run_performed=false")
print("incremental_score_PnL_inspected=false")
print("coverage_search_performed=false")
print("C3_accessed=false")
print("protected_reserve_accessed=false")
print("execution_authorized=false")

"""Validate Checkpoint 21N-M-C evaluator implementation freeze."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "configs" / "kxbtcd_candidate_e_conditional_alpha_reliability_v2_development_implementation_freeze.json"
EXPECTED_IMPLEMENTATION_FINGERPRINT = "bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a"

EXPECTED_SHAS = {
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v2_development.py": "9371d8bab58f6e328b3f82671eb19aaa7f6e252f07ed5f963c6a849bc3684d53",
    "evaluate_kxbtcd_candidate_e_conditional_alpha_reliability_v2_development.py": "4180d9b391f8c3c2fcda92da6479e79b641216994cea20d6378e09b53fc474ad",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v2_development_result.py": "1c2b3de6b1cf467c2d9a73faa24a5bd24426b6dfc82b238e82ef3b4d715a673e",
}


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    supplied = cfg.get("implementation_fingerprint")
    copy = dict(cfg)
    copy.pop("implementation_fingerprint", None)
    if canonical_sha256(copy) != supplied or supplied != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        raise RuntimeError("21N-M-C implementation fingerprint mismatch")

    if cfg.get("candidate_id") != "kxbtcd_candidate_e_conditional_alpha_reliability.v2":
        raise RuntimeError("candidate mismatch")
    if cfg.get("parent_v1_status") != "PERMANENT_FAIL_OPTIMIZER_CONTRACT":
        raise RuntimeError("v1 status changed")
    if cfg.get("parent_v2_implementation_fingerprint") != "459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd":
        raise RuntimeError("v2 implementation parent mismatch")

    for rel, expected in EXPECTED_SHAS.items():
        if sha256_file(ROOT / rel) != expected:
            raise RuntimeError(f"SHA mismatch: {rel}")

    scope = cfg["implementation_scope"]
    for key in (
        "real_fit_performed_in_21N_M_C",
        "lambda_selected_in_21N_M_C",
        "probability_gate_scored_in_21N_M_C",
        "economic_gate_scored_in_21N_M_C",
    ):
        if scope.get(key) is not False:
            raise RuntimeError(f"21N-M-C unexpectedly performed {key}")

    if cfg["post_closeout_authorization"]["only_after_valid_21N_M_C_closeout_receipt"] is not True:
        raise RuntimeError("real evaluator is not closeout locked")
    if any(cfg["safety"].values()):
        raise RuntimeError("21N-M-C safety flags must remain false")

    print("Conditional-alpha v2 development evaluator implementation validation: PASS")
    print(f"implementation_fingerprint={supplied}")
    print("candidate_id=kxbtcd_candidate_e_conditional_alpha_reliability.v2")
    print("parent_v1_remains_FAIL_OPTIMIZER_CONTRACT=true")
    print("real_v2_fit_performed=false")
    print("lambda_selection_performed=false")
    print("probability_gate_scored=false")
    print("economic_gate_scored=false")
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

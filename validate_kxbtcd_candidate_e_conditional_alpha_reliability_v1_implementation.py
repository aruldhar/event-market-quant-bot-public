"""Validate Checkpoint 21N-J-A implementation freeze without project-data fitting."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    EXPECTED_PREDECLARATION_FINGERPRINT,
    LAMBDA_GRID,
    PARAMETER_NAMES,
    RAW_FEATURES,
    validate_predeclaration,
)

CONFIG = Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_implementation_freeze.json")
EXPECTED_IMPLEMENTATION_FINGERPRINT = "566f085ef78e8045a75a1dc3781255a2dcae30f23d04ba317ab56e87ac18f5a6"

def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

def main() -> int:
    predecl = validate_predeclaration()
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    if doc.get("schema_version") != "kxbtcd_candidate_e_conditional_alpha_reliability_v1_implementation_freeze.v1":
        raise SystemExit("implementation schema mismatch")
    supplied = doc.get("implementation_fingerprint")
    copy = dict(doc)
    copy.pop("implementation_fingerprint", None)
    if canonical_sha256(copy) != supplied or supplied != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        raise SystemExit("implementation fingerprint mismatch")
    if doc.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        raise SystemExit("predeclaration lineage mismatch")
    for path, expected in doc.get("implementation_sha256s", {}).items():
        if sha256_file(path) != expected:
            raise SystemExit(f"implementation SHA mismatch: {path}")
    scope = doc["implementation_scope"]
    if scope["real_data_fit_cli_present"] is not False:
        raise SystemExit("real-data fit CLI must not exist in 21N-J-A")
    if scope["real_outcome_scoring_cli_present"] is not False:
        raise SystemExit("real-outcome scoring CLI must not exist in 21N-J-A")
    if scope["real_pnl_evaluator_present"] is not False:
        raise SystemExit("real P&L evaluator must not exist in 21N-J-A")
    if tuple(item["name"] for item in predecl["features"]) != RAW_FEATURES:
        raise SystemExit("feature contract mismatch")
    if tuple(float(x) for x in predecl["fit_contract"]["lambda_grid"]) != LAMBDA_GRID:
        raise SystemExit("lambda grid mismatch")
    if len(PARAMETER_NAMES) != 5:
        raise SystemExit("parameter dimension mismatch")
    for key, value in doc["safety"].items():
        if value is not False:
            raise SystemExit(f"safety flag {key} must be false")
    print("Checkpoint 21N-J-A conditional-alpha implementation validation: PASS")
    print(f"implementation_fingerprint={EXPECTED_IMPLEMENTATION_FINGERPRINT}")
    print(f"predeclaration_fingerprint={EXPECTED_PREDECLARATION_FINGERPRINT}")
    print("features=4")
    print("learned_parameters=5")
    print("initial_alpha=0.50")
    print("real_data_gamma_fit_performed=false")
    print("real_outcome_scoring_performed=false")
    print("real_strategy_pnl_calculated=false")
    print("c1_c2_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_authorized=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

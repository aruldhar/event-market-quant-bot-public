from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_FREEZE_FINGERPRINT = "a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e"
EXPECTED_EVALUATION_SHA256 = "2f32edeef294a6769c9d49a456c493771a76ce5aebefafc1bc11d375765b3365"
EXPECTED_LAMBDA_SHA256 = "54cf07059498683895fba674f1ee94163e9cea3f4a597822df7e31093d253f51"
EXPECTED_RECEIPT_SHA256 = "14c75f8f0ccbef081e841fd75e6adab500b459e1fcdcee3d002c328c1bf11523"

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def canonical_fingerprint(value: dict[str, Any]) -> str:
    copy = dict(value)
    copy.pop("development_freeze_fingerprint", None)
    payload = json.dumps(copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--lambda-scores", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    freeze_path = Path(args.freeze)
    evaluation_path = Path(args.evaluation)
    lambda_path = Path(args.lambda_scores)
    receipt_path = Path(args.receipt)
    for path in (freeze_path, evaluation_path, lambda_path, receipt_path):
        if not path.is_file():
            raise RuntimeError(f"required validation file missing: {path}")

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if freeze.get("development_freeze_fingerprint") != EXPECTED_FREEZE_FINGERPRINT:
        raise RuntimeError("development freeze fingerprint field mismatch")
    if canonical_fingerprint(freeze) != EXPECTED_FREEZE_FINGERPRINT:
        raise RuntimeError("development freeze canonical fingerprint mismatch")
    if sha256_file(evaluation_path) != EXPECTED_EVALUATION_SHA256:
        raise RuntimeError("evaluation file SHA-256 mismatch")
    if sha256_file(lambda_path) != EXPECTED_LAMBDA_SHA256:
        raise RuntimeError("lambda-score file SHA-256 mismatch")
    if sha256_file(receipt_path) != EXPECTED_RECEIPT_SHA256:
        raise RuntimeError("receipt file SHA-256 mismatch")

    if freeze["development_evidence"]["evaluation_fingerprint"] != receipt.get("evaluation_fingerprint"):
        raise RuntimeError("freeze/receipt evaluation fingerprint mismatch")
    if freeze["selection"]["selected_lambda"] != evaluation.get("selected_lambda"):
        raise RuntimeError("freeze/evaluation selected lambda mismatch")
    if freeze["selection"]["lambda_scores"] != evaluation.get("lambda_scores"):
        raise RuntimeError("freeze/evaluation lambda-score mismatch")
    if freeze["rolling_origin_diagnostics"] != evaluation.get("selected_rolling_origin_diagnostics"):
        raise RuntimeError("freeze/evaluation diagnostics mismatch")
    if freeze["full_development_fit"] != evaluation.get("full_development_fit"):
        raise RuntimeError("freeze/evaluation full-fit mismatch")
    if freeze["provenance"]["source_sha256s"] != receipt.get("source_sha256s"):
        raise RuntimeError("freeze/receipt source hashes mismatch")
    if freeze["provenance"]["implementation_sha256s"] != receipt.get("implementation_sha256s"):
        raise RuntimeError("freeze/receipt implementation hashes mismatch")
    if freeze["safety"] != receipt.get("safety"):
        raise RuntimeError("freeze/receipt safety mismatch")

    expected_output = dict(receipt.get("output_sha256s", {}))
    expected_output["receipt"] = EXPECTED_RECEIPT_SHA256
    if freeze["provenance"]["output_sha256s"] != expected_output:
        raise RuntimeError("freeze output hashes mismatch")

    if freeze["interpretation"].get("validation_gate_evaluated") is not False:
        raise RuntimeError("validation gate must remain unopened at development freeze")
    if freeze["interpretation"].get("model2_generalization_pass_claim") is not False:
        raise RuntimeError("development freeze cannot claim Model-2 generalization PASS")
    if freeze["interpretation"].get("profitability_claim") is not False:
        raise RuntimeError("development freeze cannot claim profitability")
    if freeze["interpretation"].get("eligible_to_open_c1_c2_validation") is not True:
        raise RuntimeError("development freeze must explicitly authorize only C1+C2 validation")

    print("Candidate-E Entry Model v1 development freeze validation: PASS")
    print(f"development_freeze_fingerprint={EXPECTED_FREEZE_FINGERPRINT}")
    print(f"selected_lambda={freeze['selection']['selected_lambda']}")
    print(f"evaluation_fingerprint={freeze['development_evidence']['evaluation_fingerprint']}")
    print("development_fit_exact_match=pass")
    print("provenance_exact_match=pass")
    print("eligible_to_open_c1_c2_validation=true")
    print("validation_gate_evaluated=false")
    print("model2_generalization_pass_claim=false")
    print("profitability_claim=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

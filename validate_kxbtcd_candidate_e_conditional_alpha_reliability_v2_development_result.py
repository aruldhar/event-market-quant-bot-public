"""Validate a persisted conditional-alpha v2 H-development result."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import canonical_sha256
from src.kxbtcd_candidate_e_conditional_alpha_reliability_v2_development import (
    CANDIDATE_ID,
    DEVELOPMENT_EVALUATION_SCHEMA,
    DEVELOPMENT_FAILURE_SCHEMA,
    DEVELOPMENT_FAILURE_RECEIPT_SCHEMA,
    DEVELOPMENT_RECEIPT_SCHEMA,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--evaluation", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--rolling-predictions")
    p.add_argument("--entry-decisions")
    return p


def main():
    args = parser().parse_args()
    evaluation_path = Path(args.evaluation)
    receipt_path = Path(args.receipt)
    evaluation = read_json(evaluation_path)
    receipt = read_json(receipt_path)

    if evaluation.get("candidate_id") != CANDIDATE_ID:
        raise RuntimeError("v2 result candidate mismatch")

    copy_eval = dict(evaluation)
    supplied_eval = copy_eval.pop("evaluation_fingerprint")
    if canonical_sha256(copy_eval) != supplied_eval:
        raise RuntimeError("evaluation fingerprint mismatch")

    failure = evaluation.get("schema_version") == DEVELOPMENT_FAILURE_SCHEMA
    expected_receipt_schema = (
        DEVELOPMENT_FAILURE_RECEIPT_SCHEMA if failure else DEVELOPMENT_RECEIPT_SCHEMA
    )
    if receipt.get("schema_version") != expected_receipt_schema:
        raise RuntimeError("receipt schema mismatch")
    if receipt.get("candidate_id") != CANDIDATE_ID:
        raise RuntimeError("receipt candidate mismatch")
    if receipt.get("evaluation_fingerprint") != supplied_eval:
        raise RuntimeError("receipt/evaluation fingerprint mismatch")

    copy_receipt = dict(receipt)
    supplied_receipt = copy_receipt.pop("receipt_fingerprint")
    if canonical_sha256(copy_receipt) != supplied_receipt:
        raise RuntimeError("receipt fingerprint mismatch")
    if receipt["output_sha256s"]["evaluation_sha256"] != sha256_file(evaluation_path):
        raise RuntimeError("evaluation SHA mismatch")

    if failure:
        if evaluation.get("overall_status") != "FAIL_OPTIMIZER_CONTRACT":
            raise RuntimeError("failure evaluation status mismatch")
        if args.rolling_predictions or args.entry_decisions:
            raise RuntimeError("optimizer failure must not supply prediction/entry artifacts")
    else:
        if evaluation.get("schema_version") != DEVELOPMENT_EVALUATION_SCHEMA:
            raise RuntimeError("development evaluation schema mismatch")
        if not args.rolling_predictions:
            raise RuntimeError("non-optimizer result requires rolling predictions")
        prediction_path = Path(args.rolling_predictions)
        if receipt["output_sha256s"]["rolling_predictions_sha256"] != sha256_file(prediction_path):
            raise RuntimeError("rolling prediction SHA mismatch")
        with prediction_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if any(row.get("candidate_id") != CANDIDATE_ID for row in rows):
            raise RuntimeError("rolling prediction candidate mismatch")
        entry_sha = receipt["output_sha256s"]["entry_decisions_sha256"]
        if entry_sha is None:
            if args.entry_decisions:
                raise RuntimeError("receipt says no entry artifact")
        else:
            if not args.entry_decisions:
                raise RuntimeError("receipt requires entry artifact")
            if entry_sha != sha256_file(Path(args.entry_decisions)):
                raise RuntimeError("entry decision SHA mismatch")

    safety = evaluation.get("safety", {})
    if any(bool(safety.get(key)) for key in (
        "C1_C2_accessed",
        "C3_accessed",
        "protected_reserve_accessed",
        "network_accessed",
        "paper_execution",
        "demo_execution",
        "real_money_execution",
        "orders_submitted",
    )):
        raise RuntimeError("safety boundary violated")

    print("Conditional-alpha v2 development result validation: PASS")
    print(f"overall_status={evaluation['overall_status']}")
    print(f"evaluation_fingerprint={supplied_eval}")
    print(f"receipt_fingerprint={supplied_receipt}")
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

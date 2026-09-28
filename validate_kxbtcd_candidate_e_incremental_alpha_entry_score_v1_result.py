"""Validate a persisted incremental-alpha entry score v1 result."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import canonical_sha256
from src.kxbtcd_candidate_e_incremental_alpha_entry_score_v1 import (
    BETA_GRID,
    BETA_SCORE_FIELDS,
    BETA_SCORE_SCHEMA,
    DIAGNOSTIC_ID,
    EXPECTED_PREDECLARATION_FINGERPRINT,
    EXPECTED_PARENT_RESULT_FINGERPRINT,
    EXPECTED_PARENT_RECEIPT_FINGERPRINT,
    RECEIPT_SCHEMA,
    RESULT_SCHEMA,
    SELECTED_COUNT,
    sha256_file,
)


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--result", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--beta-scores", required=True)
    return p


def main():
    args = parser().parse_args()
    result_path = Path(args.result)
    receipt_path = Path(args.receipt)
    score_path = Path(args.beta_scores)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if result.get("schema_version") != RESULT_SCHEMA:
        raise RuntimeError("result schema mismatch")
    if result.get("diagnostic_id") != DIAGNOSTIC_ID:
        raise RuntimeError("result diagnostic ID mismatch")
    if result.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        raise RuntimeError("predeclaration fingerprint mismatch")
    if result.get("parent_result_fingerprint") != EXPECTED_PARENT_RESULT_FINGERPRINT:
        raise RuntimeError("parent result fingerprint mismatch")
    if result.get("parent_receipt_fingerprint") != EXPECTED_PARENT_RECEIPT_FINGERPRINT:
        raise RuntimeError("parent receipt fingerprint mismatch")
    if result.get("population_entry_count") != 512:
        raise RuntimeError("population entry count mismatch")
    if result.get("selection_count_per_beta") != SELECTED_COUNT:
        raise RuntimeError("selected count mismatch")
    if tuple(float(x) for x in result.get("beta_grid", ())) != BETA_GRID:
        raise RuntimeError("beta grid mismatch")
    if result.get("coverage_search_performed") is not False:
        raise RuntimeError("coverage search occurred")
    if result.get("absolute_threshold_search_performed") is not False:
        raise RuntimeError("absolute threshold search occurred")
    if result.get("strategy_pass") is not False:
        raise RuntimeError("exploratory result cannot pass a strategy")

    copy_result = dict(result)
    supplied_result = copy_result.pop("result_fingerprint")
    if canonical_sha256(copy_result) != supplied_result:
        raise RuntimeError("result fingerprint mismatch")

    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise RuntimeError("receipt schema mismatch")
    if receipt.get("diagnostic_id") != DIAGNOSTIC_ID:
        raise RuntimeError("receipt diagnostic mismatch")
    if receipt.get("result_fingerprint") != supplied_result:
        raise RuntimeError("receipt/result fingerprint mismatch")
    copy_receipt = dict(receipt)
    supplied_receipt = copy_receipt.pop("receipt_fingerprint")
    if canonical_sha256(copy_receipt) != supplied_receipt:
        raise RuntimeError("receipt fingerprint mismatch")
    if receipt["output_sha256s"]["result_sha256"] != sha256_file(result_path):
        raise RuntimeError("result SHA mismatch")
    if receipt["output_sha256s"]["beta_scores_sha256"] != sha256_file(score_path):
        raise RuntimeError("beta score SHA mismatch")

    with score_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != BETA_SCORE_FIELDS:
            raise RuntimeError("beta score fields changed")
        rows = list(reader)

    if len(rows) != 512 * len(BETA_GRID):
        raise RuntimeError("beta score row count changed")
    for beta in BETA_GRID:
        beta_rows = [r for r in rows if float(r["beta"]) == beta]
        if len(beta_rows) != 512:
            raise RuntimeError(f"beta {beta} population count changed")
        selected = [r for r in beta_rows if r["selected"] == "true"]
        if len(selected) != SELECTED_COUNT:
            raise RuntimeError(f"beta {beta} selected count changed")
        if any(r["schema_version"] != BETA_SCORE_SCHEMA for r in beta_rows):
            raise RuntimeError("beta score schema mismatch")
        if any(r["diagnostic_id"] != DIAGNOSTIC_ID for r in beta_rows):
            raise RuntimeError("beta score diagnostic mismatch")

    safety = result.get("safety", {})
    for key in (
        "C1_C2_accessed",
        "C3_accessed",
        "protected_reserve_accessed",
        "network_accessed",
        "paper_execution",
        "demo_execution",
        "real_money_execution",
        "orders_submitted",
    ):
        if safety.get(key) is not False:
            raise RuntimeError(f"safety boundary violated at {key}")

    gate = result["incremental_alpha_gate"]
    if gate["status"] not in {
        "INCREMENTAL_ALPHA_SIGNAL",
        "NO_INCREMENTAL_ALPHA_SIGNAL",
    }:
        raise RuntimeError("incremental-alpha gate status invalid")
    if gate["strategy_pass"] is not False:
        raise RuntimeError("incremental-alpha diagnostic cannot pass strategy")
    if gate["fresh_validation_claim"] is not False:
        raise RuntimeError("incremental-alpha diagnostic cannot claim fresh validation")

    print("Incremental alpha entry score v1 result validation: PASS")
    print(f"incremental_alpha_status={gate['status']}")
    print(f"selected_beta={result['selected_beta']}")
    print(f"result_fingerprint={supplied_result}")
    print(f"receipt_fingerprint={supplied_receipt}")
    print("strategy_pass=false")
    print("coverage_search_performed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

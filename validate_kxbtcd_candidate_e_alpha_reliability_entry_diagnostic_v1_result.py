"""Validate a persisted alpha-reliability entry diagnostic v1 result."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import canonical_sha256
from src.kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1 import (
    DECISION_FIELDS,
    DIAGNOSTIC_ID,
    EXPECTED_PARENT_EVALUATION_FINGERPRINT,
    EXPECTED_PARENT_RECEIPT_FINGERPRINT,
    EXPECTED_PREDECLARATION_FINGERPRINT,
    RECEIPT_SCHEMA,
    RESULT_SCHEMA,
    sha256_file,
)


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--result", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--decisions", required=True)
    return p


def main():
    args = parser().parse_args()
    result_path = Path(args.result)
    receipt_path = Path(args.receipt)
    decisions_path = Path(args.decisions)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if result.get("schema_version") != RESULT_SCHEMA:
        raise RuntimeError("diagnostic result schema mismatch")
    if result.get("diagnostic_id") != DIAGNOSTIC_ID:
        raise RuntimeError("diagnostic result ID mismatch")
    if result.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        raise RuntimeError("predeclaration fingerprint mismatch")
    if result.get("parent_evaluation_fingerprint") != EXPECTED_PARENT_EVALUATION_FINGERPRINT:
        raise RuntimeError("parent evaluation fingerprint mismatch")
    if result.get("parent_receipt_fingerprint") != EXPECTED_PARENT_RECEIPT_FINGERPRINT:
        raise RuntimeError("parent receipt fingerprint mismatch")
    if result.get("candidate_e_remains_valuation_probability") is not True:
        raise RuntimeError("Candidate E valuation boundary changed")
    if result.get("conditional_alpha_role") != "ranking_only":
        raise RuntimeError("alpha role changed")
    if result.get("threshold_search_performed") is not False:
        raise RuntimeError("threshold search occurred")

    copy_result = dict(result)
    supplied_result = copy_result.pop("result_fingerprint")
    if canonical_sha256(copy_result) != supplied_result:
        raise RuntimeError("result fingerprint mismatch")

    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise RuntimeError("diagnostic receipt schema mismatch")
    if receipt.get("diagnostic_id") != DIAGNOSTIC_ID:
        raise RuntimeError("diagnostic receipt ID mismatch")
    if receipt.get("result_fingerprint") != supplied_result:
        raise RuntimeError("receipt/result fingerprint mismatch")
    copy_receipt = dict(receipt)
    supplied_receipt = copy_receipt.pop("receipt_fingerprint")
    if canonical_sha256(copy_receipt) != supplied_receipt:
        raise RuntimeError("receipt fingerprint mismatch")

    if receipt["output_sha256s"]["result_sha256"] != sha256_file(result_path):
        raise RuntimeError("result SHA mismatch")
    if receipt["output_sha256s"]["decisions_sha256"] != sha256_file(decisions_path):
        raise RuntimeError("decision SHA mismatch")

    with decisions_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != DECISION_FIELDS:
            raise RuntimeError("decision CSV fields changed")
        rows = list(reader)
    if len(rows) != 1500:
        raise RuntimeError("decision event count changed")

    safety = result.get("safety", {})
    if safety.get("H1_economic_scoring") is not False:
        raise RuntimeError("H1 economic scoring occurred")
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

    if result["triage"]["strategy_pass"] is not False:
        raise RuntimeError("exploratory diagnostic cannot pass a strategy")
    if result["triage"]["fresh_validation_claim"] is not False:
        raise RuntimeError("exploratory diagnostic cannot claim fresh validation")

    print("Alpha-reliability entry diagnostic v1 result validation: PASS")
    print(f"triage_label={result['triage']['label']}")
    print(f"result_fingerprint={supplied_result}")
    print(f"receipt_fingerprint={supplied_receipt}")
    print("strategy_pass=false")
    print("threshold_search_performed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

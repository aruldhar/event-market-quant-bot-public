"""Run the frozen incremental Candidate-E edge + alpha entry score diagnostic.

Closeout-locked: real H2/H3 incremental-score economics are not allowed until
Checkpoint 21N-N-C-B has itself been safely closed and pushed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_incremental_alpha_entry_score_v1 import (
    BETA_SCORE_FIELDS,
    build_diagnostic_result,
    build_receipt,
    read_csv,
    sha256_file,
    validate_c_b_closeout_receipt,
    validate_parent_artifacts,
    validate_predeclaration,
    write_csv,
)


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--c-b-closeout-receipt", default="docs/LAST_CHECKPOINT_CLOSEOUT.json")
    p.add_argument(
        "--predeclaration",
        default="configs/kxbtcd_candidate_e_incremental_alpha_entry_score_v1_predeclaration.json",
    )
    p.add_argument("--parent-result", required=True)
    p.add_argument("--parent-receipt", required=True)
    p.add_argument("--parent-decisions", required=True)
    p.add_argument("--output-dir", required=True)
    return p


def main():
    args = parser().parse_args()
    validate_c_b_closeout_receipt(args.c_b_closeout_receipt)
    validate_predeclaration(args.predeclaration)

    decisions = read_csv(args.parent_decisions)
    validate_parent_artifacts(
        result_path=args.parent_result,
        receipt_path=args.parent_receipt,
        decisions_path=args.parent_decisions,
        decision_rows=decisions,
        enforce_frozen_counts=True,
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    result_path = out / "incremental_alpha_entry_score_result.json"
    score_path = out / "incremental_alpha_entry_score_beta_scores.csv"
    receipt_path = out / "incremental_alpha_entry_score_receipt.json"

    result, score_rows = build_diagnostic_result(
        decisions,
        enforce_frozen_counts=True,
    )
    write_csv(score_path, BETA_SCORE_FIELDS, score_rows)
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = build_receipt(
        result=result,
        result_path=result_path,
        score_path=score_path,
        input_hashes={
            "predeclaration": sha256_file(args.predeclaration),
            "parent_result": sha256_file(args.parent_result),
            "parent_receipt": sha256_file(args.parent_receipt),
            "parent_decisions": sha256_file(args.parent_decisions),
        },
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"incremental_alpha_status={result['incremental_alpha_gate']['status']}")
    print(f"selected_beta={result['selected_beta']}")
    print(f"result_fingerprint={result['result_fingerprint']}")
    print(f"receipt_fingerprint={receipt['receipt_fingerprint']}")
    print("strategy_pass=false")
    print("coverage_search_performed=false")
    print("absolute_threshold_search_performed=false")
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

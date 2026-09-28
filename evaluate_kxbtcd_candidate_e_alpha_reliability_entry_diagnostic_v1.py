"""Run the frozen Candidate-E alpha-reliability entry diagnostic v1.

The command is intentionally unusable until Checkpoint 21N-N-B has itself been
safely closed and pushed. It consumes only the already-generated selected-lambda
rolling-origin H2/H3 conditional-alpha predictions plus their validated parent
evaluation/receipt. It performs no network or execution action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1 import (
    DECISION_FIELDS,
    build_diagnostic_result,
    build_receipt,
    read_csv,
    sha256_file,
    validate_n_b_closeout_receipt,
    validate_parent_result,
    validate_predeclaration,
    write_csv,
)


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--n-b-closeout-receipt", default="docs/LAST_CHECKPOINT_CLOSEOUT.json")
    p.add_argument(
        "--predeclaration",
        default="configs/kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_predeclaration.json",
    )
    p.add_argument("--parent-evaluation", required=True)
    p.add_argument("--parent-receipt", required=True)
    p.add_argument("--rolling-predictions", required=True)
    p.add_argument("--output-dir", required=True)
    return p


def main():
    args = parser().parse_args()
    validate_n_b_closeout_receipt(args.n_b_closeout_receipt)
    validate_predeclaration(args.predeclaration)

    rows = read_csv(args.rolling_predictions)
    validate_parent_result(
        evaluation_path=args.parent_evaluation,
        receipt_path=args.parent_receipt,
        prediction_path=args.rolling_predictions,
        prediction_rows=rows,
        enforce_frozen_counts=True,
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    decision_path = out / "alpha_reliability_entry_diagnostic_decisions.csv"
    result_path = out / "alpha_reliability_entry_diagnostic_result.json"
    receipt_path = out / "alpha_reliability_entry_diagnostic_receipt.json"

    result, decisions = build_diagnostic_result(rows, enforce_frozen_counts=True)
    write_csv(decision_path, DECISION_FIELDS, decisions)
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = build_receipt(
        result=result,
        result_path=result_path,
        decision_path=decision_path,
        input_hashes={
            "predeclaration": sha256_file(args.predeclaration),
            "parent_evaluation": sha256_file(args.parent_evaluation),
            "parent_receipt": sha256_file(args.parent_receipt),
            "rolling_predictions": sha256_file(args.rolling_predictions),
        },
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"triage_label={result['triage']['label']}")
    print(f"result_fingerprint={result['result_fingerprint']}")
    print(f"receipt_fingerprint={receipt['receipt_fingerprint']}")
    print(f"candidate_e_entry_count={result['reporting']['pooled']['baseline']['entry_count']}")
    print("strategy_pass=false")
    print("threshold_search_performed=false")
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

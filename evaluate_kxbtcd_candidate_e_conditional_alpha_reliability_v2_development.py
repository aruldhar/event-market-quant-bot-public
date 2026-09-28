"""Run the frozen conditional-alpha v2 H-development evaluation.

This command is intentionally unusable until Checkpoint 21N-M-C itself has been
safely closed and pushed. It uses only already-exposed H1_OOF/H2/H3 evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v2_development import (
    ConditionalAlphaV2FitContractError,
    ENTRY_DECISION_FIELDS,
    ROLLING_PREDICTION_FIELDS,
    build_development_evaluation,
    build_failure_receipt,
    build_optimizer_failure_evaluation,
    build_result_receipt,
    project_development_labels,
    read_csv,
    sha256_file,
    validate_j_b_bindings,
    validate_label_source_hashes,
    validate_m_c_closeout_receipt,
    write_csv,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--m-c-closeout-receipt", default="docs/LAST_CHECKPOINT_CLOSEOUT.json")
    p.add_argument("--prepared-feature-rows", required=True)
    p.add_argument("--preparation-freeze", required=True)
    p.add_argument(
        "--preparation-closeout",
        default="configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_preparation_closeout.json",
    )
    p.add_argument("--h1-predictions", required=True)
    p.add_argument("--h2-predictions", required=True)
    p.add_argument("--h3-predictions", required=True)
    p.add_argument("--output-dir", required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    validate_m_c_closeout_receipt(args.m_c_closeout_receipt)

    feature_rows = read_csv(args.prepared_feature_rows)
    validate_j_b_bindings(
        feature_rows=feature_rows,
        feature_rows_path=args.prepared_feature_rows,
        preparation_freeze_path=args.preparation_freeze,
        preparation_closeout_path=args.preparation_closeout,
    )

    label_paths = {
        "H1_OOF": args.h1_predictions,
        "H2": args.h2_predictions,
        "H3": args.h3_predictions,
    }
    validate_label_source_hashes(label_paths)
    label_sources = {stage: read_csv(path) for stage, path in label_paths.items()}
    labels = project_development_labels(label_sources, enforce_frozen_counts=True)

    input_hashes = {
        "prepared_feature_rows": sha256_file(args.prepared_feature_rows),
        "preparation_freeze": sha256_file(args.preparation_freeze),
        "preparation_closeout": sha256_file(args.preparation_closeout),
        "H1_OOF_predictions": sha256_file(args.h1_predictions),
        "H2_predictions": sha256_file(args.h2_predictions),
        "H3_predictions": sha256_file(args.h3_predictions),
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    prediction_path = out / "conditional_alpha_v2_rolling_origin_predictions.csv"
    entry_path = out / "conditional_alpha_v2_entry_decisions.csv"
    evaluation_path = out / "conditional_alpha_v2_development_evaluation.json"
    receipt_path = out / "conditional_alpha_v2_development_receipt.json"

    try:
        evaluation, predictions, entries = build_development_evaluation(
            feature_rows,
            labels,
            enforce_frozen_counts=True,
        )
    except ConditionalAlphaV2FitContractError as failure:
        evaluation = build_optimizer_failure_evaluation(
            feature_rows=feature_rows,
            label_rows=labels,
            failure=failure,
        )
        evaluation_path.write_text(
            json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt = build_failure_receipt(
            evaluation=evaluation,
            evaluation_path=evaluation_path,
            input_hashes=input_hashes,
        )
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"overall_status={evaluation['overall_status']}")
        print("selected_lambda=NOT_SELECTED")
        print(f"evaluation_fingerprint={evaluation['evaluation_fingerprint']}")
        print(f"receipt_fingerprint={receipt['receipt_fingerprint']}")
        print(f"failure_phase={evaluation['failure']['phase']}")
        print(f"failure_lambda={evaluation['failure']['lambda']}")
        print(f"failure_fold={evaluation['failure']['fold']}")
        print(f"failure_message={evaluation['failure']['original_exception_message']}")
        print(f"probability_gate={evaluation['probability_gate']['status']}")
        print(f"economic_gate={evaluation['economic_gate']['status']}")
        print("full_development_fit_performed=false")
        print("C1_C2_accessed=false")
        print("C3_accessed=false")
        print("protected_reserve_accessed=false")
        print("network_accessed=false")
        print("execution_enabled=false")
        return 0

    write_csv(prediction_path, ROLLING_PREDICTION_FIELDS, predictions)
    entry_written = None
    if entries:
        write_csv(entry_path, ENTRY_DECISION_FIELDS, entries)
        entry_written = entry_path

    evaluation_path.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = build_result_receipt(
        evaluation=evaluation,
        prediction_path=prediction_path,
        entry_path=entry_written,
        evaluation_path=evaluation_path,
        input_hashes=input_hashes,
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"overall_status={evaluation['overall_status']}")
    print(f"selected_lambda={evaluation['selected_lambda']}")
    print(f"evaluation_fingerprint={evaluation['evaluation_fingerprint']}")
    print(f"receipt_fingerprint={receipt['receipt_fingerprint']}")
    print(f"probability_gate={evaluation['probability_gate']['status']}")
    print(f"economic_gate={evaluation['economic_gate']['status']}")
    print(
        "full_development_fit_performed="
        + str(evaluation["full_development_fit"] is not None).lower()
    )
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

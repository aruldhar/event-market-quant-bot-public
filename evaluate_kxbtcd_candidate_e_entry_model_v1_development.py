"""Run the frozen Checkpoint-21M Model-2 development evaluation.

Authorized evidence only: accepted frozen H1_OOF/H2/H3 features and their
already-exposed Candidate-E outcome rows. No C1/C2/C3/reserve/economics/execution.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from src.kxbtcd_candidate_e_entry_model_v1_development import (
    DEVELOPMENT_RECEIPT_SCHEMA,
    EXPECTED_PREPARATION_FINGERPRINT,
    build_development_evaluation,
    evaluation_fingerprint,
    load_json,
    project_exposed_development_labels,
    sha256_file,
    validate_preparation_binding,
)


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_lambda_scores(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ("lambda", "pooled_event_equal_log_loss", "pooled_event_equal_brier")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-rows", required=True)
    parser.add_argument("--preparation-freeze", required=True)
    parser.add_argument("--h1-predictions", required=True)
    parser.add_argument("--h2-predictions", required=True)
    parser.add_argument("--h3-predictions", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    feature_path = Path(args.feature_rows)
    freeze_path = Path(args.preparation_freeze)
    label_paths = {
        "H1_OOF": Path(args.h1_predictions),
        "H2": Path(args.h2_predictions),
        "H3": Path(args.h3_predictions),
    }
    for path in (feature_path, freeze_path, *label_paths.values()):
        if not path.is_file():
            raise RuntimeError(f"required input file missing: {path}")

    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise RuntimeError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    feature_rows = read_csv(feature_path)
    freeze = load_json(freeze_path)
    sources = {stage: read_csv(path) for stage, path in label_paths.items()}
    repo_root = Path(__file__).resolve().parent
    validate_preparation_binding(
        feature_rows,
        freeze,
        feature_rows_path=feature_path,
        label_source_paths=label_paths,
        repo_root=repo_root,
    )
    labels = project_exposed_development_labels(sources, enforce_frozen_counts=True)
    evaluation = build_development_evaluation(feature_rows, labels, enforce_frozen_counts=True)

    evaluation_path = out / "candidate_e_entry_model_v1_development_evaluation.json"
    lambda_path = out / "candidate_e_entry_model_v1_development_lambda_scores.csv"
    receipt_path = out / "candidate_e_entry_model_v1_development_receipt.json"
    write_json(evaluation_path, evaluation)
    write_lambda_scores(lambda_path, evaluation["lambda_scores"])

    receipt = {
        "schema_version": DEVELOPMENT_RECEIPT_SCHEMA,
        "model_id": evaluation["model_id"],
        "preparation_fingerprint": EXPECTED_PREPARATION_FINGERPRINT,
        "evaluation_fingerprint": evaluation_fingerprint(evaluation),
        "selected_lambda": evaluation["selected_lambda"],
        "development_feature_rows": evaluation["development_feature_rows"],
        "development_events": evaluation["development_events"],
        "source_sha256s": {
            "feature_rows": sha256_file(feature_path),
            "preparation_freeze": sha256_file(freeze_path),
            "h1_predictions": sha256_file(label_paths["H1_OOF"]),
            "h2_predictions": sha256_file(label_paths["H2"]),
            "h3_predictions": sha256_file(label_paths["H3"]),
        },
        "implementation_sha256s": {
            "src/kxbtcd_candidate_e_entry_model_v1.py": sha256_file(repo_root / "src/kxbtcd_candidate_e_entry_model_v1.py"),
            "src/kxbtcd_candidate_e_entry_model_v1_development.py": sha256_file(repo_root / "src/kxbtcd_candidate_e_entry_model_v1_development.py"),
            "evaluate_kxbtcd_candidate_e_entry_model_v1_development.py": sha256_file(Path(__file__)),
        },
        "output_sha256s": {
            "evaluation": sha256_file(evaluation_path),
            "lambda_scores": sha256_file(lambda_path),
        },
        "safety": evaluation["safety"],
    }
    write_json(receipt_path, receipt)

    pooled = evaluation["selected_rolling_origin_diagnostics"]["pooled_H2_H3"]
    print("Candidate-E Entry Model v1 development evaluation: COMPLETE")
    print(f"feature_rows={evaluation['development_feature_rows']}")
    print(f"events={evaluation['development_events']}")
    print(f"selected_lambda={evaluation['selected_lambda']}")
    print(f"selected_model2_pooled_log_loss={pooled['model2_event_equal_log_loss']}")
    print(f"candidate_e_pooled_log_loss={pooled['candidate_e_event_equal_log_loss']}")
    print(f"candidate_e_minus_model2_log_loss={pooled['candidate_e_minus_model2_log_loss']}")
    print(f"evaluation_fingerprint={receipt['evaluation_fingerprint']}")
    print("c1_c2_opened_for_model2=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

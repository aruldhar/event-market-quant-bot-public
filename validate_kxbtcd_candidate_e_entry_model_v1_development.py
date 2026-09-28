"""Independent persisted-result validator for Model-2 development evaluation."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-rows", required=True)
    parser.add_argument("--preparation-freeze", required=True)
    parser.add_argument("--h1-predictions", required=True)
    parser.add_argument("--h2-predictions", required=True)
    parser.add_argument("--h3-predictions", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--lambda-scores", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    feature_path = Path(args.feature_rows)
    freeze_path = Path(args.preparation_freeze)
    label_paths = {
        "H1_OOF": Path(args.h1_predictions),
        "H2": Path(args.h2_predictions),
        "H3": Path(args.h3_predictions),
    }
    evaluation_path = Path(args.evaluation)
    lambda_path = Path(args.lambda_scores)
    receipt_path = Path(args.receipt)
    for path in (feature_path, freeze_path, *label_paths.values(), evaluation_path, lambda_path, receipt_path):
        if not path.is_file():
            raise RuntimeError(f"required validation file missing: {path}")

    feature_rows = read_csv(feature_path)
    freeze = load_json(freeze_path)
    sources = {stage: read_csv(path) for stage, path in label_paths.items()}
    persisted_evaluation = load_json(evaluation_path)
    receipt = load_json(receipt_path)
    repo_root = Path(__file__).resolve().parent

    validate_preparation_binding(
        feature_rows,
        freeze,
        feature_rows_path=feature_path,
        label_source_paths=label_paths,
        repo_root=repo_root,
    )
    labels = project_exposed_development_labels(sources, enforce_frozen_counts=True)
    recomputed = build_development_evaluation(feature_rows, labels, enforce_frozen_counts=True)
    if recomputed != persisted_evaluation:
        raise RuntimeError("persisted development evaluation does not equal deterministic recomputation")

    if receipt.get("schema_version") != DEVELOPMENT_RECEIPT_SCHEMA:
        raise RuntimeError("development receipt schema mismatch")
    if receipt.get("preparation_fingerprint") != EXPECTED_PREPARATION_FINGERPRINT:
        raise RuntimeError("development receipt preparation fingerprint mismatch")
    fingerprint = evaluation_fingerprint(recomputed)
    if receipt.get("evaluation_fingerprint") != fingerprint:
        raise RuntimeError("development evaluation fingerprint mismatch")
    if receipt.get("selected_lambda") != recomputed.get("selected_lambda"):
        raise RuntimeError("development receipt selected lambda mismatch")

    output_hashes = receipt.get("output_sha256s", {})
    if sha256_file(evaluation_path) != output_hashes.get("evaluation"):
        raise RuntimeError("persisted evaluation file hash mismatch")
    if sha256_file(lambda_path) != output_hashes.get("lambda_scores"):
        raise RuntimeError("persisted lambda-score file hash mismatch")

    source_hashes = receipt.get("source_sha256s", {})
    expected_sources = {
        "feature_rows": feature_path,
        "preparation_freeze": freeze_path,
        "h1_predictions": label_paths["H1_OOF"],
        "h2_predictions": label_paths["H2"],
        "h3_predictions": label_paths["H3"],
    }
    for key, path in expected_sources.items():
        if sha256_file(path) != source_hashes.get(key):
            raise RuntimeError(f"development receipt source hash mismatch: {key}")

    implementation_hashes = receipt.get("implementation_sha256s", {})
    implementation_paths = {
        "src/kxbtcd_candidate_e_entry_model_v1.py": repo_root / "src/kxbtcd_candidate_e_entry_model_v1.py",
        "src/kxbtcd_candidate_e_entry_model_v1_development.py": repo_root / "src/kxbtcd_candidate_e_entry_model_v1_development.py",
        "evaluate_kxbtcd_candidate_e_entry_model_v1_development.py": repo_root / "evaluate_kxbtcd_candidate_e_entry_model_v1_development.py",
    }
    for key, path in implementation_paths.items():
        if sha256_file(path) != implementation_hashes.get(key):
            raise RuntimeError(f"development implementation hash mismatch: {key}")

    with lambda_path.open("r", encoding="utf-8", newline="") as handle:
        lambda_rows = list(csv.DictReader(handle))
    if len(lambda_rows) != len(recomputed["lambda_scores"]):
        raise RuntimeError("lambda-score CSV row count mismatch")
    for persisted, expected in zip(lambda_rows, recomputed["lambda_scores"]):
        if float(persisted["lambda"]) != float(expected["lambda"]):
            raise RuntimeError("lambda-score CSV lambda mismatch")
        if float(persisted["pooled_event_equal_log_loss"]) != float(expected["pooled_event_equal_log_loss"]):
            raise RuntimeError("lambda-score CSV log-loss mismatch")
        if float(persisted["pooled_event_equal_brier"]) != float(expected["pooled_event_equal_brier"]):
            raise RuntimeError("lambda-score CSV Brier mismatch")

    required_false = (
        "c1_c2_opened_for_model2",
        "c3_opened_for_model2",
        "protected_reserve_accessed",
        "strategy_v1_pnl_calculated",
        "execution_enabled",
    )
    for key in required_false:
        if recomputed["safety"].get(key) is not False or receipt.get("safety", {}).get(key) is not False:
            raise RuntimeError(f"development safety flag changed: {key}")

    pooled = recomputed["selected_rolling_origin_diagnostics"]["pooled_H2_H3"]
    print("Candidate-E Entry Model v1 development validation: PASS")
    print(f"feature_rows={recomputed['development_feature_rows']}")
    print(f"events={recomputed['development_events']}")
    print(f"selected_lambda={recomputed['selected_lambda']}")
    print(f"selected_model2_pooled_log_loss={pooled['model2_event_equal_log_loss']}")
    print(f"candidate_e_pooled_log_loss={pooled['candidate_e_event_equal_log_loss']}")
    print(f"candidate_e_minus_model2_log_loss={pooled['candidate_e_minus_model2_log_loss']}")
    print(f"evaluation_fingerprint={fingerprint}")
    print("deterministic_recomputation=pass")
    print("c1_c2_opened_for_model2=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

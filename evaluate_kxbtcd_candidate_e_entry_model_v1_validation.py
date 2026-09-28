from __future__ import annotations

import argparse
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1_validation import (
    ATTEMPT_SCHEMA,
    BLOCK_SCORE_FIELDS,
    C1_OUTCOMES_SHA256,
    C2_OUTCOMES_SHA256,
    DEPENDENCY_FILES,
    EVENT_SCORE_FIELDS,
    IMPLEMENTATION_FILES,
    SCORED_ROW_FIELDS,
    build_receipt,
    evaluate_validation,
    read_csv,
    read_json,
    sha256_file,
    validate_implementation_freeze_document,
    validate_result_closeout,
    write_csv,
    write_json,
)
from src.kxbtcd_candidate_e_entry_model_v1 import canonical_sha256

FEATURE_NAME = "candidate_e_entry_model_v1_validation_features.csv"
OFFSET_NAME = "candidate_e_entry_model_v1_validation_offsets.csv"
EVENT_MAP_NAME = "candidate_e_entry_model_v1_validation_event_map.csv"
PREPARATION_FREEZE_NAME = (
    "candidate_e_entry_model_v1_validation_preparation_freeze.json"
)

def initialize_attempt(
    *,
    path: Path,
    implementation_fingerprint: str,
    preparation_fingerprint: str,
    output_dir: Path,
    resume: bool,
) -> dict:
    contract = {
        "schema_version": ATTEMPT_SCHEMA,
        "model_id": "kxbtcd_candidate_e_entry_residual_logistic.v1",
        "validation_implementation_fingerprint": implementation_fingerprint,
        "validation_preparation_fingerprint": preparation_fingerprint,
        "c1_outcomes_sha256": C1_OUTCOMES_SHA256,
        "c2_outcomes_sha256": C2_OUTCOMES_SHA256,
        "output_dir": str(output_dir),
    }

    if path.exists():
        existing = read_json(path)
        for key, value in contract.items():
            if existing.get(key) != value:
                raise RuntimeError(
                    f"existing Model-2 validation attempt contract changed at {key}"
                )
        if existing.get("status") == "COMPLETE":
            raise RuntimeError(
                "Model-2 C1+C2 validation is already complete; fresh rescore prohibited"
            )
        if not resume:
            raise RuntimeError(
                "Model-2 validation outcomes were already marked opened. "
                "Use --resume only with this unchanged frozen implementation."
            )
        return existing

    if resume:
        raise RuntimeError("--resume requested but no validation attempt exists")

    document = dict(contract)
    document.update(
        {
            "status": "OUTCOMES_OPENED_FOR_MODEL2_VALIDATION",
            "c1_c2_outcomes_opened_for_model2": True,
            "c3_opened_for_model2": False,
            "protected_reserve_accessed": False,
            "strategy_v1_pnl_calculated": False,
            "execution_enabled": False,
        }
    )
    write_json(path, document)
    return document

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-dir", required=True)
    parser.add_argument("--development-freeze", required=True)
    parser.add_argument("--implementation-freeze", required=True)
    parser.add_argument("--c1-result-closeout", required=True)
    parser.add_argument("--c2-result-closeout", required=True)
    parser.add_argument("--c1-outcomes", required=True)
    parser.add_argument("--c2-outcomes", required=True)
    parser.add_argument("--attempt-path", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    implementation_hashes = {
        relative: sha256_file(relative)
        for relative in IMPLEMENTATION_FILES
    }
    dependency_hashes = {
        relative: sha256_file(relative)
        for relative in DEPENDENCY_FILES
    }
    implementation_freeze = read_json(args.implementation_freeze)
    validate_implementation_freeze_document(
        implementation_freeze,
        implementation_sha256s=implementation_hashes,
        dependency_sha256s=dependency_hashes,
    )
    implementation_fingerprint = implementation_freeze[
        "validation_implementation_fingerprint"
    ]

    prepared = Path(args.prepared_dir)
    feature_path = prepared / FEATURE_NAME
    offset_path = prepared / OFFSET_NAME
    event_map_path = prepared / EVENT_MAP_NAME
    preparation_freeze_path = prepared / PREPARATION_FREEZE_NAME

    preparation_freeze = read_json(preparation_freeze_path)
    preparation_fingerprint = preparation_freeze[
        "validation_preparation_fingerprint"
    ]

    c1_closeout = read_json(args.c1_result_closeout)
    c2_closeout = read_json(args.c2_result_closeout)
    validate_result_closeout(c1_closeout, stage="C1")
    validate_result_closeout(c2_closeout, stage="C2")

    c1_outcomes_path = Path(args.c1_outcomes)
    c2_outcomes_path = Path(args.c2_outcomes)
    if sha256_file(c1_outcomes_path) != C1_OUTCOMES_SHA256:
        raise RuntimeError("C1 outcome SHA-256 mismatch")
    if sha256_file(c2_outcomes_path) != C2_OUTCOMES_SHA256:
        raise RuntimeError("C2 outcome SHA-256 mismatch")

    out_dir = Path(args.out_dir)
    attempt_path = Path(args.attempt_path)
    attempt = initialize_attempt(
        path=attempt_path,
        implementation_fingerprint=implementation_fingerprint,
        preparation_fingerprint=preparation_fingerprint,
        output_dir=out_dir,
        resume=args.resume,
    )

    # First real Model-2 C1/C2 row-label read occurs only after the attempt
    # journal above permanently marks this evidence as opened.
    c1_outcomes = read_csv(c1_outcomes_path)
    c2_outcomes = read_csv(c2_outcomes_path)

    scored, event_scores, block_scores, summary = evaluate_validation(
        feature_rows=read_csv(feature_path),
        offset_rows=read_csv(offset_path),
        event_map_rows=read_csv(event_map_path),
        c1_outcome_rows=c1_outcomes,
        c2_outcome_rows=c2_outcomes,
        development_freeze=read_json(args.development_freeze),
        preparation_freeze=preparation_freeze,
        implementation_fingerprint=implementation_fingerprint,
    )

    if out_dir.exists() and not args.resume:
        raise RuntimeError(f"validation output directory already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    scored_path = out_dir / "validation_scored_rows.csv"
    event_path = out_dir / "validation_event_scores.csv"
    block_path = out_dir / "validation_block_scores.csv"
    summary_path = out_dir / "validation_summary.json"
    receipt_path = out_dir / "validation_receipt.json"

    write_csv(scored_path, SCORED_ROW_FIELDS, scored)
    write_csv(event_path, EVENT_SCORE_FIELDS, event_scores)
    write_csv(block_path, BLOCK_SCORE_FIELDS, block_scores)
    write_json(summary_path, summary)

    source_hashes = {
        "feature_rows": sha256_file(feature_path),
        "offset_rows": sha256_file(offset_path),
        "event_map": sha256_file(event_map_path),
        "preparation_freeze": sha256_file(preparation_freeze_path),
        "development_freeze": sha256_file(args.development_freeze),
        "implementation_freeze": sha256_file(args.implementation_freeze),
        "c1_result_closeout": sha256_file(args.c1_result_closeout),
        "c2_result_closeout": sha256_file(args.c2_result_closeout),
        "c1_outcomes": sha256_file(c1_outcomes_path),
        "c2_outcomes": sha256_file(c2_outcomes_path),
    }
    output_hashes = {
        "scored_rows": sha256_file(scored_path),
        "event_scores": sha256_file(event_path),
        "block_scores": sha256_file(block_path),
        "summary": sha256_file(summary_path),
    }
    receipt = build_receipt(
        summary=summary,
        source_sha256s=source_hashes,
        output_sha256s=output_hashes,
        implementation_fingerprint=implementation_fingerprint,
    )
    write_json(receipt_path, receipt)

    complete_attempt = dict(attempt)
    complete_attempt.update(
        {
            "status": "COMPLETE",
            "validation_evaluation_fingerprint": summary[
                "validation_evaluation_fingerprint"
            ],
            "validation_receipt_fingerprint": receipt[
                "validation_receipt_fingerprint"
            ],
            "validation_passed": summary["validation_passed"],
        }
    )
    write_json(attempt_path, complete_attempt)

    print("Candidate-E Entry Model v1 C1+C2 validation evaluation: COMPLETE")
    print("events=1000")
    print("rows=28894")
    print(
        "candidate_e_event_equal_log_loss="
        + str(summary["candidate_e_event_equal_log_loss"])
    )
    print(
        "model2_event_equal_log_loss="
        + str(summary["model2_event_equal_log_loss"])
    )
    print(
        "candidate_e_minus_model2_log_loss="
        + str(summary["candidate_e_minus_model2_log_loss"])
    )
    print(
        "candidate_e_event_equal_brier="
        + str(summary["candidate_e_event_equal_brier"])
    )
    print(
        "model2_event_equal_brier="
        + str(summary["model2_event_equal_brier"])
    )
    print(
        "candidate_e_minus_model2_brier="
        + str(summary["candidate_e_minus_model2_brier"])
    )
    print(
        "median_event_candidate_e_minus_model2_log_loss="
        + str(summary["median_event_candidate_e_minus_model2_log_loss"])
    )
    print("block_log_loss_win_count=" + str(summary["block_log_loss_win_count"]))
    print(
        "newest_block_log_loss_win="
        + str(summary["newest_block_log_loss_win"]).lower()
    )
    print("validation_passed=" + str(summary["validation_passed"]).lower())
    print(
        "validation_evaluation_fingerprint="
        + summary["validation_evaluation_fingerprint"]
    )
    print(
        "validation_receipt_fingerprint="
        + receipt["validation_receipt_fingerprint"]
    )
    print("c1_c2_outcomes_opened_for_model2=true")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

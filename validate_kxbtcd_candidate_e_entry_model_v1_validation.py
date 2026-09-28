from __future__ import annotations

import argparse
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1_validation import (
    BLOCK_SCORE_FIELDS,
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
)
from src.kxbtcd_candidate_e_entry_model_v1 import canonical_rows_fingerprint

FEATURE_NAME = "candidate_e_entry_model_v1_validation_features.csv"
OFFSET_NAME = "candidate_e_entry_model_v1_validation_offsets.csv"
EVENT_MAP_NAME = "candidate_e_entry_model_v1_validation_event_map.csv"
PREPARATION_FREEZE_NAME = (
    "candidate_e_entry_model_v1_validation_preparation_freeze.json"
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-dir", required=True)
    parser.add_argument("--development-freeze", required=True)
    parser.add_argument("--implementation-freeze", required=True)
    parser.add_argument("--c1-result-closeout", required=True)
    parser.add_argument("--c2-result-closeout", required=True)
    parser.add_argument("--c1-outcomes", required=True)
    parser.add_argument("--c2-outcomes", required=True)
    parser.add_argument("--result-dir", required=True)
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

    c1_closeout = read_json(args.c1_result_closeout)
    c2_closeout = read_json(args.c2_result_closeout)
    validate_result_closeout(c1_closeout, stage="C1")
    validate_result_closeout(c2_closeout, stage="C2")

    prepared = Path(args.prepared_dir)
    feature_path = prepared / FEATURE_NAME
    offset_path = prepared / OFFSET_NAME
    event_map_path = prepared / EVENT_MAP_NAME
    preparation_freeze_path = prepared / PREPARATION_FREEZE_NAME

    scored, event_scores, block_scores, summary = evaluate_validation(
        feature_rows=read_csv(feature_path),
        offset_rows=read_csv(offset_path),
        event_map_rows=read_csv(event_map_path),
        c1_outcome_rows=read_csv(args.c1_outcomes),
        c2_outcome_rows=read_csv(args.c2_outcomes),
        development_freeze=read_json(args.development_freeze),
        preparation_freeze=read_json(preparation_freeze_path),
        implementation_fingerprint=implementation_fingerprint,
    )

    result_dir = Path(args.result_dir)
    persisted_scored = read_csv(result_dir / "validation_scored_rows.csv")
    persisted_events = read_csv(result_dir / "validation_event_scores.csv")
    persisted_blocks = read_csv(result_dir / "validation_block_scores.csv")
    persisted_summary = read_json(result_dir / "validation_summary.json")
    persisted_receipt = read_json(result_dir / "validation_receipt.json")

    if canonical_rows_fingerprint(persisted_scored) != canonical_rows_fingerprint(scored):
        raise RuntimeError("persisted scored rows differ from independent recomputation")
    if canonical_rows_fingerprint(
        persisted_events, key="event_ticker"
    ) != canonical_rows_fingerprint(event_scores, key="event_ticker"):
        raise RuntimeError("persisted event scores differ from independent recomputation")
    if canonical_rows_fingerprint(
        persisted_blocks, key="validation_block"
    ) != canonical_rows_fingerprint(block_scores, key="validation_block"):
        raise RuntimeError("persisted block scores differ from independent recomputation")
    if persisted_summary != summary:
        raise RuntimeError("persisted validation summary differs from independent recomputation")

    source_hashes = {
        "feature_rows": sha256_file(feature_path),
        "offset_rows": sha256_file(offset_path),
        "event_map": sha256_file(event_map_path),
        "preparation_freeze": sha256_file(preparation_freeze_path),
        "development_freeze": sha256_file(args.development_freeze),
        "implementation_freeze": sha256_file(args.implementation_freeze),
        "c1_result_closeout": sha256_file(args.c1_result_closeout),
        "c2_result_closeout": sha256_file(args.c2_result_closeout),
        "c1_outcomes": sha256_file(args.c1_outcomes),
        "c2_outcomes": sha256_file(args.c2_outcomes),
    }
    output_hashes = {
        "scored_rows": sha256_file(result_dir / "validation_scored_rows.csv"),
        "event_scores": sha256_file(result_dir / "validation_event_scores.csv"),
        "block_scores": sha256_file(result_dir / "validation_block_scores.csv"),
        "summary": sha256_file(result_dir / "validation_summary.json"),
    }
    expected_receipt = build_receipt(
        summary=summary,
        source_sha256s=source_hashes,
        output_sha256s=output_hashes,
        implementation_fingerprint=implementation_fingerprint,
    )
    if persisted_receipt != expected_receipt:
        raise RuntimeError("persisted validation receipt differs from independent derivation")

    print("Candidate-E Entry Model v1 C1+C2 validation independent validation: PASS")
    print("events=1000")
    print("rows=28894")
    print(
        "validation_passed="
        + str(summary["validation_passed"]).lower()
    )
    print(
        "validation_evaluation_fingerprint="
        + summary["validation_evaluation_fingerprint"]
    )
    print(
        "validation_receipt_fingerprint="
        + expected_receipt["validation_receipt_fingerprint"]
    )
    print("deterministic_recomputation=pass")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

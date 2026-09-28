from __future__ import annotations

import argparse
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1 import canonical_rows_fingerprint
from src.kxbtcd_candidate_e_entry_model_v1_materialization import read_csv
from src.kxbtcd_candidate_e_entry_model_v1_validation_preparation import (
    ARCHIVE_SHA256S,
    C1_PREOUTCOME_SHA256,
    C2_PREOUTCOME_SHA256,
    build_validation_event_map,
    build_validation_offset_rows,
    build_validation_preparation_freeze,
    materialize_validation_features,
    read_csv_filtered,
    read_json,
    read_preoutcome_csv_strict,
    sha256_file,
)

IMPLEMENTATION_PATHS = (
    "src/kxbtcd_candidate_e_entry_model_v1_validation_preparation.py",
    "prepare_kxbtcd_candidate_e_entry_model_v1_validation.py",
    "validate_kxbtcd_candidate_e_entry_model_v1_validation_preparation.py",
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c1-preoutcome", required=True)
    parser.add_argument("--c2-preoutcome", required=True)
    parser.add_argument("--champion-r0", required=True)
    parser.add_argument("--champion-r1", required=True)
    parser.add_argument("--development-freeze", required=True)
    parser.add_argument("--archive-allowlist", required=True)
    parser.add_argument("--archive-candles", required=True)
    parser.add_argument("--archive-trades", required=True)
    parser.add_argument("--prepared-dir", required=True)
    args = parser.parse_args()

    source_paths = {
        "c1_preoutcome": Path(args.c1_preoutcome),
        "c2_preoutcome": Path(args.c2_preoutcome),
        "champion_r0": Path(args.champion_r0),
        "champion_r1": Path(args.champion_r1),
        "development_freeze": Path(args.development_freeze),
        "archive_allowlist": Path(args.archive_allowlist),
        "archive_candles": Path(args.archive_candles),
        "archive_trades": Path(args.archive_trades),
    }
    expected_hashes = {
        "c1_preoutcome": C1_PREOUTCOME_SHA256,
        "c2_preoutcome": C2_PREOUTCOME_SHA256,
        **ARCHIVE_SHA256S,
    }
    for name, expected in expected_hashes.items():
        if sha256_file(source_paths[name]) != expected:
            raise RuntimeError(f"{name} SHA-256 mismatch")

    c1 = read_preoutcome_csv_strict(source_paths["c1_preoutcome"], expected_stage="C1")
    c2 = read_preoutcome_csv_strict(source_paths["c2_preoutcome"], expected_stage="C2")
    selected_markets = {row["market_ticker"] for row in [*c1, *c2]}

    feature_rows = materialize_validation_features(
        c1_preoutcome_rows=c1,
        c2_preoutcome_rows=c2,
        champion_r0=read_json(source_paths["champion_r0"]),
        champion_r1=read_json(source_paths["champion_r1"]),
        archive_allowlist_rows=read_csv_filtered(
            source_paths["archive_allowlist"], allowed_markets=selected_markets
        ),
        candle_rows=read_csv_filtered(
            source_paths["archive_candles"], allowed_markets=selected_markets
        ),
        trade_rows=read_csv_filtered(
            source_paths["archive_trades"], allowed_markets=selected_markets
        ),
    )
    offset_rows = build_validation_offset_rows(
        c1_preoutcome_rows=c1,
        c2_preoutcome_rows=c2,
        champion_r0=read_json(source_paths["champion_r0"]),
        champion_r1=read_json(source_paths["champion_r1"]),
    )
    event_map = build_validation_event_map(feature_rows)

    prepared = Path(args.prepared_dir)
    feature_path = prepared / "candidate_e_entry_model_v1_validation_features.csv"
    offset_path = prepared / "candidate_e_entry_model_v1_validation_offsets.csv"
    event_map_path = prepared / "candidate_e_entry_model_v1_validation_event_map.csv"
    freeze_path = prepared / "candidate_e_entry_model_v1_validation_preparation_freeze.json"

    persisted_features = read_csv(feature_path)
    persisted_offsets = read_csv(offset_path)
    persisted_event_map = read_csv(event_map_path)
    persisted_freeze = read_json(freeze_path)

    expected_freeze = build_validation_preparation_freeze(
        feature_rows=feature_rows,
        offset_rows=offset_rows,
        event_map_rows=event_map,
        source_files=source_paths,
        implementation_files={relative: Path(relative) for relative in IMPLEMENTATION_PATHS},
        output_files={
            "feature_rows": feature_path,
            "offset_rows": offset_path,
            "event_map": event_map_path,
        },
        development_freeze_document=read_json(source_paths["development_freeze"]),
    )

    if canonical_rows_fingerprint(persisted_features) != expected_freeze["feature_rows_fingerprint"]:
        raise RuntimeError("persisted validation features differ from rematerialization")
    if canonical_rows_fingerprint(persisted_offsets) != expected_freeze["validation_offset_rows_fingerprint"]:
        raise RuntimeError("persisted validation offsets differ from rematerialization")
    if canonical_rows_fingerprint(persisted_event_map, key="event_ticker") != expected_freeze["validation_event_map_fingerprint"]:
        raise RuntimeError("persisted validation event map differs from rematerialization")
    if persisted_freeze != expected_freeze:
        raise RuntimeError("persisted validation preparation freeze differs from derivation")

    print("Candidate-E Entry Model v1 C1+C2 validation preparation validation: PASS")
    print(f"feature_rows={len(feature_rows)}")
    print(f"events={len(event_map)}")
    print("validation_blocks=5x200")
    print(f"feature_rows_fingerprint={expected_freeze['feature_rows_fingerprint']}")
    print(f"validation_offset_rows_fingerprint={expected_freeze['validation_offset_rows_fingerprint']}")
    print(f"candidate_probability_endpoint_rows={expected_freeze['candidate_probability_endpoint_rows']}")
    print(f"validation_event_map_fingerprint={expected_freeze['validation_event_map_fingerprint']}")
    print(f"validation_preparation_fingerprint={expected_freeze['validation_preparation_fingerprint']}")
    print("deterministic_rematerialization=pass")
    print("model2_offset_input=finite_validation_offset_sidecar")
    print("probability_endpoint_policy=preserve_historical_float_endpoint_no_clipping")
    print("historical_prediction_csv_rows_read=false")
    print("c1_c2_outcome_rows_read_for_model2=false")
    print("validation_scores_calculated=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

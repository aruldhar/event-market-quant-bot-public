from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1_validation_preparation import (
    ARCHIVE_SHA256S,
    C1_PREOUTCOME_SHA256,
    C2_PREOUTCOME_SHA256,
    EVENT_MAP_FIELDS,
    FEATURE_FIELDS,
    OFFSET_FIELDS,
    PARENT_COMMIT,
    build_validation_event_map,
    build_validation_offset_rows,
    build_validation_preparation_freeze,
    materialize_validation_features,
    read_csv_filtered,
    read_json,
    read_preoutcome_csv_strict,
    sha256_file,
    write_csv,
    write_json,
)

DEPENDENCY_PATHS = (
    "src/kxbtcd_candidate_e_entry_model_v1.py",
    "src/kxbtcd_candidate_e_entry_model_v1_materialization.py",
    "src/kxbtcd_candidate_e_predeclaration.py",
    "configs/kxbtcd_candidate_e_entry_model_v1_development_freeze.json",
    "configs/kxbtcd_candidate_e_champion_r0.json",
    "configs/kxbtcd_candidate_e_champion_r1.json",
)
IMPLEMENTATION_PATHS = (
    "src/kxbtcd_candidate_e_entry_model_v1_validation_preparation.py",
    "prepare_kxbtcd_candidate_e_entry_model_v1_validation.py",
    "validate_kxbtcd_candidate_e_entry_model_v1_validation_preparation.py",
)

def git(*args: str) -> str:
    completed = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()

def assert_parent_checkout() -> None:
    git("fetch", "origin")
    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/main")
    if head != PARENT_COMMIT or remote != PARENT_COMMIT:
        raise RuntimeError(
            f"expected HEAD == origin/main == {PARENT_COMMIT}; "
            f"HEAD={head}, origin/main={remote}"
        )
    for relative in DEPENDENCY_PATHS:
        result = subprocess.run(["git", "diff", "--quiet", "--", relative], check=False)
        if result.returncode != 0:
            raise RuntimeError(f"tracked dependency has local changes: {relative}")

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
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    assert_parent_checkout()

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
    for name, path in source_paths.items():
        if not path.is_file():
            raise RuntimeError(f"missing source {name}: {path}")

    expected_hashes = {
        "c1_preoutcome": C1_PREOUTCOME_SHA256,
        "c2_preoutcome": C2_PREOUTCOME_SHA256,
        **ARCHIVE_SHA256S,
    }
    for name, expected in expected_hashes.items():
        actual = sha256_file(source_paths[name])
        if actual != expected:
            raise RuntimeError(f"{name} SHA-256 mismatch: {actual} != {expected}")

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

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    feature_path = out_dir / "candidate_e_entry_model_v1_validation_features.csv"
    offset_path = out_dir / "candidate_e_entry_model_v1_validation_offsets.csv"
    event_map_path = out_dir / "candidate_e_entry_model_v1_validation_event_map.csv"
    freeze_path = out_dir / "candidate_e_entry_model_v1_validation_preparation_freeze.json"

    write_csv(feature_path, FEATURE_FIELDS, feature_rows)
    write_csv(offset_path, OFFSET_FIELDS, offset_rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)

    freeze = build_validation_preparation_freeze(
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
    write_json(freeze_path, freeze)

    print("Candidate-E Entry Model v1 C1+C2 validation preparation: COMPLETE")
    print(f"feature_rows={len(feature_rows)}")
    print(f"events={len(event_map)}")
    print("validation_blocks=5x200")
    print(f"feature_rows_fingerprint={freeze['feature_rows_fingerprint']}")
    print(f"validation_offset_rows_fingerprint={freeze['validation_offset_rows_fingerprint']}")
    print(f"candidate_probability_endpoint_rows={freeze['candidate_probability_endpoint_rows']}")
    print(f"validation_event_map_fingerprint={freeze['validation_event_map_fingerprint']}")
    print(f"validation_preparation_fingerprint={freeze['validation_preparation_fingerprint']}")
    print("candidate_e_C1=Champion-R0")
    print("candidate_e_C2=Champion-R1")
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

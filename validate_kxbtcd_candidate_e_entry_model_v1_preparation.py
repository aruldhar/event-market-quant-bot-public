"""Independent offline validator for Checkpoint-21M preparation artifacts.

The validator re-reads the bound source files, deterministically rematerializes
H1_OOF/H2/H3 features, and checks persisted bytes/fingerprints, schemas, counts,
chronology, outcome exclusion, implementation hashes, and frozen safety flags.
It does not attach labels or fit Model 2.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from src.kxbtcd_candidate_e_entry_model_v1 import (
    CONTINUOUS_FEATURES,
    DEVELOPMENT_STAGES,
    EXPECTED_DEVELOPMENT_EVENT_COUNTS,
    EXPECTED_DEVELOPMENT_ROW_COUNTS,
    MODEL_ID,
    PARAMETER_NAMES,
    build_development_event_map,
    canonical_rows_fingerprint,
    canonical_sha256,
    validate_feature_rows,
)
from src.kxbtcd_candidate_e_entry_model_v1_materialization import (
    EVENT_MAP_FIELDS,
    FEATURE_FIELDS,
    FREEZE_SCHEMA_VERSION,
    IMPLEMENTATION_FILES,
    SOURCE_FILE_KEYS,
    materialize_development_features,
    read_csv,
    sha256_file,
)


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--preoutcome", required=True)
    parser.add_argument("--h1-predictions", required=True)
    parser.add_argument("--h2-predictions", required=True)
    parser.add_argument("--h3-predictions", required=True)
    parser.add_argument("--archive-allowlist", required=True)
    parser.add_argument("--archive-candles", required=True)
    parser.add_argument("--archive-trades", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    _add_source_arguments(parser)
    parser.add_argument("--feature-rows", required=True)
    parser.add_argument("--event-map", required=True)
    parser.add_argument("--freeze", required=True)
    return parser


def validate_preparation_artifacts(
    feature_rows_path: str | Path,
    event_map_path: str | Path,
    freeze_path: str | Path,
    *,
    source_files: Mapping[str, str | Path] | None = None,
    implementation_root: str | Path | None = None,
    enforce_frozen_counts: bool = True,
) -> dict[str, Any]:
    """Independently rederive and verify one persisted preparation freeze."""
    features = read_csv(feature_rows_path)
    event_map = read_csv(event_map_path)
    if not features:
        raise RuntimeError("feature CSV is empty")
    if not event_map:
        raise RuntimeError("event-map CSV is empty")
    freeze = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    if not isinstance(freeze, dict):
        raise RuntimeError("freeze root must be object")
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise RuntimeError("freeze schema mismatch")
    if freeze.get("model_id") != MODEL_ID:
        raise RuntimeError("freeze model_id mismatch")
    expected_contract = {
        "feature_contract": list(FEATURE_FIELDS),
        "continuous_feature_count": len(CONTINUOUS_FEATURES),
        "learned_parameter_count": len(PARAMETER_NAMES),
        "development_stages": list(DEVELOPMENT_STAGES),
        "development_event_counts": dict(EXPECTED_DEVELOPMENT_EVENT_COUNTS),
        "development_row_counts": dict(EXPECTED_DEVELOPMENT_ROW_COUNTS),
    }
    for key, expected in expected_contract.items():
        if freeze.get(key) != expected:
            raise RuntimeError(f"freeze contract mismatch: {key}")
    if tuple(features[0].keys()) != FEATURE_FIELDS:
        raise RuntimeError("feature CSV schema mismatch")
    if tuple(event_map[0].keys()) != EVENT_MAP_FIELDS:
        raise RuntimeError("event-map CSV schema mismatch")

    validate_feature_rows(features, enforce_frozen_counts=enforce_frozen_counts)
    expected_map = build_development_event_map(
        features, enforce_frozen_counts=enforce_frozen_counts
    )
    normalized_map = tuple(
        {
            **row,
            "stage_event_index_zero_based": int(row["stage_event_index_zero_based"]),
            "row_count": int(row["row_count"]),
        }
        for row in event_map
    )
    if normalized_map != expected_map:
        raise RuntimeError("event map differs from independent deterministic derivation")
    if freeze.get("feature_rows_fingerprint") != canonical_rows_fingerprint(features):
        raise RuntimeError("feature-row fingerprint mismatch")
    if freeze.get("development_event_map_fingerprint") != canonical_rows_fingerprint(
        normalized_map, key="event_ticker"
    ):
        raise RuntimeError("event-map fingerprint mismatch")

    expected_output_hashes = {
        "feature_rows": sha256_file(feature_rows_path),
        "development_event_map": sha256_file(event_map_path),
    }
    if freeze.get("prepared_output_sha256s") != expected_output_hashes:
        raise RuntimeError("prepared-output SHA-256 mismatch")

    if source_files is not None:
        if set(source_files) != set(SOURCE_FILE_KEYS):
            raise RuntimeError("source-file key set mismatch")
        expected_source_hashes = {
            name: sha256_file(source_files[name]) for name in sorted(SOURCE_FILE_KEYS)
        }
        if freeze.get("source_file_sha256s") != expected_source_hashes:
            raise RuntimeError("source-file SHA-256 mismatch")
        rematerialized = materialize_development_features(
            preoutcome_rows=read_csv(source_files["preoutcome"]),
            h1_prediction_rows=read_csv(source_files["h1_predictions"]),
            h2_prediction_rows=read_csv(source_files["h2_predictions"]),
            h3_prediction_rows=read_csv(source_files["h3_predictions"]),
            archive_allowlist_rows=read_csv(source_files["archive_allowlist"]),
            candle_rows=read_csv(source_files["archive_candles"]),
            trade_rows=read_csv(source_files["archive_trades"]),
            enforce_frozen_counts=enforce_frozen_counts,
        )
        if canonical_rows_fingerprint(rematerialized) != canonical_rows_fingerprint(features):
            raise RuntimeError("persisted features differ from deterministic source rematerialization")

    if implementation_root is not None:
        root = Path(implementation_root)
        expected_implementation_hashes = {
            relative: sha256_file(root / relative) for relative in IMPLEMENTATION_FILES
        }
        if freeze.get("implementation_sha256s") != expected_implementation_hashes:
            raise RuntimeError("implementation SHA-256 mismatch")

    for key, expected in {
        "outcomes_in_feature_rows": False,
        "strategy_v1_pnl_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "execution_enabled": False,
    }.items():
        if freeze.get(key) is not expected:
            raise RuntimeError(f"safety flag changed: {key}")
    payload = {key: value for key, value in freeze.items() if key != "preparation_fingerprint"}
    if freeze.get("preparation_fingerprint") != canonical_sha256(payload):
        raise RuntimeError("preparation fingerprint mismatch")
    return {
        "feature_rows": len(features),
        "events": len(event_map),
        "feature_csv_sha256": expected_output_hashes["feature_rows"],
        "event_map_csv_sha256": expected_output_hashes["development_event_map"],
    }


def main() -> int:
    args = _parser().parse_args()
    repo = Path(__file__).resolve().parent
    sources = {
        "preoutcome": Path(args.preoutcome),
        "h1_predictions": Path(args.h1_predictions),
        "h2_predictions": Path(args.h2_predictions),
        "h3_predictions": Path(args.h3_predictions),
        "archive_allowlist": Path(args.archive_allowlist),
        "archive_candles": Path(args.archive_candles),
        "archive_trades": Path(args.archive_trades),
    }
    result = validate_preparation_artifacts(
        args.feature_rows,
        args.event_map,
        args.freeze,
        source_files=sources,
        implementation_root=repo,
        enforce_frozen_counts=True,
    )
    print("Candidate-E Entry Model v1 preparation validation: PASS")
    print(f"feature_rows={result['feature_rows']}")
    print(f"events={result['events']}")
    print(f"feature_csv_sha256={result['feature_csv_sha256']}")
    print(f"event_map_csv_sha256={result['event_map_csv_sha256']}")
    print("source_rematerialization=pass")
    print("implementation_hashes=pass")
    print("model2_fit_performed=false")
    print("strategy_v1_pnl_calculated=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

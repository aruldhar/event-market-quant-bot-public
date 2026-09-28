"""Checkpoint-21M outcome-blind Model-2 development materialization CLI.

This command creates deterministic development feature rows and an event map.
It never attaches labels and never fits Model 2.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1 import build_development_event_map
from src.kxbtcd_candidate_e_entry_model_v1_materialization import (
    EVENT_MAP_FIELDS,
    FEATURE_FIELDS,
    IMPLEMENTATION_FILES,
    build_preparation_freeze,
    materialize_development_features,
    read_csv,
    sha256_file,
    write_csv,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preoutcome", required=True)
    parser.add_argument("--h1-predictions", required=True)
    parser.add_argument("--h2-predictions", required=True)
    parser.add_argument("--h3-predictions", required=True)
    parser.add_argument("--archive-allowlist", required=True)
    parser.add_argument("--archive-candles", required=True)
    parser.add_argument("--archive-trades", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


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
    rows = materialize_development_features(
        preoutcome_rows=read_csv(sources["preoutcome"]),
        h1_prediction_rows=read_csv(sources["h1_predictions"]),
        h2_prediction_rows=read_csv(sources["h2_predictions"]),
        h3_prediction_rows=read_csv(sources["h3_predictions"]),
        archive_allowlist_rows=read_csv(sources["archive_allowlist"]),
        candle_rows=read_csv(sources["archive_candles"]),
        trade_rows=read_csv(sources["archive_trades"]),
        enforce_frozen_counts=True,
    )
    event_map = build_development_event_map(rows, enforce_frozen_counts=True)
    output = Path(args.output_dir)
    features_path = output / "candidate_e_entry_model_v1_development_features.csv"
    event_map_path = output / "candidate_e_entry_model_v1_development_event_map.csv"
    freeze_path = output / "candidate_e_entry_model_v1_preparation_freeze.json"
    write_csv(features_path, FEATURE_FIELDS, rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)
    implementation_hashes = {
        relative: sha256_file(repo / relative) for relative in IMPLEMENTATION_FILES
    }
    freeze = build_preparation_freeze(
        rows,
        event_map,
        source_files=sources,
        implementation_sha256s=implementation_hashes,
        prepared_output_files={
            "feature_rows": features_path,
            "development_event_map": event_map_path,
        },
        enforce_frozen_counts=True,
    )
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"feature_rows={len(rows)}")
    print(f"event_rows={len(event_map)}")
    print(f"feature_rows_fingerprint={freeze['feature_rows_fingerprint']}")
    print(f"development_event_map_fingerprint={freeze['development_event_map_fingerprint']}")
    print(f"preparation_fingerprint={freeze['preparation_fingerprint']}")
    print("outcomes_attached=false")
    print("model2_fit_performed=false")
    print("strategy_v1_pnl_calculated=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

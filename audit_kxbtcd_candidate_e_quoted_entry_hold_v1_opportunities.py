"""Checkpoint 21N-A outcome-independent Candidate-E opportunity audit CLI.

The command reads only the frozen development state/probability/quote fields needed
for quoted-edge translation.  It emits no settlement outcome and no realized P&L.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_quoted_entry_hold_v1 import (
    CANDIDATE_STATE_FIELDS,
    CONFIG_PATH,
    SELECTION_FIELDS,
    THRESHOLDS,
    build_candidate_side_states,
    build_opportunity_summary,
    read_csv,
    select_threshold_events,
    sha256_file,
    validate_predeclaration,
    write_csv,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preoutcome", required=True)
    parser.add_argument("--h1-predictions", required=True)
    parser.add_argument("--h2-predictions", required=True)
    parser.add_argument("--h3-predictions", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--output-dir", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    config_path = Path(args.config)
    config = validate_predeclaration(config_path)

    sources = {
        "preoutcome": Path(args.preoutcome),
        "h1_predictions": Path(args.h1_predictions),
        "h2_predictions": Path(args.h2_predictions),
        "h3_predictions": Path(args.h3_predictions),
        "strategy_config": config_path,
    }
    for name, path in sources.items():
        if not path.is_file():
            raise SystemExit(f"{name} file not found: {path}")

    side_states = build_candidate_side_states(
        preoutcome_rows=read_csv(sources["preoutcome"]),
        h1_prediction_rows=read_csv(sources["h1_predictions"]),
        h2_prediction_rows=read_csv(sources["h2_predictions"]),
        h3_prediction_rows=read_csv(sources["h3_predictions"]),
        enforce_frozen_counts=True,
    )
    selections_by_threshold = {
        threshold: select_threshold_events(side_states, threshold=threshold)
        for threshold in THRESHOLDS
    }

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    states_path = output / "candidate_side_states.csv"
    selections_path = output / "threshold_event_selections.csv"
    summary_path = output / "opportunity_audit_summary.json"

    write_csv(states_path, CANDIDATE_STATE_FIELDS, side_states)
    all_selections = [
        row
        for threshold in THRESHOLDS
        for row in selections_by_threshold[threshold]
    ]
    write_csv(selections_path, SELECTION_FIELDS, all_selections)

    summary = build_opportunity_summary(
        side_states=side_states,
        selections_by_threshold=selections_by_threshold,
        input_sha256s={name: sha256_file(path) for name, path in sources.items()},
        config_document=config,
    )
    summary["output_sha256s"] = {
        "candidate_side_states": sha256_file(states_path),
        "threshold_event_selections": sha256_file(selections_path),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"strategy_id={summary['strategy_id']}")
    print(f"strategy_predeclaration_fingerprint={summary['strategy_predeclaration_fingerprint']}")
    print(f"audit_fingerprint={summary['audit_fingerprint']}")
    print(f"development_events={summary['scope']['event_count']}")
    print(f"candidate_probability_rows={summary['scope']['candidate_probability_row_count']}")
    print(f"candidate_side_states={summary['scope']['candidate_side_state_count']}")
    for threshold, result in summary["threshold_summaries"].items():
        print(
            f"threshold={threshold} enter={result['enter_count']} "
            f"abstain={result['abstain_count']} enter_rate={result['enter_rate']}"
        )
    print("settlement_outcomes_used=false")
    print("realized_pnl_calculated=false")
    print("threshold_winner_selected=false")
    print("c1_c2_strategy_pnl_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

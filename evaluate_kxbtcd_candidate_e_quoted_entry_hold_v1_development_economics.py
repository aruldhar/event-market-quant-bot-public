"""Run the frozen Checkpoint 21N-B Strategy-v1 development economic evaluation.

AUTHORIZED ONLY AFTER the 21N-B implementation/predeclaration is safely closed.
Reads already-exposed H1_OOF/H2/H3 outcomes only. It never reads C1/C2/C3/reserve
and contains no network or execution behavior.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_quoted_entry_hold_v1_economics import (
    CONFIG_PATH,
    STRATEGY_CONFIG_PATH,
    RECEIPT_SCHEMA,
    SCENARIO_FIELDS,
    THRESHOLD_SCORE_FIELDS,
    build_development_economic_evaluation,
    build_outcome_map,
    load_json,
    read_csv,
    sha256_file,
    validate_economics_predeclaration,
    validate_opportunity_audit_summary,
    validate_selection_rows,
    validate_strategy_config_file,
    write_csv,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opportunity-summary", required=True)
    parser.add_argument("--threshold-selections", required=True)
    parser.add_argument("--h1-predictions", required=True)
    parser.add_argument("--h2-predictions", required=True)
    parser.add_argument("--h3-predictions", required=True)
    parser.add_argument("--strategy-config", default=str(STRATEGY_CONFIG_PATH))
    parser.add_argument("--economics-config", default=str(CONFIG_PATH))
    parser.add_argument("--output-dir", required=True)
    return parser


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    paths = {
        "opportunity_summary": Path(args.opportunity_summary),
        "threshold_selections": Path(args.threshold_selections),
        "h1_predictions": Path(args.h1_predictions),
        "h2_predictions": Path(args.h2_predictions),
        "h3_predictions": Path(args.h3_predictions),
        "strategy_config": Path(args.strategy_config),
        "economics_config": Path(args.economics_config),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"required {name} file missing: {path}")

    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise RuntimeError(f"output directory must be empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    economics_config = validate_economics_predeclaration(paths["economics_config"])
    validate_strategy_config_file(paths["strategy_config"])

    opportunity_summary = load_json(paths["opportunity_summary"])
    validate_opportunity_audit_summary(opportunity_summary)
    selection_rows = validate_selection_rows(
        read_csv(paths["threshold_selections"]),
        selection_path=paths["threshold_selections"],
        enforce_frozen_counts=True,
    )

    prediction_paths = {
        "H1_OOF": paths["h1_predictions"],
        "H2": paths["h2_predictions"],
        "H3": paths["h3_predictions"],
    }
    outcome_map = build_outcome_map(
        {stage: read_csv(path) for stage, path in prediction_paths.items()},
        source_paths=prediction_paths,
        enforce_frozen_counts=True,
    )

    evaluation, scenario_rows, score_rows = build_development_economic_evaluation(
        selection_rows,
        outcome_map,
    )

    evaluation_path = out / "development_economic_evaluation.json"
    scenarios_path = out / "development_event_pnl_scenarios.csv"
    scores_path = out / "development_threshold_scores.csv"
    receipt_path = out / "development_economic_receipt.json"

    _write_json(evaluation_path, evaluation)
    write_csv(scenarios_path, SCENARIO_FIELDS, scenario_rows)
    write_csv(scores_path, THRESHOLD_SCORE_FIELDS, score_rows)

    repo_root = Path(__file__).resolve().parent
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "strategy_id": evaluation["strategy_id"],
        "strategy_predeclaration_fingerprint": evaluation["strategy_predeclaration_fingerprint"],
        "opportunity_audit_fingerprint": evaluation["opportunity_audit_fingerprint"],
        "development_economics_predeclaration_fingerprint": economics_config[
            "development_economics_predeclaration_fingerprint"
        ],
        "evaluation_fingerprint": evaluation["evaluation_fingerprint"],
        "selected_threshold": evaluation["selection"]["selected_threshold"],
        "status": evaluation["selection"]["status"],
        "source_sha256s": {
            name: sha256_file(path)
            for name, path in paths.items()
        },
        "implementation_sha256s": {
            "src/kxbtcd_candidate_e_quoted_entry_hold_v1_economics.py": sha256_file(
                repo_root / "src/kxbtcd_candidate_e_quoted_entry_hold_v1_economics.py"
            ),
            "evaluate_kxbtcd_candidate_e_quoted_entry_hold_v1_development_economics.py": sha256_file(
                Path(__file__)
            ),
        },
        "output_sha256s": {
            "evaluation": sha256_file(evaluation_path),
            "event_pnl_scenarios": sha256_file(scenarios_path),
            "threshold_scores": sha256_file(scores_path),
        },
        "safety": evaluation["safety"],
    }
    _write_json(receipt_path, receipt)

    print("Candidate-E quoted-entry hold v1 development economics: COMPLETE")
    print(f"evaluation_fingerprint={evaluation['evaluation_fingerprint']}")
    print(f"status={evaluation['selection']['status']}")
    print(f"selected_threshold={evaluation['selection']['selected_threshold'] or 'NONE'}")
    for threshold, result in evaluation["threshold_results"].items():
        base = result["stress_metrics"]["0"]
        plus1 = result["stress_metrics"]["0.01"]
        print(
            f"threshold={threshold} eligible={result['selection_eligible']} "
            f"entries={base['entry_count']} "
            f"base_mean_pnl_per_event={base['mean_pnl_per_event']} "
            f"plus1_mean_pnl_per_event={plus1['mean_pnl_per_event']} "
            f"gate_pass={result['development_gate_pass']}"
        )
    print("development_strategy_pnl_calculated=true")
    print("c1_c2_strategy_pnl_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("orders_submitted=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

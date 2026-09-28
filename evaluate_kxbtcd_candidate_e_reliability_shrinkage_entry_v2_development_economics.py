"""Run frozen Checkpoint 21N-G Strategy-v2 development economics.

AUTHORIZED ONLY AFTER 21N-G implementation/predeclaration is safely closed.
Reads already-exposed H1_OOF/H2/H3 outcomes. Does not access C1/C2/C3/reserve.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_reliability_shrinkage_entry_v2_economics import (
    ALPHA_SCORE_FIELDS, AUDIT_CLOSEOUT_PATH, CONFIG_PATH, RECEIPT_SCHEMA,
    SCENARIO_FIELDS, STRATEGY_V2_CONFIG_PATH,
    build_development_economic_evaluation, build_outcome_map, load_json,
    read_csv, sha256_file, validate_audit_result_closeout,
    validate_economics_predeclaration, validate_opportunity_summary,
    validate_selection_rows, validate_strategy_v2_config, write_csv,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--opportunity-summary", required=True)
    p.add_argument("--alpha-selections", required=True)
    p.add_argument("--h1-predictions", required=True)
    p.add_argument("--h2-predictions", required=True)
    p.add_argument("--h3-predictions", required=True)
    p.add_argument("--strategy-config", default=str(STRATEGY_V2_CONFIG_PATH))
    p.add_argument("--audit-closeout-config", default=str(AUDIT_CLOSEOUT_PATH))
    p.add_argument("--economics-config", default=str(CONFIG_PATH))
    p.add_argument("--output-dir", required=True)
    return p


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    paths = {
        "opportunity_summary": Path(args.opportunity_summary),
        "alpha_selections": Path(args.alpha_selections),
        "h1_predictions": Path(args.h1_predictions),
        "h2_predictions": Path(args.h2_predictions),
        "h3_predictions": Path(args.h3_predictions),
        "strategy_config": Path(args.strategy_config),
        "audit_closeout_config": Path(args.audit_closeout_config),
        "economics_config": Path(args.economics_config),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"required {name} file missing: {path}")

    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise RuntimeError(f"output directory must be empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    economics = validate_economics_predeclaration(paths["economics_config"])
    validate_audit_result_closeout(paths["audit_closeout_config"])
    validate_strategy_v2_config(paths["strategy_config"])

    summary = load_json(paths["opportunity_summary"])
    validate_opportunity_summary(summary)
    selection_rows = validate_selection_rows(
        read_csv(paths["alpha_selections"]),
        selection_path=paths["alpha_selections"],
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

    evaluation, scenarios, scores = build_development_economic_evaluation(
        selection_rows, outcome_map
    )

    evaluation_path = out / "development_economic_evaluation.json"
    scenarios_path = out / "development_event_pnl_scenarios.csv"
    scores_path = out / "development_alpha_scores.csv"
    receipt_path = out / "development_economic_receipt.json"

    _write_json(evaluation_path, evaluation)
    write_csv(scenarios_path, SCENARIO_FIELDS, scenarios)
    write_csv(scores_path, ALPHA_SCORE_FIELDS, scores)

    repo_root = Path(__file__).resolve().parent
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "strategy_id": evaluation["strategy_id"],
        "strategy_v2_predeclaration_fingerprint": evaluation["strategy_v2_predeclaration_fingerprint"],
        "opportunity_audit_fingerprint": evaluation["opportunity_audit_fingerprint"],
        "opportunity_audit_result_closeout_fingerprint": evaluation["opportunity_audit_result_closeout_fingerprint"],
        "development_economics_predeclaration_fingerprint": economics["development_economics_predeclaration_fingerprint"],
        "evaluation_fingerprint": evaluation["evaluation_fingerprint"],
        "selected_alpha": evaluation["selection"]["selected_alpha"],
        "status": evaluation["selection"]["status"],
        "source_sha256s": {name: sha256_file(path) for name, path in paths.items()},
        "implementation_sha256s": {
            "src/kxbtcd_candidate_e_reliability_shrinkage_entry_v2_economics.py": sha256_file(
                repo_root / "src/kxbtcd_candidate_e_reliability_shrinkage_entry_v2_economics.py"
            ),
            "evaluate_kxbtcd_candidate_e_reliability_shrinkage_entry_v2_development_economics.py": sha256_file(
                Path(__file__)
            ),
        },
        "output_sha256s": {
            "evaluation": sha256_file(evaluation_path),
            "event_pnl_scenarios": sha256_file(scenarios_path),
            "alpha_scores": sha256_file(scores_path),
        },
        "safety": evaluation["safety"],
    }
    _write_json(receipt_path, receipt)

    print("Candidate-E reliability-shrinkage Strategy-v2 development economics: COMPLETE")
    print(f"evaluation_fingerprint={evaluation['evaluation_fingerprint']}")
    print(f"status={evaluation['selection']['status']}")
    print(f"selected_alpha={evaluation['selection']['selected_alpha'] or 'NONE'}")
    for alpha, result in evaluation["alpha_results"].items():
        base = result["stress_metrics"]["0"]
        plus1 = result["stress_metrics"]["0.01"]
        print(
            f"alpha={alpha} entries={base['entry_count']} "
            f"base_mean_pnl_per_event={base['mean_pnl_per_event']} "
            f"plus1_mean_pnl_per_event={plus1['mean_pnl_per_event']} "
            f"positive_blocks={result['base_positive_block_count']} "
            f"newest_positive={str(result['base_newest_block_positive']).lower()} "
            f"h3_mean={result['base_h3_mean_pnl_per_event']} "
            f"gate_pass={str(result['development_gate_pass']).lower()}"
        )
    print("alpha_0_25_outcome_scored=false")
    print("alpha_1_outcome_rescored=false")
    print("c1_c2_strategy_pnl_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("orders_submitted=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

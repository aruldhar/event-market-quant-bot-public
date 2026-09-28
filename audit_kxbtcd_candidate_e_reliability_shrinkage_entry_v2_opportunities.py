"""Checkpoint 21N-F outcome-independent Strategy-v2 opportunity audit."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from src.kxbtcd_candidate_e_reliability_shrinkage_entry_v2 import (
    ALL_ALPHAS,
    CANDIDATE_ALPHAS,
    CONFIG_PATH,
    EXPECTED_PREDICTION_SHA256S,
    EXPECTED_V1_ALL_SELECTION_SHA256,
    EXPECTED_V1_CONFIG_SHA256,
    REFERENCE_ALPHA,
    SELECTION_FIELDS,
    adjust_base_side_state,
    assert_alpha1_reproduces_v1,
    build_adjusted_side_states,
    build_opportunity_summary,
    read_csv,
    select_alpha_events,
    sha256_file,
    validate_predeclaration,
    write_csv,
)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--preoutcome", required=True)
    p.add_argument("--h1-predictions", required=True)
    p.add_argument("--h2-predictions", required=True)
    p.add_argument("--h3-predictions", required=True)
    p.add_argument("--v1-config", default="configs/kxbtcd_candidate_e_quoted_entry_hold_v1.json")
    p.add_argument("--config", default=str(CONFIG_PATH))
    p.add_argument("--output-dir", required=True)
    return p


def main() -> int:
    args = _parser().parse_args()
    config_path = Path(args.config)
    validate_predeclaration(config_path)

    sources = {
        "preoutcome": Path(args.preoutcome),
        "H1_OOF": Path(args.h1_predictions),
        "H2": Path(args.h2_predictions),
        "H3": Path(args.h3_predictions),
        "strategy_v1_config": Path(args.v1_config),
        "strategy_v2_config": config_path,
    }
    for name, path in sources.items():
        if not path.is_file():
            raise SystemExit(f"{name} file not found: {path}")

    if sha256_file(sources["strategy_v1_config"]) != EXPECTED_V1_CONFIG_SHA256:
        raise SystemExit("Strategy-v1 config SHA-256 changed")
    for stage in ("H1_OOF", "H2", "H3"):
        actual = sha256_file(sources[stage])
        if actual != EXPECTED_PREDICTION_SHA256S[stage]:
            raise SystemExit(f"{stage} prediction SHA-256 changed: {actual}")

    # Reuse the exact frozen 21N-A state builder and selection implementation.
    import src.kxbtcd_candidate_e_quoted_entry_hold_v1 as v1

    v1.validate_predeclaration(sources["strategy_v1_config"])
    base_states = v1.build_candidate_side_states(
        preoutcome_rows=v1.read_csv(sources["preoutcome"]),
        h1_prediction_rows=v1.read_csv(sources["H1_OOF"]),
        h2_prediction_rows=v1.read_csv(sources["H2"]),
        h3_prediction_rows=v1.read_csv(sources["H3"]),
        enforce_frozen_counts=True,
    )

    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    # Strong input/reconstruction guard: reproduce the complete 21N-A selection file
    # with the exact frozen v1 code before accepting any Strategy-v2 audit result.
    v1_reproduction_path = output / "strategy_v1_reproduction_threshold_event_selections.csv"
    v1_all = [
        row
        for threshold in v1.THRESHOLDS
        for row in v1.select_threshold_events(base_states, threshold=threshold)
    ]
    v1.write_csv(v1_reproduction_path, v1.SELECTION_FIELDS, v1_all)
    v1_reproduction_sha = v1.sha256_file(v1_reproduction_path)
    if v1_reproduction_sha != EXPECTED_V1_ALL_SELECTION_SHA256:
        raise SystemExit(
            "Strategy-v1 exact selection reproduction failed: "
            f"{v1_reproduction_sha} != {EXPECTED_V1_ALL_SELECTION_SHA256}"
        )

    selections_by_alpha = {}
    for alpha in ALL_ALPHAS:
        adjusted = build_adjusted_side_states(base_states, alpha=alpha)
        selections_by_alpha[alpha] = select_alpha_events(adjusted, alpha=alpha)

    v1_zero = v1.select_threshold_events(base_states, threshold=Decimal("0.00"))
    assert_alpha1_reproduces_v1(
        v1_zero_rows=v1_zero,
        alpha1_rows=selections_by_alpha[REFERENCE_ALPHA],
    )

    selections_path = output / "alpha_event_selections.csv"
    all_rows = [
        row
        for alpha in ALL_ALPHAS
        for row in selections_by_alpha[alpha]
    ]
    write_csv(selections_path, SELECTION_FIELDS, all_rows)

    input_hashes = {name: sha256_file(path) for name, path in sources.items()}
    summary = build_opportunity_summary(
        selections_by_alpha=selections_by_alpha,
        input_sha256s=input_hashes,
        v1_reproduction_sha256=v1_reproduction_sha,
    )
    summary["output_sha256s"] = {
        "alpha_event_selections": sha256_file(selections_path),
        "strategy_v1_reproduction_threshold_event_selections": v1_reproduction_sha,
    }
    summary_path = output / "opportunity_audit_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Candidate-E reliability-shrinkage Strategy-v2 opportunity audit: COMPLETE")
    print(f"strategy_v2_predeclaration_fingerprint={summary['strategy_v2_predeclaration_fingerprint']}")
    print(f"audit_fingerprint={summary['audit_fingerprint']}")
    print(f"v1_exact_reproduction={str(summary['v1_reproduction']['exact_match']).lower()}")
    for alpha in ALL_ALPHAS:
        key = str(alpha.normalize())
        # _fmt semantics: 1.00 -> "1", 0.50 -> "0.5"
        if alpha == Decimal("1.00"):
            key = "1"
        elif alpha == Decimal("0.50"):
            key = "0.5"
        elif alpha == Decimal("0.25"):
            key = "0.25"
        elif alpha == Decimal("0.75"):
            key = "0.75"
        result = summary["alpha_summaries"][key]
        print(
            f"alpha={key} enter={result['enter_count']} abstain={result['abstain_count']} "
            f"retained_vs_alpha1={result['retained_fraction_of_alpha1_entries']:.6f} "
            f"changed_decisions={result['action_or_choice_changed_count']} "
            f"changed_fraction={result['action_or_choice_changed_fraction_vs_alpha1']:.6f} "
            f"sample_eligible={str(result['later_economics_sample_eligible']).lower()} "
            f"materiality_pass={str(result['opportunity_materiality_pass']).lower()}"
        )
    print(f"any_candidate_materiality_pass={str(summary['continuation']['any_candidate_materiality_pass']).lower()}")
    print("settlement_outcomes_used=false")
    print("realized_pnl_calculated=false")
    print("alpha_winner_selected=false")
    print("strategy_v2_pnl_authorized=false")
    print("c1_c2_strategy_pnl_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("orders_submitted=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

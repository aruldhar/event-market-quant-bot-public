from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.kxbtcd_candidate_e_entry_model_v1 import (
    CANDIDATE_E_ID,
    CONTINUOUS_FEATURES,
    LAMBDA_GRID,
    MODEL_ID,
    ROW_SCHEMA_VERSION,
)
from src.kxbtcd_candidate_e_entry_model_v1_development import (
    CandidateEEntryDevelopmentError,
    PREDICTION_SCHEMAS,
    build_development_evaluation,
    project_exposed_development_labels,
)


def _synthetic_feature_and_sources():
    features = []
    sources = {"H1_OOF": [], "H2": [], "H3": []}
    stages = ("H1_OOF", "H2", "H3")
    ttcs = (55, 50, 45, 40, 35, 30)
    roles = ("q10", "q30", "q50", "q70", "q90")
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = 0
    for stage_index, stage in enumerate(stages):
        for event_index in range(4):
            event = f"E{stage_index}{event_index}"
            close = base + timedelta(days=stage_index * 10 + event_index)
            for state_index in range(8):
                ttc = ttcs[state_index % len(ttcs)]
                role = roles[(state_index + event_index) % len(roles)]
                market = f"{event}-M{state_index}"
                state = f"{event}|{market}|TTC{ttc}|{role}"
                # Pair adjacent states with identical model inputs, p=0.5, and
                # opposite labels. This makes the synthetic optimum beta=0 exactly
                # in every fit partition, avoiding platform-sensitive convergence
                # behavior while still exercising the full orchestration path.
                pair_index = state_index // 2
                candidate = 0.5
                row = {
                    "schema_version": ROW_SCHEMA_VERSION,
                    "model_id": MODEL_ID,
                    "stage": stage,
                    "state_id": state,
                    "event_ticker": event,
                    "event_close_time_utc": close.isoformat().replace("+00:00", "Z"),
                    "market_ticker": market,
                    "structural_role": role,
                    "ttc_target_minutes": ttc,
                    "decision_time_utc": (close - timedelta(minutes=ttc)).isoformat().replace("+00:00", "Z"),
                    "candidate_probability": candidate,
                }
                for feature_index, name in enumerate(CONTINUOUS_FEATURES):
                    base_value = (
                        (stage_index + 1) * 0.13
                        + (event_index + 1) * 0.017
                        + (pair_index + 1) * 0.031
                    )
                    row[name] = (
                        base_value * (feature_index + 1)
                        + ((feature_index * pair_index + event_index) % 5) * 0.007
                    )
                features.append(row)
                outcome = state_index % 2
                sources[stage].append(
                    {
                        "schema_version": PREDICTION_SCHEMAS[stage],
                        "candidate_id": CANDIDATE_E_ID,
                        "state_id": state,
                        "event_ticker": event,
                        "market_ticker": market,
                        "outcome": outcome,
                    }
                )
                index += 1
    return features, sources


def test_label_projection_filters_non_candidate_e_rows():
    _, sources = _synthetic_feature_and_sources()
    challenger = dict(sources["H1_OOF"][0])
    challenger["candidate_id"] = "rejected_challenger.v1"
    sources["H1_OOF"].append(challenger)
    labels = project_exposed_development_labels(sources, enforce_frozen_counts=False)
    assert len(labels) == 96
    assert {row["stage"] for row in labels} == {"H1_OOF", "H2", "H3"}


def test_label_projection_rejects_duplicate_candidate_state():
    _, sources = _synthetic_feature_and_sources()
    sources["H2"].append(dict(sources["H2"][0]))
    with pytest.raises(CandidateEEntryDevelopmentError, match="duplicate H2"):
        project_exposed_development_labels(sources, enforce_frozen_counts=False)


def test_label_projection_rejects_nonbinary_outcome():
    _, sources = _synthetic_feature_and_sources()
    sources["H3"][0]["outcome"] = "2"
    with pytest.raises(CandidateEEntryDevelopmentError, match="must be 0 or 1"):
        project_exposed_development_labels(sources, enforce_frozen_counts=False)


def test_development_evaluation_executes_frozen_two_fold_protocol():
    features, sources = _synthetic_feature_and_sources()
    labels = project_exposed_development_labels(sources, enforce_frozen_counts=False)
    result = build_development_evaluation(features, labels, enforce_frozen_counts=False)
    assert result["selected_lambda"] in LAMBDA_GRID
    assert len(result["lambda_scores"]) == len(LAMBDA_GRID)
    assert len(result["fold_fits"]) == 2 * len(LAMBDA_GRID)
    assert result["interpretation"]["development_selection_only"] is True
    assert result["interpretation"]["validation_gate_evaluated"] is False
    assert all(value is False for value in result["safety"].values())
    assert set(result["selected_rolling_origin_diagnostics"]) == {"H2", "H3", "pooled_H2_H3"}

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import pytest

from src.kxbtcd_candidate_e_entry_model_v1 import (
    LAMBDA_GRID,
    MODEL_ID,
    PARAMETER_NAMES,
    ROW_SCHEMA_VERSION,
    CandidateEEntryModelV1Error,
    attach_development_labels,
    build_development_event_map,
    dense_cholesky_solve,
    design_vector,
    evaluate_development_rolling_origin,
    event_equal_weights,
    fit_event_equal_scaler,
    fit_residual_logistic,
    select_lambda,
)

FEATURES = (
    "r_5m",
    "spread_t",
    "mid_move_1m",
    "spread_change_1m",
    "bid_range_1m",
    "ask_range_1m",
    "log1p_volume_1m",
    "log1p_open_interest",
    "log1p_trade_count_5m",
    "log1p_contracts_5m",
    "taker_imbalance_5m",
)


def _row(*, state, event, stage, close, index, outcome=None, p=0.5, ttc=55, role="q50"):
    values = {
        name: math.sin((index + 1) * (j + 1) * 0.37) + 0.07 * index + 0.01 * j
        for j, name in enumerate(FEATURES)
    }
    row = {
        "schema_version": ROW_SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "stage": stage,
        "state_id": state,
        "event_ticker": event,
        "event_close_time_utc": close,
        "market_ticker": f"M-{event}",
        "structural_role": role,
        "ttc_target_minutes": ttc,
        "decision_time_utc": close,
        "candidate_probability": p,
        **values,
    }
    if outcome is not None:
        row["outcome"] = outcome
    return row


def test_event_equal_weights_give_each_event_equal_total_mass():
    rows = [
        {"event_ticker": "A"},
        {"event_ticker": "A"},
        {"event_ticker": "B"},
    ]
    weights = event_equal_weights(rows)
    assert weights == pytest.approx((0.25, 0.25, 0.5))
    assert sum(weights[:2]) == pytest.approx(weights[2])


def test_event_equal_scaler_uses_event_equal_population_weighting():
    rows = []
    for state, event, value in (("a1", "A", 0.0), ("a2", "A", 2.0), ("b1", "B", 10.0)):
        row = _row(state=state, event=event, stage="H1_OOF", close="2025-01-01T00:00:00Z", index=1)
        for name in FEATURES:
            row[name] = value
        rows.append(row)
    scaler = fit_event_equal_scaler(rows)
    assert scaler.means[0] == pytest.approx(5.5)  # 0.5*(A mean=1) + 0.5*(B=10)
    expected_var = 0.25 * (0 - 5.5) ** 2 + 0.25 * (2 - 5.5) ** 2 + 0.5 * (10 - 5.5) ** 2
    assert scaler.stds[0] == pytest.approx(math.sqrt(expected_var))


def test_design_vector_is_exactly_21_and_uses_frozen_reference_coding():
    rows = [
        _row(state=f"s{i}", event=f"E{i}", stage="H1_OOF", close=f"2025-01-{i+1:02d}T00:00:00Z", index=i)
        for i in range(4)
    ]
    scaler = fit_event_equal_scaler(rows)
    reference = design_vector(rows[0], scaler)
    assert len(PARAMETER_NAMES) == 21
    assert len(reference) == 21
    assert reference[0] == 1.0
    assert reference[12:] == pytest.approx((0.0,) * 9)
    nonreference = dict(rows[1])
    nonreference["ttc_target_minutes"] = 40
    nonreference["structural_role"] = "q70"
    vector = design_vector(nonreference, scaler)
    # 1 intercept + 11 continuous => TTC indicators at 12:17; role at 17:21.
    assert vector[14] == 1.0  # T-40
    assert vector[19] == 1.0  # q70


def test_cholesky_solver_matches_known_positive_definite_system():
    solution = dense_cholesky_solve([[4.0, 1.0], [1.0, 3.0]], [1.0, 2.0])
    assert solution == pytest.approx((1 / 11, 7 / 11))


def test_optimizer_is_deterministic_and_starts_from_candidate_e_baseline_contract():
    rows = []
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for i in range(18):
        outcome = 1 if i >= 6 else 0
        p = 0.45 + 0.01 * ((i % 3) - 1)
        rows.append(
            _row(
                state=f"s{i}",
                event=f"E{i}",
                stage="H1_OOF",
                close=(base + timedelta(minutes=i)).isoformat().replace("+00:00", "Z"),
                index=i,
                outcome=outcome,
                p=p,
                ttc=(55, 50, 45, 40, 35, 30)[i % 6],
                role=("q10", "q30", "q50", "q70", "q90")[i % 5],
            )
        )
    first = fit_residual_logistic(rows, lambda_value=1.0)
    second = fit_residual_logistic(rows, lambda_value=1.0)
    assert first.coefficients == second.coefficients
    assert first.objective == second.objective
    assert first.iterations <= 100
    assert any(abs(value) > 1e-8 for value in first.coefficients)


def test_candidate_probability_is_not_clipped():
    rows = [
        _row(state=f"s{i}", event=f"E{i}", stage="H1_OOF", close=f"2025-01-{i+1:02d}T00:00:00Z", index=i, outcome=i % 2)
        for i in range(4)
    ]
    rows[0]["candidate_probability"] = 0.0
    with pytest.raises(CandidateEEntryModelV1Error, match="clipping is prohibited"):
        fit_residual_logistic(rows, lambda_value=1.0)


def test_attach_labels_occurs_after_feature_rows_and_requires_exact_state_set():
    features = [
        _row(state="s1", event="E1", stage="H1_OOF", close="2025-01-01T00:00:00Z", index=1),
        _row(state="s2", event="E2", stage="H2", close="2025-01-02T00:00:00Z", index=2),
        _row(state="s3", event="E3", stage="H3", close="2025-01-03T00:00:00Z", index=3),
    ]
    labels = [
        {"state_id": row["state_id"], "event_ticker": row["event_ticker"], "market_ticker": row["market_ticker"], "outcome": i % 2}
        for i, row in enumerate(features)
    ]
    attached = attach_development_labels(features, labels, enforce_frozen_counts=False)
    assert [row["outcome"] for row in attached] == [0, 1, 0]
    with pytest.raises(CandidateEEntryModelV1Error, match="label state set mismatch"):
        attach_development_labels(features, labels[:-1], enforce_frozen_counts=False)


def test_development_event_map_is_whole_event_chronological_and_outcome_blind():
    rows = [
        _row(state="s1", event="E1", stage="H1_OOF", close="2025-01-01T00:00:00Z", index=1),
        _row(state="s2", event="E2", stage="H2", close="2025-01-02T00:00:00Z", index=2),
        _row(state="s3", event="E3", stage="H3", close="2025-01-03T00:00:00Z", index=3),
    ]
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    assert [row["stage"] for row in event_map] == ["H1_OOF", "H2", "H3"]
    assert all("outcome" not in row for row in event_map)


def test_lambda_exact_tie_chooses_larger_lambda():
    scores = [
        {"lambda": value, "pooled_event_equal_log_loss": 0.2 if value in (0.1, 1.0) else 0.3}
        for value in LAMBDA_GRID
    ]
    assert select_lambda(scores) == 1.0


def _rolling_fixture():
    rows = []
    index = 0
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for stage_index, stage in enumerate(("H1_OOF", "H2", "H3")):
        for event_index in range(6):
            event = f"{stage}-E{event_index}"
            close = base + timedelta(days=stage_index * 10, hours=event_index)
            for episode in range(2):
                outcome = 1 if (event_index + stage_index) % 3 else 0
                p = 0.42 + 0.03 * ((event_index + episode) % 4)
                rows.append(
                    _row(
                        state=f"{event}-s{episode}",
                        event=event,
                        stage=stage,
                        close=close.isoformat().replace("+00:00", "Z"),
                        index=index,
                        outcome=outcome,
                        p=p,
                        ttc=(55, 50, 45, 40, 35, 30)[(event_index + episode) % 6],
                        role=("q10", "q30", "q50", "q70", "q90")[(event_index + episode) % 5],
                    )
                )
                index += 1
    return rows


def test_rolling_origin_development_protocol_is_deterministic_on_synthetic_only():
    rows = _rolling_fixture()
    first = evaluate_development_rolling_origin(rows, enforce_frozen_counts=False)
    second = evaluate_development_rolling_origin(rows, enforce_frozen_counts=False)
    assert first.selected_lambda in LAMBDA_GRID
    assert first.selected_lambda == second.selected_lambda
    assert first.lambda_scores == second.lambda_scores
    assert first.full_development_fit.coefficients == second.full_development_fit.coefficients
    assert {(row["fold"], row["score_stage"]) for row in first.fold_fits} == {(1, "H2"), (2, "H3")}


def test_l2_regularization_shrinks_full_residual_vector_including_intercept():
    rows = _rolling_fixture()
    weak = fit_residual_logistic(rows, lambda_value=0.001)
    strong = fit_residual_logistic(rows, lambda_value=10.0)
    weak_norm = math.sqrt(sum(value * value for value in weak.coefficients))
    strong_norm = math.sqrt(sum(value * value for value in strong.coefficients))
    assert strong_norm < weak_norm
    assert abs(strong.coefficients[0]) < abs(weak.coefficients[0])

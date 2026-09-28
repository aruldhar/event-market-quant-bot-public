from __future__ import annotations

import math

import pytest

from src.kxbtcd_candidate_c_generalization_review import (
    DevelopmentContextRow,
    FoldModel,
    OofRow,
    aggregate_event_metrics,
    positive_lag1_ess_heuristic,
    predict_from_stored_fold,
    protocol_layout_candidates,
    raw_space_coefficients,
    _symmetric_eigenvalues_3x3,
)


def _oof(
    state: str,
    event: str,
    week: str,
    block: str,
    *,
    q: float,
    p: float,
    outcome: int,
    raw_ll: float,
    cand_ll: float,
) -> OofRow:
    return OofRow(
        state_id=state,
        event_ticker=event,
        market_ticker=f"M-{state}",
        utc_week_start=week,
        block=block,
        outcome=outcome,
        q_market=q,
        spread=0.02,
        candidate_probability=p,
        raw_log_loss=raw_ll,
        candidate_log_loss=cand_ll,
        raw_brier=(q - outcome) ** 2,
        candidate_brier=(p - outcome) ** 2,
    )


def test_event_aggregation_equal_weights_rows_within_event() -> None:
    rows = (
        _oof("a1", "E1", "W1", "B1", q=0.2, p=0.1, outcome=0, raw_ll=0.2, cand_ll=0.1),
        _oof("a2", "E1", "W1", "B1", q=0.2, p=0.1, outcome=0, raw_ll=0.4, cand_ll=0.2),
        _oof("b1", "E2", "W1", "B1", q=0.8, p=0.9, outcome=1, raw_ll=0.3, cand_ll=0.4),
    )
    events = aggregate_event_metrics(rows)
    by_event = {event.event_ticker: event for event in events}
    assert by_event["E1"].raw_log_loss == pytest.approx(0.3)
    assert by_event["E1"].candidate_log_loss == pytest.approx(0.15)
    assert by_event["E1"].delta_log_loss == pytest.approx(0.15)
    assert by_event["E2"].delta_log_loss == pytest.approx(-0.1)


def test_raw_space_coefficient_conversion_reconstructs_same_logit() -> None:
    model = FoldModel(
        fold=1,
        fit_blocks=("B0",),
        score_block="B1",
        beta0=0.2,
        beta1=1.5,
        beta2=-0.4,
        beta3=0.7,
        means=(0.1, 0.02, 0.005),
        stds=(2.0, 0.01, 0.1),
    )
    raw = raw_space_coefficients(model)
    q = 0.7
    spread = 0.03
    market_logit = math.log(q / (1 - q))
    features = (market_logit, spread, market_logit * spread)
    direct_z = (
        model.beta0
        + model.beta1 * ((features[0] - model.means[0]) / model.stds[0])
        + model.beta2 * ((features[1] - model.means[1]) / model.stds[1])
        + model.beta3 * ((features[2] - model.means[2]) / model.stds[2])
    )
    raw_z = raw[0] + raw[1] * features[0] + raw[2] * features[1] + raw[3] * features[2]
    assert raw_z == pytest.approx(direct_z)


def test_stored_fold_prediction_requires_no_refit() -> None:
    model = FoldModel(
        fold=1,
        fit_blocks=("B0",),
        score_block="B1",
        beta0=0.0,
        beta1=1.0,
        beta2=0.0,
        beta3=0.0,
        means=(0.0, 0.1, 0.0),
        stds=(1.0, 0.2, 1.0),
    )
    p = predict_from_stored_fold(model, 0.8, 0.05)
    assert 0.0 < p < 1.0
    assert p == pytest.approx(0.8)


def test_positive_lag1_ess_never_exceeds_nominal_count() -> None:
    assert positive_lag1_ess_heuristic(20, -0.5) == 20.0
    assert positive_lag1_ess_heuristic(20, 0.0) == 20.0
    assert positive_lag1_ess_heuristic(20, 0.5) == pytest.approx(20 / 3)
    assert positive_lag1_ess_heuristic(20, 1.0) == 1.0


def test_symmetric_eigenvalue_helper_matches_diagonal_matrix() -> None:
    values = _symmetric_eigenvalues_3x3(
        (
            (3.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 2.0),
        )
    )
    assert values == pytest.approx((1.0, 2.0, 3.0))


def test_protocol_layout_candidates_use_only_event_and_week_ids() -> None:
    pairs = tuple(
        (f"E{index}", f"2026-W{index // 2:02d}")
        for index in range(24)
    )
    rows = protocol_layout_candidates(pairs, block_counts=(6,))
    assert len(rows) == 6
    assert all(row["outcomes_used_to_construct_layout"] == "false" for row in rows)
    assert sum(int(row["event_count"]) for row in rows) == 24
    assert max(int(row["week_count"]) for row in rows) - min(
        int(row["week_count"]) for row in rows
    ) <= 1

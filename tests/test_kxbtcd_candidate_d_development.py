import math

from src.kxbtcd_candidate_d_development import (
    CandidateDObservation,
    CandidateDFit,
    MetricPair,
    _market_logit,
    event_weighted_metrics,
    evaluate_advancement_gate,
    fit_candidate_d_fold,
    predict_candidate_d,
)
from src.kxbtcd_candidate_d_predeclaration import FROZEN_PREDECLARATION_FINGERPRINT


def obs(event, q, y, block=0, state="s"):
    return CandidateDObservation(
        partition="train",
        state_id=f"{state}-{event}-{q}-{y}",
        event_ticker=event,
        market_ticker=f"M-{event}",
        utc_week_start="2025-03-17T00:00:00Z",
        block=block,
        outcome=y,
        q_market=q,
        market_logit=_market_logit(q),
    )


def test_market_logit_uses_frozen_point001_clip():
    assert math.isclose(_market_logit(0.0), math.log(0.001 / 0.999), rel_tol=0, abs_tol=1e-12)
    assert math.isclose(_market_logit(1.0), math.log(0.999 / 0.001), rel_tol=0, abs_tol=1e-12)
    assert math.isclose(_market_logit(0.5), 0.0, rel_tol=0, abs_tol=1e-15)


def test_raw_market_is_exactly_nested_at_zero_corrections():
    row = obs("E1", 0.73, 1)
    fit = CandidateDFit(
        fold_index=1,
        fit_blocks=(0, 1),
        score_block=2,
        alpha=0.0,
        delta=0.0,
        iterations=0,
        converged=True,
        fit_objective=0.0,
    )
    assert math.isclose(predict_candidate_d(row, fit), 0.73, rel_tol=0, abs_tol=1e-15)


def test_event_weighting_gives_each_event_equal_total_weight():
    rows = (
        obs("E1", 0.5, 1, state="a"),
        obs("E1", 0.5, 1, state="b"),
        obs("E1", 0.5, 1, state="c"),
        obs("E2", 0.5, 0, state="d"),
    )
    probabilities = [0.9, 0.9, 0.9, 0.2]
    metrics = event_weighted_metrics(rows, probabilities)
    expected_e1 = -math.log(0.9)
    expected_e2 = -math.log(0.8)
    assert math.isclose(metrics.log_loss, (expected_e1 + expected_e2) / 2, rel_tol=0, abs_tol=1e-15)


def test_fit_is_deterministic_and_returns_finite_positive_slope_on_simple_data():
    rows = (
        obs("E1", 0.2, 0, state="a"),
        obs("E2", 0.3, 0, state="b"),
        obs("E3", 0.7, 1, state="c"),
        obs("E4", 0.8, 1, state="d"),
        obs("E5", 0.4, 0, state="e"),
        obs("E6", 0.6, 1, state="f"),
    )
    fit1 = fit_candidate_d_fold(rows, fold_index=1, fit_blocks=(0,), score_block=1)
    fit2 = fit_candidate_d_fold(rows, fold_index=1, fit_blocks=(0,), score_block=1)
    assert fit1 == fit2
    assert fit1.converged
    assert math.isfinite(fit1.alpha)
    assert math.isfinite(fit1.delta)
    assert fit1.market_logit_slope > 0


def test_gate_requires_latest_block_and_four_of_five_even_when_pooled_is_better():
    fits = [
        CandidateDFit(i + 1, (0,), i + 2, 0.0, 0.0, 1, True, 0.1)
        for i in range(5)
    ]
    gate = evaluate_advancement_gate(
        raw_pooled=MetricPair(0.20, 0.08),
        candidate_pooled=MetricPair(0.19, 0.08),
        per_block_raw_log_loss=[0.2] * 5,
        per_block_candidate_log_loss=[0.19, 0.19, 0.19, 0.19, 0.21],
        median_event_delta=0.01,
        fits=fits,
    )
    assert gate["score_block_log_loss_win_count"] == 4
    assert gate["at_least_4_of_5_score_blocks_better"] is True
    assert gate["latest_B6_log_loss_strictly_better"] is False
    assert gate["passed"] is False


def test_gate_fails_nonpositive_slope():
    fits = [
        CandidateDFit(i + 1, (0,), i + 2, 0.0, 0.0, 1, True, 0.1)
        for i in range(4)
    ] + [
        CandidateDFit(5, (0,), 6, 0.0, -1.0, 1, True, 0.1)
    ]
    gate = evaluate_advancement_gate(
        raw_pooled=MetricPair(0.20, 0.08),
        candidate_pooled=MetricPair(0.19, 0.07),
        per_block_raw_log_loss=[0.2] * 5,
        per_block_candidate_log_loss=[0.19] * 5,
        median_event_delta=0.01,
        fits=fits,
    )
    assert gate["all_five_market_logit_slopes_positive"] is False
    assert "nonpositive_market_logit_slope" in gate["automatic_failure_reasons"]
    assert gate["passed"] is False


def test_predeclaration_fingerprint_is_the_frozen_checkpoint18b_value():
    assert (
        FROZEN_PREDECLARATION_FINGERPRINT
        == "a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537"
    )

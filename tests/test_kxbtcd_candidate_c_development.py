from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import math

import pytest

from src.kxbtcd_candidate_b_failure_analysis import DevelopmentPrediction
from src.kxbtcd_candidate_c_development import (
    CandidateCObservation,
    FeatureScaler,
    KxbtcdCandidateCDevelopmentError,
    _canonical_sha256,
    _week_map_payload,
    build_candidate_c_observations,
    compute_fit_fold_scaler,
    evaluate_advancement_gate,
    event_weighted_metrics,
    fit_candidate_c_fold,
    select_lambda_from_pooled_oof,
    validate_week_map_document,
)


def _weeks(count: int = 58) -> list[str]:
    return [f"2025-W{index:02d}" for index in range(count)]


def _document_for_weeks(weeks: list[str]) -> dict:
    payload = _week_map_payload(weeks)
    document = dict(payload)
    document["week_map_fingerprint"] = _canonical_sha256(payload)
    document["derivation_outcomes_used"] = False
    document["locked_test_outcomes_opened"] = 0
    return document


def _obs(
    *,
    state: str,
    event: str,
    block: int,
    outcome: int,
    q: float,
    spread: float,
) -> CandidateCObservation:
    logit = math.log(q / (1.0 - q))
    return CandidateCObservation(
        state_id=state,
        event_ticker=event,
        market_ticker=f"M-{state}",
        utc_week_start=f"W{block}",
        block=block,
        outcome=outcome,
        q_market=q,
        market_logit=logit,
        spread=spread,
        market_logit_x_spread=logit * spread,
    )


def test_week_map_is_balanced_contiguous_and_fingerprinted() -> None:
    document = _document_for_weeks(_weeks())
    mapping = validate_week_map_document(document)
    counts = [sum(1 for value in mapping.values() if value == block) for block in range(5)]
    assert counts == [12, 12, 12, 11, 11]
    ordered = [mapping[week] for week in sorted(mapping)]
    assert ordered == sorted(ordered)


def test_week_map_rejects_post_freeze_assignment_change() -> None:
    document = _document_for_weeks(_weeks())
    document["week_to_block"][0]["block"] = "B4"
    payload_keys = [
        "schema_version",
        "candidate_id",
        "candidate_c_predeclaration_fingerprint",
        "frozen_preoutcome_run_id",
        "dataset_fingerprint",
        "split_fingerprint",
        "chronology_unit",
        "block_rule",
        "development_week_count",
        "block_week_counts",
        "week_to_block",
    ]
    document["week_map_fingerprint"] = _canonical_sha256({key: document[key] for key in payload_keys})
    with pytest.raises(KxbtcdCandidateCDevelopmentError):
        validate_week_map_document(document)


def test_scaler_uses_only_rows_passed_to_fit_fold() -> None:
    fit_rows = (
        _obs(state="a", event="E1", block=0, outcome=0, q=0.30, spread=0.01),
        _obs(state="b", event="E2", block=0, outcome=1, q=0.70, spread=0.03),
    )
    scaler = compute_fit_fold_scaler(fit_rows)
    means_before = scaler.means
    _ = _obs(state="future", event="E3", block=1, outcome=1, q=0.99, spread=0.50)
    assert scaler.means == means_before
    assert scaler.population_stds[0] > 0
    assert scaler.population_stds[1] > 0
    assert scaler.population_stds[2] > 0


def test_scaler_fails_closed_on_zero_variance() -> None:
    rows = (
        _obs(state="a", event="E1", block=0, outcome=0, q=0.40, spread=0.02),
        _obs(state="b", event="E2", block=0, outcome=1, q=0.40, spread=0.02),
    )
    with pytest.raises(KxbtcdCandidateCDevelopmentError):
        compute_fit_fold_scaler(rows)


def test_lambda_exact_tie_chooses_larger_penalty() -> None:
    losses = {
        Decimal("0.01"): 0.2,
        Decimal("0.1"): 0.1,
        Decimal("1"): 0.1,
        Decimal("10"): 0.3,
    }
    assert select_lambda_from_pooled_oof(losses) == Decimal("1")


def test_advancement_gate_requires_all_three_conditions() -> None:
    passed = evaluate_advancement_gate(
        raw_pooled=type("M", (), {"log_loss": 0.20, "brier": 0.10})(),
        candidate_pooled=type("M", (), {"log_loss": 0.19, "brier": 0.10})(),
        per_fold_raw_log_loss=[0.2, 0.2, 0.2, 0.2],
        per_fold_candidate_log_loss=[0.19, 0.19, 0.19, 0.21],
    )
    assert passed["passed"] is True
    failed = evaluate_advancement_gate(
        raw_pooled=type("M", (), {"log_loss": 0.20, "brier": 0.10})(),
        candidate_pooled=type("M", (), {"log_loss": 0.19, "brier": 0.11})(),
        per_fold_raw_log_loss=[0.2, 0.2, 0.2, 0.2],
        per_fold_candidate_log_loss=[0.19, 0.19, 0.19, 0.21],
    )
    assert failed["passed"] is False


def test_event_weighting_gives_each_event_equal_total_weight() -> None:
    rows = (
        _obs(state="a1", event="E1", block=1, outcome=0, q=0.20, spread=0.01),
        _obs(state="a2", event="E1", block=1, outcome=0, q=0.20, spread=0.02),
        _obs(state="a3", event="E1", block=1, outcome=0, q=0.20, spread=0.03),
        _obs(state="b1", event="E2", block=1, outcome=1, q=0.80, spread=0.02),
    )
    probabilities = [0.2, 0.2, 0.2, 0.8]
    metrics = event_weighted_metrics(rows, probabilities)
    expected_event_loss = -math.log(0.8)
    assert metrics.log_loss == pytest.approx(expected_event_loss)


def test_fold_fit_is_deterministic_and_converges() -> None:
    rows = (
        _obs(state="a", event="E1", block=0, outcome=0, q=0.25, spread=0.01),
        _obs(state="b", event="E2", block=0, outcome=0, q=0.35, spread=0.04),
        _obs(state="c", event="E3", block=0, outcome=1, q=0.65, spread=0.02),
        _obs(state="d", event="E4", block=0, outcome=1, q=0.75, spread=0.05),
        _obs(state="e", event="E5", block=0, outcome=1, q=0.55, spread=0.03),
    )
    scaler = compute_fit_fold_scaler(rows)
    fit1 = fit_candidate_c_fold(
        rows,
        lambda_value=Decimal("0.1"),
        fold_index=1,
        fit_blocks=(0,),
        score_block=1,
        scaler=scaler,
    )
    fit2 = fit_candidate_c_fold(
        rows,
        lambda_value=Decimal("0.1"),
        fold_index=1,
        fit_blocks=(0,),
        score_block=1,
        scaler=scaler,
    )
    assert fit1.converged is True
    assert fit1.coefficients == fit2.coefficients
    assert fit1.iterations == fit2.iterations


def test_observation_builder_rejects_locked_test_partition() -> None:
    prediction = DevelopmentPrediction(
        partition="locked_test",
        state_id="S1",
        event_ticker="E1",
        market_ticker="M1",
        utc_week_start="W0",
        event_close_time_utc="2026-01-01T00:00:00Z",
        time_to_close_seconds=3300.0,
        strike_dollars=100000.0,
        spread=0.01,
        structural_role="q50",
        q_market=0.5,
        candidate_b_probability=0.5,
        outcome=1,
        raw_log_loss=0.69,
        candidate_b_log_loss=0.69,
        raw_brier=0.25,
        candidate_b_brier=0.25,
    )
    with pytest.raises(KxbtcdCandidateCDevelopmentError):
        build_candidate_c_observations((prediction,), {"W0": 0}, enforce_canonical_counts=False)

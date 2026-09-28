from __future__ import annotations

from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_c3_evaluation import (
    CHAMPION_R2_BETA_DISTANCE,
    C3_ELIGIBLE_EVENT_TARGET,
    C3_MARKET_COUNT,
    C3_ROW_COUNT,
    C3_STRICT_TAIL_END_EXCLUSIVE,
    C3_STRICT_TAIL_REMAINING,
    CandidateEC3EvaluationError,
    _create_or_validate_c3_attempt,
    assert_not_prior_exposed_identity,
    passes_c3_validation_gate,
    predict_c3_probability,
)


def test_c3_frozen_identity_constants() -> None:
    assert C3_ELIGIBLE_EVENT_TARGET == 500
    assert C3_ROW_COUNT == 13549
    assert C3_MARKET_COUNT == 2470
    assert C3_STRICT_TAIL_END_EXCLUSIVE == 4755
    assert C3_STRICT_TAIL_REMAINING == 4676
    assert C3_STRICT_TAIL_REMAINING - 4500 == 176
    assert float(CHAMPION_R2_BETA_DISTANCE) > 0.0


def test_c3_prediction_moves_with_btc_distance() -> None:
    beta = float(CHAMPION_R2_BETA_DISTANCE)
    at_strike = predict_c3_probability(
        q_market=0.50,
        d_btc=0.0,
        beta_distance=beta,
    )
    above = predict_c3_probability(
        q_market=0.50,
        d_btc=25.0,
        beta_distance=beta,
    )
    below = predict_c3_probability(
        q_market=0.50,
        d_btc=-25.0,
        beta_distance=beta,
    )
    assert below < at_strike < above
    assert at_strike == pytest.approx(0.5)


def test_c3_gate_requires_four_blocks_and_newest_win() -> None:
    common = dict(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        median_event_raw_minus_candidate_log_loss=0.005,
        champion_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )
    assert passes_c3_validation_gate(
        block_raw_minus_candidate_log_loss=[
            0.01,
            0.02,
            0.03,
            -0.01,
            0.02,
        ],
        **common,
    )
    assert not passes_c3_validation_gate(
        block_raw_minus_candidate_log_loss=[
            0.01,
            0.02,
            0.03,
            0.04,
            -0.01,
        ],
        **common,
    )
    assert not passes_c3_validation_gate(
        block_raw_minus_candidate_log_loss=[
            0.01,
            0.02,
            -0.03,
            -0.01,
            0.02,
        ],
        **common,
    )


def test_c3_gate_treats_primary_tie_as_fail() -> None:
    assert not passes_c3_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.0,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[
            0.01,
            0.02,
            0.03,
            0.04,
            0.05,
        ],
        median_event_raw_minus_candidate_log_loss=0.005,
        champion_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_c3_hard_deny_rejects_prior_identity() -> None:
    with pytest.raises(CandidateEC3EvaluationError):
        assert_not_prior_exposed_identity(
            prior_events=frozenset({"OLD_EVENT"}),
            prior_markets=frozenset(),
            event_ticker="OLD_EVENT",
            market_ticker="NEW_MARKET",
        )
    with pytest.raises(CandidateEC3EvaluationError):
        assert_not_prior_exposed_identity(
            prior_events=frozenset(),
            prior_markets=frozenset({"OLD_MARKET"}),
            event_ticker="NEW_EVENT",
            market_ticker="OLD_MARKET",
        )
    assert_not_prior_exposed_identity(
        prior_events=frozenset({"OLD_EVENT"}),
        prior_markets=frozenset({"OLD_MARKET"}),
        event_ticker="NEW_EVENT",
        market_ticker="NEW_MARKET",
    )


def test_c3_attempt_receipt_blocks_fresh_second_attempt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "c3_attempt.json"
    implementation = {
        "c3_implementation_fingerprint": "a" * 64,
    }
    first = _create_or_validate_c3_attempt(
        path=path,
        implementation_freeze=implementation,
        git_head="b" * 40,
        resume_manifest=None,
    )
    assert first["C3_permanently_exposed"] is True
    assert first["remaining_reserve_accessed"] is False

    with pytest.raises(CandidateEC3EvaluationError):
        _create_or_validate_c3_attempt(
            path=path,
            implementation_freeze=implementation,
            git_head="b" * 40,
            resume_manifest=None,
        )

    resumed = _create_or_validate_c3_attempt(
        path=path,
        implementation_freeze=implementation,
        git_head="b" * 40,
        resume_manifest=tmp_path / "manifest.json",
    )
    assert resumed["fresh_second_C3_attempt_allowed"] is False

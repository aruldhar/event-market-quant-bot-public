from __future__ import annotations

import pytest

from src.kxbtcd_candidate_e_final_fit import (
    FINAL_EVENT_COUNT,
    FINAL_ROW_COUNT,
    STRICT_UNTOUCHED_TAIL_REMAINING,
)
from src.kxbtcd_candidate_e_h1_evaluation import (
    CandidateEObservation,
    DISTANCE_CANDIDATE_ID,
    fit_candidate_e,
)


def test_final_fit_frozen_scope_constants() -> None:
    assert FINAL_EVENT_COUNT == 4500
    assert FINAL_ROW_COUNT == 123520
    assert STRICT_UNTOUCHED_TAIL_REMAINING == 4676


def test_final_fit_reuses_one_parameter_distance_optimizer() -> None:
    observations = (
        CandidateEObservation(
            state_id="a",
            event_ticker="E1",
            market_ticker="M1",
            block_id="H1",
            structural_role="q50",
            ttc_target_minutes=30,
            outcome=1,
            q_market=0.5,
            d_btc=10.0,
            r_5m=0.0,
        ),
        CandidateEObservation(
            state_id="b",
            event_ticker="E2",
            market_ticker="M2",
            block_id="C3",
            structural_role="q50",
            ttc_target_minutes=30,
            outcome=0,
            q_market=0.5,
            d_btc=-10.0,
            r_5m=0.0,
        ),
    )
    fit = fit_candidate_e(
        observations,
        candidate_id=DISTANCE_CANDIDATE_ID,
        fold=0,
        fit_blocks=("H1", "C3"),
        score_block="POST_HISTORICAL_CONFIRMATION",
    )
    assert fit.converged is True
    assert fit.beta_distance > 0.0
    assert fit.beta_momentum is None


def test_final_fit_scope_arithmetic() -> None:
    assert (
        36314
        + 22354
        + 22409
        + 14887
        + 14007
        + 13549
    ) == FINAL_ROW_COUNT
    assert (
        1500 + 750 + 750 + 500 + 500 + 500
    ) == FINAL_EVENT_COUNT

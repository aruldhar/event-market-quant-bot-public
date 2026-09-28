from __future__ import annotations

import copy

import pytest

from src.kxbtcd_candidate_e_h1_result_closeout import (
    CandidateEH1ResultCloseoutError,
    DISTANCE_ID,
    EXPECTED_RESULT_FINGERPRINT,
    EXPECTED_SUMMARY,
    MOMENTUM_ID,
    advancement_decision,
    canonical_summary_fingerprint,
    validate_coefficients,
    validate_fold_rows,
    validate_summary,
)


def test_frozen_summary_fingerprint_matches_observed_h1_result():
    assert canonical_summary_fingerprint(EXPECTED_SUMMARY) == EXPECTED_RESULT_FINGERPRINT
    assert validate_summary(EXPECTED_SUMMARY)["selection"] == DISTANCE_ID


def test_summary_rejects_posthoc_selection_change():
    altered = copy.deepcopy(EXPECTED_SUMMARY)
    altered["selection"] = MOMENTUM_ID
    with pytest.raises(CandidateEH1ResultCloseoutError):
        validate_summary(altered)


def test_summary_rejects_h2_exposure():
    altered = copy.deepcopy(EXPECTED_SUMMARY)
    altered["H2_outcomes_opened"] = True
    with pytest.raises(CandidateEH1ResultCloseoutError):
        validate_summary(altered)


def test_advancement_decision_selects_distance_and_keeps_h2_h3_sealed():
    decision = advancement_decision(EXPECTED_SUMMARY)
    assert decision["H1_result"] == "PASS"
    assert decision["selected_candidate_id"] == DISTANCE_ID
    assert decision["momentum_nested_complexity_gate_passed"] is False
    assert decision["nested_score_block_win_count"] == 2
    assert decision["H2_outcomes_opened"] is False
    assert decision["H3_outcomes_opened"] is False
    assert decision["execution_authorized"] is False


def _fold(candidate, block, raw, candidate_loss):
    return {
        "candidate_id": candidate,
        "score_block": block,
        "raw_log_loss": raw,
        "candidate_log_loss": candidate_loss,
    }


def test_fold_validator_reproduces_two_of_five_nested_wins():
    rows = [
        _fold(DISTANCE_ID, "B2", "0.093684502220090865", "0.029051861012645085"),
        _fold(DISTANCE_ID, "B3", "0.12302918031242148", "0.047419469633196702"),
        _fold(DISTANCE_ID, "B4", "0.11679455386971177", "0.046742849808794153"),
        _fold(DISTANCE_ID, "B5", "0.099600791943792746", "0.031252646282291463"),
        _fold(DISTANCE_ID, "B6", "0.091628731058039634", "0.014517154305671688"),
        _fold(MOMENTUM_ID, "B2", "0.093684502220090865", "0.029095643179052749"),
        _fold(MOMENTUM_ID, "B3", "0.12302918031242148", "0.047474599718853823"),
        _fold(MOMENTUM_ID, "B4", "0.11679455386971177", "0.046667401094384733"),
        _fold(MOMENTUM_ID, "B5", "0.099600791943792746", "0.031262413260748696"),
        _fold(MOMENTUM_ID, "B6", "0.091628731058039634", "0.014471587207905503"),
    ]
    validate_fold_rows(rows)


def _coef(candidate, block, beta_distance, beta_momentum):
    return {
        "candidate_id": candidate,
        "score_block": block,
        "beta_distance": beta_distance,
        "beta_momentum": beta_momentum,
        "converged": "true",
    }


def test_coefficient_validator_requires_all_positive_distance_slopes():
    rows = [
        _coef(DISTANCE_ID, "B2", "0.0081323383310510297", ""),
        _coef(DISTANCE_ID, "B3", "0.0095589432277629807", ""),
        _coef(DISTANCE_ID, "B4", "0.010172158015085328", ""),
        _coef(DISTANCE_ID, "B5", "0.010887612715427673", ""),
        _coef(DISTANCE_ID, "B6", "0.011430502474609366", ""),
        _coef(MOMENTUM_ID, "B2", "0.0081814345452425261", "-0.0046668713049018524"),
        _coef(MOMENTUM_ID, "B3", "0.0095989058569614649", "-0.0043868382514955905"),
        _coef(MOMENTUM_ID, "B4", "0.01019923586183839", "-0.0039735264782275017"),
        _coef(MOMENTUM_ID, "B5", "0.010918049920250599", "-0.0043955867905513439"),
        _coef(MOMENTUM_ID, "B6", "0.011460281132241925", "-0.0042615767375541423"),
    ]
    validate_coefficients(rows)
    rows[0]["beta_distance"] = "-0.0081323383310510297"
    with pytest.raises(CandidateEH1ResultCloseoutError):
        validate_coefficients(rows)

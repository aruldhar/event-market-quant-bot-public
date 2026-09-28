"""Checkpoint-18C Candidate-D development result closeout.

This module validates the already-completed exposed-development result and
encodes the frozen advancement decision.  It does not fit, retune, rescore,
collect data, access terminal data, or enable execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

CANDIDATE_ID = "kxbtcd_market_logit_recalibration.v1"
EXPECTED_RUN_STAMP = "20260815T234004Z"
EXPECTED_RESULT_FINGERPRINT = "b72617517d7bbc3bc1e01ff332496efaf5ba0c64c5eb445f82574e63fa4a47ab"
EXPECTED_PREDECLARATION_FINGERPRINT = "a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537"
EXPECTED_WEEK_MAP_FINGERPRINT = "ba93f6a063c616a34437d6f9d208e39b85c993868c71ea78db8b40a70ec23dff"

EXPECTED = {
    "development_event_count": 231,
    "development_row_count": 5364,
    "oof_event_count": 160,
    "oof_row_count": 3726,
    "raw_pooled_oof_event_weighted_log_loss": 0.15456664732282768,
    "candidate_d_pooled_oof_event_weighted_log_loss": 0.15159108042312835,
    "delta_log_loss_raw_minus_candidate_d": 0.002975566899699328,
    "raw_pooled_oof_event_weighted_brier": 0.037893942261917626,
    "candidate_d_pooled_oof_event_weighted_brier": 0.026426318458628383,
    "delta_brier_raw_minus_candidate_d": 0.011467623803289244,
    "median_event_delta_log_loss_raw_minus_candidate_d": 0.04671924978445033,
    "candidate_d_better_event_count": 149,
    "candidate_d_worse_event_count": 11,
    "candidate_d_tie_event_count": 0,
    "development_screen_passed": False,
    "candidate_d_fit_count": 5,
    "candidate_d_hyperparameter_search_performed": False,
    "candidate_d_regularization_used": False,
    "terminal_result_artifact_loaded": False,
    "terminal_rows_loaded": 0,
    "terminal_labels_loaded": 0,
    "terminal_features_loaded": 0,
    "network_requests": 0,
    "execution_enabled": False,
    "orders_placed": 0,
}

EXPECTED_GATE = {
    "pooled_oof_log_loss_strictly_better": True,
    "pooled_oof_brier_no_worse": True,
    "score_block_log_loss_win_count": 3,
    "at_least_4_of_5_score_blocks_better": False,
    "latest_B6_log_loss_strictly_better": False,
    "median_event_log_loss_delta_positive": True,
    "all_five_fits_converged_and_finite": True,
    "all_five_market_logit_slopes_positive": True,
    "automatic_failure_reasons": [
        "fewer_than_4_of_5_score_block_log_loss_wins",
        "latest_B6_log_loss_not_strictly_better",
    ],
    "passed": False,
}

EXPECTED_FOLD_DELTAS = [
    ("B2", 0.093203479823316726, 0.014792100067968545),
    ("B3", 0.0061807888233462449, 0.019514709544529128),
    ("B4", 0.076486093656489507, 0.021339318056821609),
    ("B5", -0.029863425409502709, 0.0084444935043224527),
    ("B6", -0.13112910239515319, -0.0067525021571954863),
]

EXPECTED_SLOPES = [
    3.1982462074078875,
    3.4689767579266322,
    2.6971700475935849,
    2.7317860853200795,
    2.3714201483058033,
]


class CandidateDResultCloseoutError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise CandidateDResultCloseoutError(message)


def _same_number(left: Any, right: Any, name: str) -> None:
    if float(left) != float(right):
        _error(f"{name} changed: {left!r} != {right!r}")


def validate_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    if summary.get("candidate_id") != CANDIDATE_ID:
        _error("Candidate-D result candidate ID mismatch")
    if summary.get("candidate_d_predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("Candidate-D predeclaration fingerprint mismatch")
    if summary.get("week_map_fingerprint") != EXPECTED_WEEK_MAP_FINGERPRINT:
        _error("Candidate-D week-map fingerprint mismatch")
    if summary.get("evaluation_result_fingerprint") != EXPECTED_RESULT_FINGERPRINT:
        _error("Candidate-D evaluation result fingerprint mismatch")

    for key, expected in EXPECTED.items():
        observed = summary.get(key)
        if isinstance(expected, float):
            _same_number(observed, expected, key)
        elif observed != expected:
            _error(f"{key} changed: {observed!r} != {expected!r}")

    gate = summary.get("development_advancement_gate")
    if not isinstance(gate, Mapping):
        _error("Candidate-D advancement gate missing")
    for key, expected in EXPECTED_GATE.items():
        observed = gate.get(key)
        if key == "automatic_failure_reasons":
            if list(observed or []) != expected:
                _error("Candidate-D automatic failure reasons changed")
        elif observed != expected:
            _error(f"Candidate-D gate field {key} changed")

    if summary.get("development_screen_passed") is not False or gate.get("passed") is not False:
        _error("Candidate D must remain a development FAIL")

    return dict(summary)


def load_and_validate_result(repository_root: str | Path = ".") -> tuple[dict[str, Any], Path]:
    root = Path(repository_root).resolve()
    path = (
        root
        / "data"
        / "analysis"
        / "kxbtcd_candidate_d_development"
        / EXPECTED_RUN_STAMP
        / "candidate_d_development_summary.json"
    )
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateDResultCloseoutError(f"could not load Candidate-D result: {exc}") from exc
    if not isinstance(summary, Mapping):
        _error("Candidate-D result root must be an object")
    return validate_summary(summary), path


def advancement_decision(summary: Mapping[str, Any]) -> dict[str, Any]:
    validate_summary(summary)
    return {
        "candidate_id": CANDIDATE_ID,
        "development_result": "FAIL",
        "advance_candidate_d": False,
        "failure_reasons": list(EXPECTED_GATE["automatic_failure_reasons"]),
        "post_hoc_candidate_d_repair_on_same_screen_authorized": False,
        "final_development_fit_authorized": False,
        "prospective_terminal_evaluation_authorized": False,
        "execution_authorized": False,
        "interpretation": (
            "Candidate D improved pooled development metrics and most events, but failed "
            "the frozen temporal-stability gate because it won only 3/5 score blocks and "
            "did not beat raw in latest block B6."
        ),
    }

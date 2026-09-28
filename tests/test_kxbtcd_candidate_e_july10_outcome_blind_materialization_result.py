from __future__ import annotations

from copy import deepcopy

import pytest

from src.kxbtcd_candidate_e_july10_outcome_blind_materialization_result import (
    EXPECTED_DECISION_STATUS_COUNTS,
    canonical_fingerprint,
    build_closeout_document,
    summarize_materialization,
    validate_closeout_document,
    OutcomeBlindMaterializationCloseoutError,
)


def test_closeout_fingerprint_is_stable():
    document = build_closeout_document()
    assert document["result_closeout_fingerprint"] == canonical_fingerprint(document)
    assert document["interpretation"]["evaluation_status"] == (
        "NON_EVALUABLE_NO_VALID_TWO_SIDED_DECISION_STATE"
    )
    assert document["interpretation"]["settlement_outcomes_needed_for_this_sample"] is False


def test_closeout_rejects_mutation():
    document = build_closeout_document()
    mutated = deepcopy(document)
    mutated["materialization"]["execution_scenario_count"] = 1
    with pytest.raises(OutcomeBlindMaterializationCloseoutError):
        validate_closeout_document(mutated)


def test_materialization_summary_distinguishes_non_evaluable_from_zero_edge():
    payload = {
        "structural_markets": [{} for _ in range(20)],
        "decision_states": [
            {
                "status": "INVALID_TWO_SIDED_BOOK",
                "signal_candidates": [],
            }
            for _ in range(73)
        ] + [
            {
                "status": "SOURCE_UNAVAILABLE_DECISION_TIMESTAMP",
                "signal_candidates": [],
            }
            for _ in range(47)
        ],
        "threshold_selections": [
            {"selected_signal": None}
            for _ in range(20)
        ],
        "execution_scenarios": [],
    }
    summary = summarize_materialization(payload)
    assert summary["structural_market_count"] == 20
    assert summary["decision_state_count"] == 120
    assert summary["decision_status_counts"] == EXPECTED_DECISION_STATUS_COUNTS
    assert summary["signal_candidate_count"] == 0
    assert summary["selected_signal_count"] == 0
    assert summary["execution_scenario_count"] == 0

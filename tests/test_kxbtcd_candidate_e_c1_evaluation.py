from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_c1_evaluation import (
    C1_MARKET_COUNT,
    C1_VALIDATION_FINGERPRINT,
    CandidateEC1EvaluationError,
    DEFAULT_C1_IMPLEMENTATION_FREEZE_PATH,
    _c1_request_plan,
    assert_not_prior_exposed_identity,
    passes_c1_validation_gate,
    predict_c1_probability,
    validate_c1_implementation_freeze_document,
    validate_c1_validation_freeze_document,
)
from src.kxbtcd_candidate_e_c1_preparation import C1_VALIDATION_FREEZE_PATH


def test_tracked_c1_validation_freeze_is_exact() -> None:
    document = json.loads(Path(C1_VALIDATION_FREEZE_PATH).read_text(encoding="utf-8"))
    validated = validate_c1_validation_freeze_document(document)
    assert validated["c1_validation_fingerprint"] == C1_VALIDATION_FINGERPRINT
    assert len(_c1_request_plan(validated)) == C1_MARKET_COUNT
    assert validated["C1_outcomes_opened"] is False
    assert validated["C2_C3_materialized"] is False


def test_frozen_gate_passes_only_with_all_primary_requirements() -> None:
    base = dict(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.0,
        block_raw_minus_candidate_log_loss=[0.01, 0.01, -0.01, 0.01, 0.01],
        median_event_raw_minus_candidate_log_loss=0.01,
        champion_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )
    assert passes_c1_validation_gate(**base)

    for key, value in (
        ("pooled_raw_minus_candidate_log_loss", 0.0),
        ("pooled_raw_minus_candidate_brier", -1e-12),
        ("median_event_raw_minus_candidate_log_loss", 0.0),
        ("champion_model_valid", False),
        ("structural_coverage_ok", False),
        ("policy_firewall_ok", False),
    ):
        changed = dict(base)
        changed[key] = value
        assert not passes_c1_validation_gate(**changed)


def test_frozen_gate_requires_four_blocks_and_newest_win() -> None:
    assert not passes_c1_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.01,
        block_raw_minus_candidate_log_loss=[0.01, 0.01, 0.01, -0.01, -0.01],
        median_event_raw_minus_candidate_log_loss=0.01,
        champion_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )
    assert not passes_c1_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.01,
        block_raw_minus_candidate_log_loss=[0.01, 0.01, 0.01, 0.01, 0.0],
        median_event_raw_minus_candidate_log_loss=0.01,
        champion_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_distance_model_nests_raw_probability_at_zero_distance() -> None:
    for q in (0.001, 0.1, 0.5, 0.9, 0.999):
        predicted = predict_c1_probability(
            q_market=q,
            d_btc=0.0,
            beta_distance=0.014447239079794087,
        )
        assert math.isclose(predicted, q, rel_tol=0.0, abs_tol=1e-15)


def test_prior_exposed_identity_is_hard_denied() -> None:
    with pytest.raises(CandidateEC1EvaluationError):
        assert_not_prior_exposed_identity(
            prior_events=frozenset({"OLD-EVENT"}),
            prior_markets=frozenset(),
            event_ticker="OLD-EVENT",
            market_ticker="NEW-MARKET",
        )
    with pytest.raises(CandidateEC1EvaluationError):
        assert_not_prior_exposed_identity(
            prior_events=frozenset(),
            prior_markets=frozenset({"OLD-MARKET"}),
            event_ticker="NEW-EVENT",
            market_ticker="OLD-MARKET",
        )


def test_generated_implementation_freeze_validates_without_outcome_access() -> None:
    path = Path(DEFAULT_C1_IMPLEMENTATION_FREEZE_PATH)
    assert path.is_file(), "run the Checkpoint-21C freeze script before focused tests"
    document = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_c1_implementation_freeze_document(
        document,
        repo=Path(".").resolve(),
        verify_parent=True,
        verify_implementation_hashes=True,
        verify_local_frozen_data=False,
    )
    assert validated["C1_outcomes_opened_at_freeze"] == 0
    assert validated["network_requests_at_freeze"] == 0
    assert validated["orders_placed"] == 0


def test_implementation_freeze_tamper_fails() -> None:
    path = Path(DEFAULT_C1_IMPLEMENTATION_FREEZE_PATH)
    assert path.is_file(), "run the Checkpoint-21C freeze script before focused tests"
    document = json.loads(path.read_text(encoding="utf-8"))
    tampered = copy.deepcopy(document)
    tampered["orders_placed"] = 1
    with pytest.raises(CandidateEC1EvaluationError):
        validate_c1_implementation_freeze_document(
            tampered,
            repo=Path(".").resolve(),
            verify_parent=False,
            verify_implementation_hashes=False,
        )

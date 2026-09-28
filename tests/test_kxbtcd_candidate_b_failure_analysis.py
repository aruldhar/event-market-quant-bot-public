from __future__ import annotations

import pytest

from src.kxbtcd_candidate_b_failure_analysis import (
    DevelopmentPrediction,
    KxbtcdCandidateBFailureAnalysisError,
    _q_band,
    _same_float_value,
    _slice_metrics,
    _spread_band,
    _ttc_anchor,
    analyze_candidate_b_failure,
)
from src.kxbtcd_candidate_c_predeclaration import (
    assign_contiguous_week_blocks,
    candidate_c_predeclaration,
    candidate_c_predeclaration_fingerprint,
    validate_candidate_c_predeclaration,
)


def _row(event: str, *, raw: float, candidate: float, week: str = "2026-01-05") -> DevelopmentPrediction:
    return DevelopmentPrediction(
        partition="train",
        state_id=f"state:{event}:{raw}:{candidate}",
        event_ticker=event,
        market_ticker=f"market:{event}",
        utc_week_start=week,
        event_close_time_utc=f"{week}T12:00:00Z",
        time_to_close_seconds=3300.0,
        strike_dollars=100000.0,
        spread=0.01,
        structural_role="q50",
        q_market=0.5,
        candidate_b_probability=0.5,
        outcome=1,
        raw_log_loss=raw,
        candidate_b_log_loss=candidate,
        raw_brier=raw,
        candidate_b_brier=candidate,
    )


def test_candidate_c_predeclaration_is_frozen_and_non_authorizing() -> None:
    validate_candidate_c_predeclaration()
    spec = candidate_c_predeclaration()
    assert spec["contract_version"] == "kxbtcd_candidate_c_predeclaration.v2"
    assert spec["candidate_id"] == "kxbtcd_market_spread_interaction_logistic.v1"
    assert [feature["name"] for feature in spec["features"]] == [
        "market_logit",
        "spread",
        "market_logit_x_spread",
    ]
    assert "learned_time_to_close_term" in spec["excluded_feature_families"]
    assert spec["status_in_checkpoint_14"] == "predeclared_not_fit_not_authorized"
    assert spec["checkpoint_14_permissions"]["candidate_c_fit"] is False
    assert spec["checkpoint_14_permissions"]["locked_test_outcome_access"] is False
    assert spec["checkpoint_14_permissions"]["network_access_for_diagnostics"] is False
    assert spec["checkpoint_14_permissions"]["paper_execution"] is False
    assert candidate_c_predeclaration_fingerprint() == (
        "d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322"
    )


def test_week_blocks_are_contiguous_and_balanced() -> None:
    weeks = [f"2026-01-{day:02d}" for day in range(1, 12)]
    mapping = assign_contiguous_week_blocks(weeks, block_count=5)
    blocks = [[week for week in sorted(weeks) if mapping[week] == b] for b in range(5)]
    sizes = [len(block) for block in blocks]
    assert max(sizes) - min(sizes) <= 1
    flattened = [week for block in blocks for week in block]
    assert flattened == sorted(weeks)


def test_slice_metrics_equal_weight_events_not_rows() -> None:
    rows = [
        _row("E1", raw=0.2, candidate=0.1),
        _row("E1", raw=0.4, candidate=0.2),
        _row("E2", raw=1.0, candidate=1.2),
    ]
    metrics = _slice_metrics(rows)
    assert metrics.event_count == 2
    assert metrics.raw_log_loss == pytest.approx(((0.2 + 0.4) / 2 + 1.0) / 2)
    assert metrics.candidate_log_loss == pytest.approx(((0.1 + 0.2) / 2 + 1.2) / 2)
    assert metrics.better_events == 1
    assert metrics.worse_events == 1


def test_fixed_diagnostic_buckets() -> None:
    assert _q_band(0.0) == "[0.0,0.1)"
    assert _q_band(1.0) == "[0.9,1.0]"
    assert _spread_band(0.0) == "0"
    assert _spread_band(0.01) == "(0,0.01]"
    assert _spread_band(0.02) == "(0.01,0.02]"
    assert _spread_band(0.03) == "(0.02,0.05]"
    assert _ttc_anchor(3359.0) == "55m"
    assert _ttc_anchor(1800.0) == "30m"
    with pytest.raises(KxbtcdCandidateBFailureAnalysisError):
        _ttc_anchor(1500.0)



def test_cross_tab_slice_labels_are_deterministic() -> None:
    # The analyzer uses fixed existing bucket functions and an explicit separator,
    # so labels are stable and parseable without any data-dependent binning.
    q = _q_band(0.35)
    spread = _spread_band(0.01)
    assert f"q={q}|spread={spread}" == "q=[0.3,0.4)|spread=(0,0.01]"
    assert f"B4|spread={spread}" == "B4|spread=(0,0.01]"


def test_float_roundtrip_lineage_comparison_accepts_cp13_serialization_noise() -> None:
    assert _same_float_value(
        "0.71999999999999997",
        "0.72",
        left_name="prediction.q_market",
        right_name="preoutcome.q_market",
    )
    assert _same_float_value(
        "83749.990000000005",
        "83749.99",
        left_name="prediction.strike",
        right_name="preoutcome.strike",
    )
    assert not _same_float_value(
        "0.71",
        "0.72",
        left_name="prediction.q_market",
        right_name="preoutcome.q_market",
    )

def test_analysis_rejects_non_development_partition() -> None:
    row = _row("E1", raw=0.2, candidate=0.1)
    locked = DevelopmentPrediction(**{**row.__dict__, "partition": "locked_test"})
    with pytest.raises(KxbtcdCandidateBFailureAnalysisError):
        analyze_candidate_b_failure([locked], provenance={})

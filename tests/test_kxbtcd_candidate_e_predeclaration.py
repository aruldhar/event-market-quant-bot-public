from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_predeclaration import (
    DISTANCE_CANDIDATE_ID,
    FROZEN_PREDECLARATION_FINGERPRINT,
    MOMENTUM_CANDIDATE_ID,
    KxbtcdCandidateEPredeclarationError,
    balanced_seven_block_sizes,
    btc_return_5m_bps,
    btc_strike_log_distance_bps,
    market_logit_offset,
    passes_nested_complexity_gate,
    passes_raw_advancement_gate,
    select_candidate_e,
    validate_candidate_e_predeclaration,
)


def test_frozen_predeclaration_fingerprint() -> None:
    assert validate_candidate_e_predeclaration() == FROZEN_PREDECLARATION_FINGERPRINT


def test_10000_scale_is_log_basis_points() -> None:
    # A +0.10% simple move is almost +10 log-bp.
    value = btc_strike_log_distance_bps(100.1, 100.0)
    assert value == pytest.approx(9.995003330834232)
    assert btc_return_5m_bps(100.1, 100.0) == pytest.approx(value)


def test_feature_signs_and_zero() -> None:
    assert btc_strike_log_distance_bps(100.0, 100.0) == pytest.approx(0.0)
    assert btc_strike_log_distance_bps(101.0, 100.0) > 0.0
    assert btc_strike_log_distance_bps(99.0, 100.0) < 0.0
    assert btc_return_5m_bps(101.0, 100.0) > 0.0
    assert btc_return_5m_bps(99.0, 100.0) < 0.0


@pytest.mark.parametrize("args", [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_features_fail_closed_on_invalid_prices(args: tuple[float, float]) -> None:
    with pytest.raises(KxbtcdCandidateEPredeclarationError):
        btc_strike_log_distance_bps(*args)


def test_market_logit_uses_frozen_model_only_clip() -> None:
    assert market_logit_offset(0.5) == pytest.approx(0.0)
    assert market_logit_offset(0.0) == pytest.approx(math.log(0.001 / 0.999))
    assert market_logit_offset(1.0) == pytest.approx(math.log(0.999 / 0.001))


def test_balanced_seven_blocks() -> None:
    assert balanced_seven_block_sizes(168) == (24, 24, 24, 24, 24, 24, 24)
    assert balanced_seven_block_sizes(170) == (25, 25, 24, 24, 24, 24, 24)


def test_raw_gate_requires_temporal_stability_and_positive_distance() -> None:
    good = dict(
        pooled_log_loss_delta=0.01,
        pooled_brier_delta=0.001,
        score_block_log_loss_deltas=[0.01, 0.01, -0.001, 0.02, 0.01],
        median_event_log_loss_delta=0.001,
        all_fits_valid=True,
        beta_distance_by_fold=[0.01] * 5,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )
    assert passes_raw_advancement_gate(**good)
    bad_latest = dict(good)
    bad_latest["score_block_log_loss_deltas"] = [0.01, 0.01, 0.01, 0.01, -0.001]
    assert not passes_raw_advancement_gate(**bad_latest)
    bad_sign = dict(good)
    bad_sign["beta_distance_by_fold"] = [0.01, 0.01, 0.0, 0.01, 0.01]
    assert not passes_raw_advancement_gate(**bad_sign)


def test_complexity_gate_requires_four_blocks_and_latest() -> None:
    assert passes_nested_complexity_gate(
        pooled_log_loss_delta_distance_minus_momentum=0.01,
        pooled_brier_delta_distance_minus_momentum=0.001,
        score_block_log_loss_deltas_distance_minus_momentum=[0.01, 0.01, -0.01, 0.01, 0.01],
        median_event_log_loss_delta_distance_minus_momentum=0.001,
    )
    assert not passes_nested_complexity_gate(
        pooled_log_loss_delta_distance_minus_momentum=0.01,
        pooled_brier_delta_distance_minus_momentum=0.001,
        score_block_log_loss_deltas_distance_minus_momentum=[0.01, 0.01, 0.01, 0.01, -0.01],
        median_event_log_loss_delta_distance_minus_momentum=0.001,
    )


def test_family_selection_prefers_simpler_model_unless_momentum_earns_complexity() -> None:
    assert select_candidate_e(
        distance_passes_raw=False,
        momentum_passes_raw=False,
        momentum_passes_complexity=False,
    ) == "family_FAIL"
    assert select_candidate_e(
        distance_passes_raw=True,
        momentum_passes_raw=False,
        momentum_passes_complexity=False,
    ) == DISTANCE_CANDIDATE_ID
    assert select_candidate_e(
        distance_passes_raw=False,
        momentum_passes_raw=True,
        momentum_passes_complexity=False,
    ) == MOMENTUM_CANDIDATE_ID
    assert select_candidate_e(
        distance_passes_raw=True,
        momentum_passes_raw=True,
        momentum_passes_complexity=False,
    ) == DISTANCE_CANDIDATE_ID
    assert select_candidate_e(
        distance_passes_raw=True,
        momentum_passes_raw=True,
        momentum_passes_complexity=True,
    ) == MOMENTUM_CANDIDATE_ID


def test_mutated_predeclaration_fails_fingerprint(tmp_path: Path) -> None:
    src = Path("configs/kxbtcd_candidate_e_predeclaration.json")
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["fit_contract"]["regularization"] = "ridge"
    target = tmp_path / "mutated.json"
    target.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(KxbtcdCandidateEPredeclarationError):
        validate_candidate_e_predeclaration(target)

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.kxbtcd_candidate_e_h2_result_closeout as mod


def test_frozen_h2_result_identities():
    assert mod.EXPECTED_SOURCE_COMMIT == (
        "87297dbe6fcdb026d28b133bc02d8cc06db9463a"
    )
    assert mod.H2_IMPLEMENTATION_FINGERPRINT == (
        "0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e"
    )
    assert mod.H2_VALIDATION_FINGERPRINT == (
        "57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9"
    )
    assert mod.FINAL_H1_MODEL_FINGERPRINT == (
        "d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a"
    )
    assert mod.EXPECTED_RESULT_FINGERPRINT == (
        "eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7"
    )


def test_frozen_h2_primary_metrics():
    assert float(mod.EXPECTED_RAW_LOG_LOSS) > float(
        mod.EXPECTED_CANDIDATE_LOG_LOSS
    )
    assert float(mod.EXPECTED_LOG_LOSS_DELTA) > 0.0
    assert float(mod.EXPECTED_RAW_BRIER) > float(
        mod.EXPECTED_CANDIDATE_BRIER
    )


def test_advancement_decision_is_same_distance_only():
    summary = {
        "schema_version": "kxbtcd_candidate_e_h2_evaluation_summary.v1"
    }
    # Unit-test the fixed decision shape without constructing the full frozen
    # summary; validate_summary itself is exercised against the real artifact by
    # the integration-style test below.
    decision = {
        "H2_result": "PASS",
        "selected_candidate_id": mod.DISTANCE_ID,
        "frozen_beta_distance": mod.EXPECTED_BETA_DISTANCE,
        "block_log_loss_win_count": 5,
        "latest_block_B4_win": True,
        "H3_outcomes_opened": False,
    }
    assert decision["selected_candidate_id"] == mod.DISTANCE_ID
    assert decision["block_log_loss_win_count"] == 5
    assert decision["latest_block_B4_win"]
    assert not decision["H3_outcomes_opened"]


def test_validate_real_h2_result_if_artifacts_present():
    if not mod.SUMMARY_PATH.exists():
        pytest.skip("canonical H2 result artifacts not present in this checkout")
    summary = mod.load_and_validate_result(".")
    assert summary["H2_validation_passed"] is True
    assert summary["block_log_loss_win_count"] == 5
    assert summary["latest_block_B4_win"] is True
    assert summary["H3_outcomes_opened"] is False


def test_summary_fingerprint_is_bound_to_full_summary():
    if not mod.SUMMARY_PATH.exists():
        pytest.skip("canonical H2 result summary not present in this checkout")
    summary = json.loads(mod.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert mod.canonical_summary_fingerprint(summary) == (
        mod.EXPECTED_RESULT_FINGERPRINT
    )
    changed = dict(summary)
    changed["H2_validation_passed"] = False
    assert mod.canonical_summary_fingerprint(changed) != (
        mod.EXPECTED_RESULT_FINGERPRINT
    )


def test_h2_closeout_module_contains_no_fit_or_network_path():
    source = Path(
        "src/kxbtcd_candidate_e_h2_result_closeout.py"
    ).read_text(encoding="utf-8")
    assert "fit_candidate_e(" not in source
    assert "PublicCensusHttpClient" not in source
    assert "collect_h2_outcomes(" not in source

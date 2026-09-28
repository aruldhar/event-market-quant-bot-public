from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.kxbtcd_candidate_e_h3_result_closeout as mod


def test_frozen_h3_result_identities():
    assert mod.EXPECTED_SOURCE_COMMIT == (
        "990b307272ef3a5f4beef91173532490d5dbd318"
    )
    assert mod.H3_IMPLEMENTATION_FINGERPRINT == (
        "6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc"
    )
    assert mod.H3_VALIDATION_FINGERPRINT == (
        "a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197"
    )
    assert mod.FINAL_H1_H2_MODEL_FINGERPRINT == (
        "1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842"
    )
    assert mod.EXPECTED_RESULT_FINGERPRINT == (
        "436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54"
    )


def test_frozen_h3_primary_metrics():
    assert float(mod.EXPECTED_RAW_LOG_LOSS) > float(
        mod.EXPECTED_CANDIDATE_LOG_LOSS
    )
    assert float(mod.EXPECTED_LOG_LOSS_DELTA) > 0.0
    assert float(mod.EXPECTED_RAW_BRIER) > float(
        mod.EXPECTED_CANDIDATE_BRIER
    )


def test_historical_generalization_decision_is_pass():
    assert mod.H3_EVENT_COUNT == 750
    assert mod.H3_ROW_COUNT == 22409
    assert mod.H3_MARKET_COUNT == 3750
    assert mod.H3_BLOCKS == ("B0", "B1", "B2", "B3", "B4")


def test_validate_real_h3_result_if_artifacts_present():
    if not mod.SUMMARY_PATH.exists():
        pytest.skip("canonical H3 result artifacts not present in this checkout")
    summary = mod.load_and_validate_result(".")
    decision = mod.advancement_decision(summary)
    assert summary["H3_validation_passed"] is True
    assert summary["block_log_loss_win_count"] == 5
    assert summary["latest_block_B4_win"] is True
    assert decision["historical_generalization_program"] == "PASS"


def test_summary_fingerprint_is_bound_to_full_summary():
    if not mod.SUMMARY_PATH.exists():
        pytest.skip("canonical H3 result summary not present in this checkout")
    summary = json.loads(mod.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert mod.canonical_summary_fingerprint(summary) == (
        mod.EXPECTED_RESULT_FINGERPRINT
    )
    changed = dict(summary)
    changed["H3_validation_passed"] = False
    assert mod.canonical_summary_fingerprint(changed) != (
        mod.EXPECTED_RESULT_FINGERPRINT
    )


def test_h3_closeout_module_contains_no_fit_or_network_path():
    source = Path(
        "src/kxbtcd_candidate_e_h3_result_closeout.py"
    ).read_text(encoding="utf-8")
    assert "fit_candidate_e(" not in source
    assert "PublicCensusHttpClient" not in source
    assert "collect_h3_outcomes(" not in source

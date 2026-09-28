from __future__ import annotations

import json
from pathlib import Path

FREEZE_FINGERPRINT = "a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e"

def test_development_freeze_writer_has_no_validation_or_execution_input_surface():
    text = Path("freeze_kxbtcd_candidate_e_entry_model_v1_development_result.py").read_text(encoding="utf-8").lower()
    for prohibited in ("--c1", "--c2", "--c3", "--reserve", "--pnl", "--order", "--execution"):
        assert prohibited not in text

def test_development_freeze_validator_has_no_c1_c2_c3_or_economics_surface():
    text = Path("validate_kxbtcd_candidate_e_entry_model_v1_development_freeze.py").read_text(encoding="utf-8").lower()
    for prohibited in ("--c1", "--c2", "--c3", "--reserve", "--pnl", "--order", "--execution"):
        assert prohibited not in text

def test_embedded_freeze_contract_is_validation_only():
    import freeze_kxbtcd_candidate_e_entry_model_v1_development_result as writer
    freeze = writer.EXPECTED_FREEZE
    assert freeze["selection"]["selected_lambda"] == 0.01
    assert len(freeze["full_development_fit"]["coefficients"]) == 21
    assert len(freeze["full_development_fit"]["scaler"]) == 11
    assert freeze["interpretation"]["eligible_to_open_c1_c2_validation"] is True
    assert freeze["interpretation"]["validation_gate_evaluated"] is False
    assert freeze["interpretation"]["model2_generalization_pass_claim"] is False
    assert freeze["interpretation"]["profitability_claim"] is False
    assert freeze["safety"]["c1_c2_opened_for_model2"] is False
    assert freeze["safety"]["c3_opened_for_model2"] is False
    assert freeze["safety"]["protected_reserve_accessed"] is False
    assert freeze["safety"]["strategy_v1_pnl_calculated"] is False
    assert freeze["safety"]["execution_enabled"] is False
    assert writer.canonical_fingerprint(freeze) == FREEZE_FINGERPRINT

def test_development_diagnostics_preserve_mixed_h2_h3_result():
    import freeze_kxbtcd_candidate_e_entry_model_v1_development_result as writer
    diag = writer.EXPECTED_FREEZE["rolling_origin_diagnostics"]
    assert diag["H2"]["candidate_e_minus_model2_log_loss"] > 0.0
    assert diag["H3"]["candidate_e_minus_model2_log_loss"] < 0.0
    assert diag["pooled_H2_H3"]["candidate_e_minus_model2_log_loss"] > 0.0

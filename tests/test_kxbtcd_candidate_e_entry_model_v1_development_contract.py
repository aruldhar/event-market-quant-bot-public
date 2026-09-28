from pathlib import Path


def test_development_cli_has_no_execution_or_economics_interface():
    text = Path("evaluate_kxbtcd_candidate_e_entry_model_v1_development.py").read_text(encoding="utf-8")
    assert "--c1" not in text.lower()
    assert "--c2" not in text.lower()
    assert "--c3" not in text.lower()
    assert "--reserve" not in text.lower()
    assert "--pnl" not in text.lower()
    assert "--order" not in text.lower()


def test_development_validator_recomputes_persisted_evaluation():
    text = Path("validate_kxbtcd_candidate_e_entry_model_v1_development.py").read_text(encoding="utf-8")
    assert "build_development_evaluation" in text
    assert "deterministic recomputation" in text

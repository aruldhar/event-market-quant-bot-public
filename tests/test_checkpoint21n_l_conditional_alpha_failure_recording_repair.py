import json,hashlib
from pathlib import Path
from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_development import ConditionalAlphaFitContractError
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"configs"/"kxbtcd_candidate_e_conditional_alpha_reliability_v1_failure_recording_repair.json"
EXPECTED='276fdf07803d083a67d94e6c5b923fcbf06392c4db4fb33cd1d9c1f3a954a865'
def canonical(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def test_repair_contract_fingerprint_and_no_science_change():
    d=json.loads(CFG.read_text())
    supplied=d.pop("repair_fingerprint")
    assert supplied==EXPECTED==canonical(d)
    assert d["authorized_change"]["optimizer_core_modified"] is False
    assert d["authorized_change"]["curvature_threshold_modified"] is False
    assert d["authorized_change"]["gradient_tolerance_modified"] is False
    assert d["authorized_change"]["fallback_or_skip_failed_fit_added"] is False
def test_failure_context_is_exact():
    e=ConditionalAlphaFitContractError(
        lambda_value=0.001,fold=2,fit_stages=("H1_OOF","H2"),score_stage="H3",
        original_type="ConditionalAlphaV1Error",
        original_message="BFGS positive-curvature requirement y^T s > 1e-12 failed",
    )
    assert e.as_dict()["lambda"]==0.001
    assert e.as_dict()["fold"]==2
    assert e.as_dict()["fit_stages"]==["H1_OOF","H2"]
    assert e.as_dict()["score_stage"]=="H3"
def test_cli_records_failure_without_rescue():
    text=(ROOT/"evaluate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_development.py").read_text()
    assert "build_optimizer_failure_evaluation" in text
    assert "build_failure_receipt" in text
    assert "selected_lambda=NOT_SELECTED" in text
    assert "full_development_fit_performed=false" in text

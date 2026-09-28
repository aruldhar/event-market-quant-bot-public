import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"configs"/"kxbtcd_candidate_e_conditional_alpha_reliability_v2_predeclaration.json"
def test_v2_predeclaration_fingerprint_and_optimizer():
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    x=dict(cfg); expected=x.pop("predeclaration_fingerprint")
    actual=hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    assert expected==actual=="6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8"
    assert cfg["candidate_id"]=="kxbtcd_candidate_e_conditional_alpha_reliability.v2"
    assert cfg["optimizer_v2"]["algorithm"]=="deterministic_full_batch_exact_hessian_damped_newton"
    assert cfg["optimizer_v2"]["gradient_l2_tolerance"]=="1e-8"
    assert cfg["optimizer_v2"]["fallback_optimizer"] is None
def test_v2_predeclaration_remains_non_scoring():
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    assert cfg["next_checkpoint"]["real_v2_fit_authorized_by_21N_M_A"] is False
    assert cfg["next_checkpoint"]["lambda_selection_authorized"] is False
    assert cfg["next_checkpoint"]["probability_gate_authorized"] is False
    assert cfg["next_checkpoint"]["economic_gate_authorized"] is False
    assert cfg["evidence_firewall"]["protected_reserve"]=="sealed"

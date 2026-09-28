import json, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"configs"/"kxbtcd_candidate_e_conditional_alpha_reliability_v1_development_implementation_freeze.json"
EXPECTED='02530cdd8ba58b45cde85c0ba40f681355ce5b14c4a3ad53ee5f1072fff156a8'
def canonical(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def test_implementation_freeze_contract():
    d=json.loads(CFG.read_text())
    supplied=d.pop("implementation_fingerprint")
    assert supplied==EXPECTED==canonical(d)
    assert d["development_contract"]["probability_gate_first"] is True
    assert d["development_contract"]["economic_gate_only_if_probability_passes"] is True
    assert d["development_contract"]["full_development_fit_only_if_probability_and_economic_gates_pass"] is True
    assert d["development_contract"]["lambda_grid"]==[0.001,0.01,0.1,1.0,10.0]
def test_implementation_checkpoint_safety_flags_all_false():
    d=json.loads(CFG.read_text())
    assert all(v is False for v in d["safety"].values())

"""Validate the frozen Checkpoint 21N-K implementation package."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CFG=ROOT/"configs"/"kxbtcd_candidate_e_conditional_alpha_reliability_v1_development_implementation_freeze.json"
EXPECTED='02530cdd8ba58b45cde85c0ba40f681355ce5b14c4a3ad53ee5f1072fff156a8'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def canonical(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def fail(m): raise SystemExit(m)

def main():
    d=json.loads(CFG.read_text(encoding="utf-8"))
    if d.get("checkpoint_id")!="21N-K": fail("checkpoint mismatch")
    if d.get("candidate_id")!="kxbtcd_candidate_e_conditional_alpha_reliability.v1": fail("candidate mismatch")
    copy=dict(d); supplied=copy.pop("implementation_fingerprint",None)
    if supplied!=EXPECTED or canonical(copy)!=supplied: fail("implementation fingerprint mismatch")
    if d["parent_21N_J_B"]["preparation_fingerprint"]!="a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46":
        fail("J-B preparation binding changed")
    if d["development_contract"]["lambda_grid"]!=[0.001,0.01,0.1,1.0,10.0]:
        fail("lambda grid changed")
    if d["development_contract"]["probability_gate_first"] is not True:
        fail("sequential probability gate not frozen")
    if d["development_contract"]["full_development_fit_only_if_probability_and_economic_gates_pass"] is not True:
        fail("full-fit gate changed")
    for rel, expected in d["implementation_sha256s"].items():
        if sha(ROOT/rel)!=expected: fail(f"implementation SHA mismatch: {rel}")
    if any(v is not False for v in d["safety"].values()):
        fail("21N-K safety flags must all remain false")
    print("Checkpoint 21N-K conditional-alpha development implementation validation: PASS")
    print(f"implementation_fingerprint={supplied}")
    print(f"predeclaration_fingerprint={d['parent_predeclaration_fingerprint']}")
    print(f"preparation_fingerprint={d['parent_21N_J_B']['preparation_fingerprint']}")
    print("real_project_outcomes_read_in_21N_K=false")
    print("real_gamma_fit_performed_in_21N_K=false")
    print("real_lambda_selected_in_21N_K=false")
    print("real_probability_gate_scored_in_21N_K=false")
    print("real_conditional_alpha_pnl_calculated_in_21N_K=false")
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_authorized=false")
    return 0
if __name__=="__main__": raise SystemExit(main())

import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT/"configs"/"kxbtcd_candidate_e_conditional_alpha_reliability_v1_preparation_closeout.json"
EXPECTED = 'f1b0caed9d83d8657bd916422b17dde4e239cbc41a5de880ed78a51217cdffb1'

def canonical(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def test_frozen_closeout_contract():
    d=json.loads(CFG.read_text())
    assert d["checkpoint_id"]=="21N-J-B"
    assert d["status"]=="OUTCOME_BLIND_PREPARATION_ACCEPTED"
    assert d["materialization_result"]["feature_rows"]==76419
    assert d["materialization_result"]["development_events"]==2570
    assert d["materialization_result"]["independent_rematerialization_validation"]=="PASS"
    assert d["materialization_result"]["feature_rows_fingerprint"]=="590ab13567821839fb0d404ed4813d328fc4e68ee1a61fd39038d3f8624a42fe"
    assert d["materialization_result"]["prepared_output_sha256"]=="268c756f82f6be2b53f5fee1f212ad0ecd1d02459547861cc5c3b3623357472f"
    assert d["materialization_result"]["preparation_fingerprint"]=="a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46"
    supplied=d.pop("preparation_closeout_fingerprint")
    assert supplied==EXPECTED==canonical(d)

def test_safety_firewall_remains_closed():
    d=json.loads(CFG.read_text())
    assert all(value is False for value in d["safety"].values())
    assert d["next_checkpoint"]["outcome_access_authorized_by_21N_J_B"] is False
    assert d["next_checkpoint"]["real_gamma_fit_authorized_by_21N_J_B"] is False

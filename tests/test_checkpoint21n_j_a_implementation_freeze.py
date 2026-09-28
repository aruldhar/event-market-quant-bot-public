from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_implementation_freeze.json"


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def test_implementation_freeze_fingerprint_and_file_hashes_are_self_consistent():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    supplied = doc["implementation_fingerprint"]
    copy = dict(doc)
    copy.pop("implementation_fingerprint")
    assert canonical_sha256(copy) == supplied
    for relative, expected in doc["implementation_sha256s"].items():
        assert sha256_file(ROOT / relative) == expected


def test_implementation_freeze_keeps_real_evidence_and_execution_closed():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    scope = doc["implementation_scope"]
    assert scope["real_data_fit_cli_present"] is False
    assert scope["real_outcome_scoring_cli_present"] is False
    assert scope["real_pnl_evaluator_present"] is False
    assert doc["phase_sequence"]["21N_J_B"].startswith("after J-A closeout")
    assert doc["materialization_contract"]["requires_safe_21N_J_A_closeout_receipt"] is True
    assert all(value is False for value in doc["safety"].values())


def test_future_materialization_cli_is_outcome_blind_and_requires_j_a_receipt():
    text = (ROOT / "prepare_kxbtcd_candidate_e_conditional_alpha_reliability_v1.py").read_text(encoding="utf-8")
    assert "--j-a-closeout-receipt" in text
    for prohibited in ("--outcome", "--label", "--labels", "--pnl", "--order"):
        assert prohibited not in text.lower()

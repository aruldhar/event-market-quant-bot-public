"""21N-Y-A2 memory/storage repair freeze; parent experiments stay frozen."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from .kxbtcd_candidate_e_v2_execution_quantity_transport_amendment_freeze import validate_amendment
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import validate_parents

PATH = Path("configs/kxbtcd_candidate_e_v2_memory_amendment.json")
EXPECTED_FINGERPRINT = "f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03"


def fingerprint(payload):
    body = dict(payload)
    body.pop("amendment_fingerprint", None)
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def text_hash(raw):
    # The repository deliberately checks .ps1 out as CRLF. Git stores LF.
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def validate_policy_body(repo):
    def function(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "simulate_policy")
        return ast.dump(node, include_attributes=False)
    original = repo / "src/kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator.py"
    adapted = repo / "src/kxbtcd_candidate_e_v2_disk_policy.py"
    if function(original) != function(adapted):
        raise ValueError("disk runner policy body differs from frozen Y-A")


def validate_memory_amendment(repo_root="."):
    repo = Path(repo_root)
    parent = validate_amendment(repo)
    validate_parents(repo)
    payload = json.loads((repo / PATH).read_text(encoding="utf-8"))
    if payload.get("amendment_fingerprint") != EXPECTED_FINGERPRINT or fingerprint(payload) != EXPECTED_FINGERPRINT:
        raise ValueError("memory amendment fingerprint mismatch")
    if payload.get("parent_quantity_amendment") != parent["amendment_fingerprint"]:
        raise ValueError("quantity amendment binding mismatch")
    validator_text = Path(__file__).read_text(encoding="utf-8").replace(EXPECTED_FINGERPRINT, "<fingerprint>")
    if hashlib.sha256(validator_text.encode()).hexdigest() != payload["validator_template_sha256"]:
        raise ValueError("memory amendment validator source changed")
    for key in ("frozen_files", "parent_source_hashes"):
        for relative, expected in payload[key].items():
            path = repo / relative
            observed = (text_hash(path.read_bytes()) if key == "frozen_files" else
                        hashlib.sha256(path.read_bytes()).hexdigest()) if path.is_file() else None
            if observed != expected:
                raise ValueError("amendment/source file mismatch: " + relative)
    validate_policy_body(repo)
    return payload

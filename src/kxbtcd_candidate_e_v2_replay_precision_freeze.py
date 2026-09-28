"""21N-Y-A3 additive replay precision freeze."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .kxbtcd_candidate_e_v2_memory_amendment_freeze import validate_memory_amendment, text_hash, fingerprint

PATH = Path("configs/kxbtcd_candidate_e_v2_replay_precision_amendment.json")
EXPECTED_FINGERPRINT = "82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370"


def validate_precision_amendment(repo_root="."):
    repo = Path(repo_root)
    parent = validate_memory_amendment(repo)
    payload = json.loads((repo / PATH).read_text(encoding="utf-8"))
    if payload.get("amendment_fingerprint") != EXPECTED_FINGERPRINT or fingerprint(payload) != EXPECTED_FINGERPRINT:
        raise ValueError("replay precision amendment fingerprint mismatch")
    if payload.get("parent_memory_amendment") != parent["amendment_fingerprint"]:
        raise ValueError("memory amendment binding mismatch")
    source = (repo / "src/kxbtcd_candidate_e_v2_replay_precision_freeze.py").read_text(encoding="utf-8")
    if hashlib.sha256(source.replace(EXPECTED_FINGERPRINT, "<fingerprint>").encode()).hexdigest() != payload["validator_template_sha256"]:
        raise ValueError("precision freeze validator changed")
    for relative, expected in payload["frozen_files"].items():
        path = repo / relative
        if not path.is_file() or text_hash(path.read_bytes()) != expected:
            raise ValueError("precision amendment file changed: " + relative)
    return payload

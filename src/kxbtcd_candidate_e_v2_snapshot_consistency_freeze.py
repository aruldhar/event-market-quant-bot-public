"""Additive Y-A4 freeze; validates unchanged Y-A3 and its frozen ancestors."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .kxbtcd_candidate_e_v2_memory_amendment_freeze import fingerprint, text_hash
from .kxbtcd_candidate_e_v2_replay_precision_freeze import validate_precision_amendment
from .kxbtcd_candidate_e_v2_snapshot_consistency import RULES

PATH = Path('configs/kxbtcd_candidate_e_v2_snapshot_consistency_amendment.json')
EXPECTED_FINGERPRINT = '31df5185c3840092eaae09f82fd0139cf46db37dc5bfd9bd067d6dcfa758c92a'


def validate_snapshot_consistency_amendment(repo_root='.'):
    repo = Path(repo_root)
    parent = validate_precision_amendment(repo)
    payload = json.loads((repo / PATH).read_text(encoding='utf-8'))
    if payload.get('amendment_fingerprint') != EXPECTED_FINGERPRINT or fingerprint(payload) != EXPECTED_FINGERPRINT:
        raise ValueError('snapshot consistency amendment fingerprint mismatch')
    if payload.get('parent_replay_precision_amendment') != parent['amendment_fingerprint'] or payload.get('rules') != RULES:
        raise ValueError('snapshot consistency parent or rule binding mismatch')
    validator = (repo / 'src/kxbtcd_candidate_e_v2_snapshot_consistency_freeze.py').read_text(encoding='utf-8')
    if hashlib.sha256(validator.replace(EXPECTED_FINGERPRINT, '<fingerprint>').encode()).hexdigest() != payload['validator_template_sha256']:
        raise ValueError('snapshot consistency validator changed')
    for relative, expected in payload['frozen_files'].items():
        path = repo / relative
        if not path.is_file() or text_hash(path.read_bytes()) != expected:
            raise ValueError('snapshot consistency frozen file changed: ' + relative)
    return payload

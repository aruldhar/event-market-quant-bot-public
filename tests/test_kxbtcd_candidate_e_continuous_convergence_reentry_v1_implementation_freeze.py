from __future__ import annotations

import json
from pathlib import Path

from src.kxbtcd_candidate_e_continuous_convergence_reentry_v1_simulator_freeze import (
    DEFAULT_FREEZE_PATH,
    EXPECTED_IMPLEMENTATION_FINGERPRINT,
    canonical_fingerprint,
    validate_freeze,
)
from src.kxbtcd_candidate_e_continuous_convergence_reentry_v1_simulator import (
    validate_parents,
)


def test_freeze_fingerprint():
    payload = json.loads(Path(DEFAULT_FREEZE_PATH).read_text(encoding="utf-8"))
    expected = "cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f"
    assert EXPECTED_IMPLEMENTATION_FINGERPRINT == expected
    assert payload["implementation_fingerprint"] == expected
    assert canonical_fingerprint(payload) == expected
    assert payload["source_binding_required_before_path_run"] is True
    assert payload["continuous_real_july10_paths_run_before_freeze"] is False


def test_implementation_validator_is_receipt_lifecycle_independent():
    freeze = validate_freeze(".")
    parents = validate_parents(".")
    assert freeze["implementation_fingerprint"] == EXPECTED_IMPLEMENTATION_FINGERPRINT
    assert (
        parents["continuous_strategy_predeclaration_fingerprint"]
        == "4c81dd092009cb7d6f32f4d9a8c66254b5bbcdee652c46379536993390994dda"
    )

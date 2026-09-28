import json
import subprocess
import sys
from pathlib import Path

EXPECTED = "2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e"

def test_predeclaration_validator_passes():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, str(root / "validate_kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_predeclaration.py")],
        cwd=root, capture_output=True, text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "validation: PASS" in p.stdout

def test_predeclaration_keeps_candidate_e_as_valuation():
    root = Path(__file__).resolve().parents[1]
    doc = json.loads((root / "configs/kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1_predeclaration.json").read_text())
    assert doc["predeclaration_fingerprint"] == EXPECTED
    assert doc["valuation_policy"]["conditional_adjusted_probability_used_for_valuation"] is False
    assert doc["valuation_policy"]["conditional_alpha_role"] == "ranking/filter diagnostic only"
    assert doc["alpha_ranking_policy"]["fixed_alpha_threshold_search"] is False
    assert doc["evidence_scope"]["C3_allowed"] is False

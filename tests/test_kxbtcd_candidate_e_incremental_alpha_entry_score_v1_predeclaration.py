import json
from pathlib import Path

EXPECTED = "bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa"

def test_incremental_alpha_predeclaration_contract():
    root = Path(__file__).resolve().parents[1]
    doc = json.loads((root / "configs" / "kxbtcd_candidate_e_incremental_alpha_entry_score_v1_predeclaration.json").read_text())
    assert doc["predeclaration_fingerprint"] == EXPECTED
    assert doc["beta_tuning"]["grid"][0] == 0.0
    assert doc["beta_tuning"]["negative_beta_allowed"] is False
    assert doc["selection_policy"]["selected_count_expected"] == 128
    assert doc["selection_policy"]["coverage_search_allowed"] is False
    assert doc["incremental_alpha_gate"]["status_if_all_true"] == "INCREMENTAL_ALPHA_SIGNAL"

from pathlib import Path
import importlib.util


def load_module():
    path = Path(__file__).parents[1] / "validate_kxbtcd_candidate_e_quoted_entry_hold_v1_development_result.py"
    spec = importlib.util.spec_from_file_location("validate21nc", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_expected_fingerprint_is_frozen():
    mod = load_module()
    assert mod.EXPECTED_EVAL == "8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc"


def test_result_file_contract_is_complete():
    mod = load_module()
    assert set(mod.FILES) == {"evaluation", "event_pnl_scenarios", "threshold_scores", "receipt"}


def test_no_selected_threshold_accepts_both_canonical_representations():
    mod = load_module()
    assert mod.no_selected_threshold(None) is True
    assert mod.no_selected_threshold("") is True
    assert mod.no_selected_threshold("0.03") is False

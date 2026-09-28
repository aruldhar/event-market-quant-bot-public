import pytest

from src.kxbtcd_candidate_e_read_only_soak_acceptance import (
    ReadOnlySoakAcceptanceError,
    accept_terminal_read_only_soak,
)


def evidence(**overrides):
    summary = {
        "run_id": "soak-24h", "measurement_complete": True,
        "safety_invariant_status": "PASS", "execution_mode": "disabled",
        "readiness_input_contract": "v2_exact_rest_candle_and_kalshi",
        "orders": 0, "signals": 0, "production_writes": 0,
    }
    manifest = {
        "run_id": "soak-24h", "measurement_complete": True,
        "lifecycle_state": "TERMINAL", "operational_classification": "MEASUREMENT_COMPLETE",
        "safety_invariant_status": "PASS",
    }
    summary.update(overrides.pop("summary", {}))
    manifest.update(overrides.pop("manifest", {}))
    return summary, manifest


def test_accepts_consistent_terminal_non_trading_soak():
    summary, manifest = evidence()
    assert accept_terminal_read_only_soak(summary=summary, manifest=manifest).run_id == "soak-24h"


@pytest.mark.parametrize("changes", [
    {"summary": {"measurement_complete": False}},
    {"manifest": {"lifecycle_state": "RUNNING"}},
    {"summary": {"orders": 1}},
    {"summary": {"readiness_input_contract": "legacy_coinbase_ws_and_kalshi"}},
])
def test_rejects_incomplete_nonterminal_or_trading_soak(changes):
    summary, manifest = evidence(**changes)
    with pytest.raises(ReadOnlySoakAcceptanceError):
        accept_terminal_read_only_soak(summary=summary, manifest=manifest)

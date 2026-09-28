import pytest

from src.kxbtcd_candidate_e_controlled_restart_proof import (
    ControlledRestartProofError,
    validate_controlled_restart_proof,
)


def payload(**overrides):
    return {
        "accepted_soak_run_id": "accepted_24h",
        "restart_run_id": "restart_1",
        "restart_evidence_id": "restart_receipt_1",
        "fresh_clock_evidence": True,
        "fresh_coinbase_completed_candle": True,
        "fresh_kalshi_discovery": True,
        "fresh_kalshi_snapshot": True,
        "reached_ready_read_only": True,
        "orders": 0, "signals": 0, "production_writes": 0,
        **overrides,
    }


def test_controlled_restart_requires_fresh_read_only_recovery():
    receipt = validate_controlled_restart_proof(payload())
    assert receipt.restart_run_id == "restart_1"


@pytest.mark.parametrize("overrides, message", [
    ({"restart_run_id": "accepted_24h"}, "new run"),
    ({"fresh_kalshi_snapshot": False}, "fresh"),
    ({"orders": 1}, "prohibited"),
])
def test_controlled_restart_fails_closed_on_stale_or_trading_evidence(overrides, message):
    with pytest.raises(ControlledRestartProofError, match=message):
        validate_controlled_restart_proof(payload(**overrides))

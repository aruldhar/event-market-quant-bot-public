import pytest

from src.kxbtcd_candidate_e_controlled_restart_proof import validate_controlled_restart_proof
from src.kxbtcd_candidate_e_micro_probe_launch_plan import (
    MicroProbeLaunchPlanError,
    bind_micro_probe_launch_plan,
)
from src.kxbtcd_candidate_e_micro_probe_market_terms import validate_micro_probe_market_terms
from src.kxbtcd_candidate_e_micro_probe_readiness import validate_micro_probe_readiness


def terms(ticker="KXBTCD-EXAMPLE-T100000"):
    return validate_micro_probe_market_terms({
        "market_ticker": ticker, "observed_utc": "2026-09-08T00:00:00Z",
        "market_response_sha256": "a" * 64, "fractional_trading_enabled": True,
        "quantity_increment_contracts": "0.01", "price_grid_evidence_id": "grid",
        "fee_schedule_id": "fees", "fee_schedule_response_sha256": "b" * 64,
        "fee_schedule_effective_utc": "2026-09-08T00:00:00Z",
    })


def restart(soak="soak", evidence="restart-evidence"):
    return validate_controlled_restart_proof({
        "accepted_soak_run_id": soak, "restart_run_id": "restart", "restart_evidence_id": evidence,
        "fresh_clock_evidence": True, "fresh_coinbase_completed_candle": True,
        "fresh_kalshi_discovery": True, "fresh_kalshi_snapshot": True,
        "reached_ready_read_only": True, "orders": 0, "signals": 0, "production_writes": 0,
    })


def readiness(ticker="KXBTCD-EXAMPLE-T100000", soak="soak", evidence="restart-evidence"):
    return validate_micro_probe_readiness({
        "preflight": {"market_ticker": ticker, "quantity_contracts": "0.01",
            "quantity_increment_contracts": "0.01", "maximum_entry_attempts": 1,
            "maximum_orders": 1, "maximum_cash_loss": "1", "fee_schedule_id": "fees",
            "kill_switch_id": "kill", "audit_run_id": "audit"},
        "accepted_read_only_soak": True, "accepted_controlled_restart": True,
        "accepted_soak_run_id": soak, "accepted_restart_evidence_id": evidence,
        "explicit_user_run_approval_id": "approval",
    })


def test_launch_plan_binds_matching_evidence():
    plan = bind_micro_probe_launch_plan(terms=terms(), restart=restart(), readiness=readiness())
    assert plan.market_ticker == "KXBTCD-EXAMPLE-T100000"


@pytest.mark.parametrize("term_ticker, restart_soak, readiness_soak, evidence", [
    ("OTHER", "soak", "soak", "restart-evidence"),
    ("KXBTCD-EXAMPLE-T100000", "other-soak", "soak", "restart-evidence"),
    ("KXBTCD-EXAMPLE-T100000", "soak", "soak", "other-evidence"),
])
def test_launch_plan_rejects_mixed_evidence(term_ticker, restart_soak, readiness_soak, evidence):
    with pytest.raises(MicroProbeLaunchPlanError):
        bind_micro_probe_launch_plan(
            terms=terms(term_ticker), restart=restart(restart_soak),
            readiness=readiness(soak=readiness_soak, evidence=evidence),
        )

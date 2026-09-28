from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_micro_probe_preflight import (
    MicroProbePreflightError,
    validate_micro_probe_preflight,
)


def payload(**overrides):
    return {
        "market_ticker": "KXBTCD-EXAMPLE-T100000", "quantity_contracts": "0.01",
        "quantity_increment_contracts": "0.01", "maximum_entry_attempts": 5,
        "maximum_orders": 8, "maximum_cash_loss": "1.00",
        "fee_schedule_id": "verified_fee_schedule", "kill_switch_id": "manual_kill",
        "audit_run_id": "micro_probe_1", **overrides,
    }


def test_preflight_requires_exact_micro_quantity_and_explicit_controls():
    receipt = validate_micro_probe_preflight(payload())
    assert receipt.quantity_contracts == Decimal("0.01")
    assert receipt.maximum_entry_attempts == 5


def test_preflight_fails_closed_on_unproven_increment_or_missing_cap():
    with pytest.raises(MicroProbePreflightError, match="increment"):
        validate_micro_probe_preflight(payload(quantity_increment_contracts="0.02"))
    with pytest.raises(MicroProbePreflightError, match="missing"):
        validate_micro_probe_preflight({})

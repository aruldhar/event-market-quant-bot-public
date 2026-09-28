from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_micro_probe_reconciliation import (
    MicroProbeReconciliationError,
    reconcile_micro_probe,
)


def payload(**overrides):
    return {
        "audit_run_id": "probe-1", "entry_order_id": "entry-1", "exit_order_id": "exit-1",
        "entry_filled_contracts": "0.01", "exit_filled_contracts": "0.01",
        "venue_entry_fee": "0.0001", "expected_entry_fee": "0.0001",
        "venue_exit_fee": "0.0001", "expected_exit_fee": "0.0001",
        "final_position_contracts": "0", **overrides,
    }


def test_reconciliation_accepts_authoritative_flat_micro_probe():
    receipt = reconcile_micro_probe(payload())
    assert receipt.exit_filled_contracts == Decimal("0.01")


@pytest.mark.parametrize("overrides, message", [
    ({"entry_filled_contracts": "0.02"}, "exact micro"),
    ({"venue_exit_fee": "0.0002"}, "fee differs"),
    ({"final_position_contracts": "0.01"}, "flat"),
])
def test_reconciliation_rejects_unreconciled_fills_fees_or_position(overrides, message):
    with pytest.raises(MicroProbeReconciliationError, match=message):
        reconcile_micro_probe(payload(**overrides))

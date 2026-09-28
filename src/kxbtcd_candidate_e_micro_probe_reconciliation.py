"""Offline reconciliation gate for a future explicitly authorized micro probe."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


class MicroProbeReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class MicroProbeReconciliationReceipt:
    audit_run_id: str
    entry_order_id: str
    exit_order_id: str
    entry_filled_contracts: Decimal
    exit_filled_contracts: Decimal
    venue_entry_fee: Decimal
    venue_exit_fee: Decimal


def _text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise MicroProbeReconciliationError("reconciliation identity field is blank")
    return value


def _decimal(payload: Mapping[str, object], key: str) -> Decimal:
    try:
        value = Decimal(str(payload[key]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise MicroProbeReconciliationError("reconciliation numeric field is invalid") from exc
    if not value.is_finite() or value < 0:
        raise MicroProbeReconciliationError("reconciliation amount must be finite and nonnegative")
    return value


def reconcile_micro_probe(payload: Mapping[str, object]) -> MicroProbeReconciliationReceipt:
    """Require venue facts to close the tiny probe flat; no venue capability exists here."""
    required = (
        "audit_run_id", "entry_order_id", "exit_order_id", "entry_filled_contracts",
        "exit_filled_contracts", "venue_entry_fee", "expected_entry_fee",
        "venue_exit_fee", "expected_exit_fee", "final_position_contracts",
    )
    if any(key not in payload for key in required):
        raise MicroProbeReconciliationError("missing required reconciliation facts")
    entry = _decimal(payload, "entry_filled_contracts")
    exit_ = _decimal(payload, "exit_filled_contracts")
    if entry <= 0 or entry > Decimal("0.01") or exit_ != entry:
        raise MicroProbeReconciliationError("venue fills do not reconcile the exact micro position")
    entry_fee = _decimal(payload, "venue_entry_fee")
    exit_fee = _decimal(payload, "venue_exit_fee")
    if entry_fee != _decimal(payload, "expected_entry_fee") or exit_fee != _decimal(payload, "expected_exit_fee"):
        raise MicroProbeReconciliationError("venue-reported fee differs from verified expected fee")
    if _decimal(payload, "final_position_contracts") != 0:
        raise MicroProbeReconciliationError("micro probe did not reconcile flat")
    return MicroProbeReconciliationReceipt(
        audit_run_id=_text(payload, "audit_run_id"), entry_order_id=_text(payload, "entry_order_id"),
        exit_order_id=_text(payload, "exit_order_id"), entry_filled_contracts=entry,
        exit_filled_contracts=exit_, venue_entry_fee=entry_fee, venue_exit_fee=exit_fee,
    )

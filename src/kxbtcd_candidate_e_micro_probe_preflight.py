"""Fail-closed offline preflight for a future explicitly authorized micro probe."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


class MicroProbePreflightError(ValueError):
    pass


@dataclass(frozen=True)
class MicroProbePreflightReceipt:
    market_ticker: str
    quantity_contracts: Decimal
    quantity_increment_contracts: Decimal
    maximum_entry_attempts: int
    maximum_orders: int
    maximum_cash_loss: Decimal
    fee_schedule_id: str
    kill_switch_id: str
    audit_run_id: str


def validate_micro_probe_preflight(payload: Mapping[str, object]) -> MicroProbePreflightReceipt:
    """Validate explicit future-probe facts without creating an order path."""
    required = (
        "market_ticker", "quantity_contracts", "quantity_increment_contracts",
        "maximum_entry_attempts", "maximum_orders", "maximum_cash_loss",
        "fee_schedule_id", "kill_switch_id", "audit_run_id",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise MicroProbePreflightError("missing required preflight fields")
    try:
        quantity = Decimal(str(payload["quantity_contracts"]))
        increment = Decimal(str(payload["quantity_increment_contracts"]))
        loss = Decimal(str(payload["maximum_cash_loss"]))
    except Exception as exc:
        raise MicroProbePreflightError("preflight numeric field is invalid") from exc
    if quantity != Decimal("0.01"):
        raise MicroProbePreflightError("future first probe quantity must be exactly 0.01 contracts")
    if not increment.is_finite() or increment <= 0 or quantity % increment != 0:
        raise MicroProbePreflightError("market does not prove the 0.01 quantity increment")
    attempts = payload["maximum_entry_attempts"]
    orders = payload["maximum_orders"]
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1 or attempts > 5:
        raise MicroProbePreflightError("entry attempt cap must be between one and five")
    if isinstance(orders, bool) or not isinstance(orders, int) or orders < attempts:
        raise MicroProbePreflightError("order cap must cover entry attempts")
    if not loss.is_finite() or loss <= 0:
        raise MicroProbePreflightError("cash-loss cap must be positive finite")
    text = {key: str(payload[key]).strip() for key in ("market_ticker", "fee_schedule_id", "kill_switch_id", "audit_run_id")}
    if not all(text.values()):
        raise MicroProbePreflightError("preflight identity field is blank")
    return MicroProbePreflightReceipt(
        market_ticker=text["market_ticker"], quantity_contracts=quantity,
        quantity_increment_contracts=increment, maximum_entry_attempts=attempts,
        maximum_orders=orders, maximum_cash_loss=loss,
        fee_schedule_id=text["fee_schedule_id"], kill_switch_id=text["kill_switch_id"],
        audit_run_id=text["audit_run_id"],
    )

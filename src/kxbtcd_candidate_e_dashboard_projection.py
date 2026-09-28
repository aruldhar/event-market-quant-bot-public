"""Pure read-only projection of future confirmed trading-ledger events.

The future execution worker is responsible for durable writes and venue
reconciliation.  This module only consumes an already-normalized event stream;
it cannot submit, cancel, amend, or reconcile venue orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping


class DashboardProjectionError(ValueError):
    pass


EVENT_SCHEMA_VERSION = "kxbtcd_candidate_e_dashboard_event.v1"


@dataclass(frozen=True)
class DashboardTradeRow:
    run_id: str
    position_id: str
    market_ticker: str
    entry_filled_quantity: Decimal
    exit_filled_quantity: Decimal
    net_position_quantity: Decimal
    net_confirmed_cash_flow: Decimal
    realized_net_pnl: Decimal | None
    reconciled_flat: bool
    fill_count: int


@dataclass(frozen=True)
class DashboardProjection:
    trades: tuple[DashboardTradeRow, ...]
    total_realized_net_pnl: Decimal
    closed_trade_count: int
    open_position_count: int


def _text(event: Mapping[str, object], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DashboardProjectionError(f"{field} is required")
    return value


def _decimal(event: Mapping[str, object], field: str, *, nonnegative: bool = True) -> Decimal:
    try:
        value = Decimal(str(event[field]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise DashboardProjectionError(f"{field} must be decimal") from exc
    if not value.is_finite() or (nonnegative and value < 0):
        raise DashboardProjectionError(f"{field} must be finite and nonnegative")
    return value


def _event_identity(event: Mapping[str, object], previous: tuple[str, int] | None) -> tuple[str, int]:
    if event.get("schema_version") != EVENT_SCHEMA_VERSION:
        raise DashboardProjectionError("unexpected dashboard event schema")
    run_id = _text(event, "run_id")
    sequence = event.get("event_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise DashboardProjectionError("event_sequence must be a positive integer")
    if previous is not None and (run_id < previous[0] or (run_id == previous[0] and sequence <= previous[1])):
        raise DashboardProjectionError("ledger events are not in strict run sequence")
    return run_id, sequence


def project_confirmed_ledger_events(events: Iterable[Mapping[str, object]]) -> DashboardProjection:
    """Project confirmed fills after explicit flat-position reconciliation.

    `realized_net_pnl` is intentionally absent until the position is confirmed
    flat.  The value is the signed cash flow of confirmed buy/sell fills after
    confirmed fees; it never includes a mark, model estimate, or assumed fill.
    """
    positions: dict[tuple[str, str], dict[str, object]] = {}
    previous: tuple[str, int] | None = None
    for raw in events:
        if not isinstance(raw, Mapping):
            raise DashboardProjectionError("ledger event must be an object")
        event = raw
        run_id, sequence = _event_identity(event, previous)
        previous = run_id, sequence
        event_type = _text(event, "event_type")
        if event_type == "confirmed_fill":
            position_id = _text(event, "position_id")
            market_ticker = _text(event, "market_ticker")
            side = _text(event, "side")
            if side not in {"buy", "sell"}:
                raise DashboardProjectionError("confirmed fill side is invalid")
            quantity = _decimal(event, "filled_quantity")
            price = _decimal(event, "fill_price")
            fee = _decimal(event, "venue_fee")
            if quantity <= 0:
                raise DashboardProjectionError("confirmed fill quantity must be positive")
            key = run_id, position_id
            state = positions.setdefault(key, {
                "market_ticker": market_ticker, "quantity": Decimal("0"),
                "entry_quantity": Decimal("0"), "exit_quantity": Decimal("0"),
                "cash_flow": Decimal("0"), "fill_count": 0, "reconciled_flat": False,
            })
            if state["market_ticker"] != market_ticker or state["reconciled_flat"]:
                raise DashboardProjectionError("confirmed fill conflicts with position state")
            signed_quantity = quantity if side == "buy" else -quantity
            signed_cash_flow = -(price * quantity + fee) if side == "buy" else price * quantity - fee
            state["quantity"] += signed_quantity
            if side == "buy":
                state["entry_quantity"] += quantity
            else:
                state["exit_quantity"] += quantity
            state["cash_flow"] += signed_cash_flow
            state["fill_count"] += 1
        elif event_type == "position_reconciled":
            position_id = _text(event, "position_id")
            key = run_id, position_id
            state = positions.get(key)
            if state is None:
                raise DashboardProjectionError("reconciliation has no confirmed fills")
            if event.get("venue_state_confirmed") is not True:
                raise DashboardProjectionError("position reconciliation is not authoritative")
            reported_quantity = _decimal(event, "position_quantity")
            if reported_quantity != 0 or state["quantity"] != 0:
                raise DashboardProjectionError("position is not confirmed flat")
            state["reconciled_flat"] = True
        elif event_type in {"decision_recorded", "order_status", "runtime_metric"}:
            # These events may provide drilldown context, but cannot alter cash
            # accounting or turn an estimated state into realized P&L.
            continue
        else:
            raise DashboardProjectionError("unknown dashboard ledger event")
    rows = tuple(sorted((DashboardTradeRow(
        run_id=run_id, position_id=position_id,
        market_ticker=state["market_ticker"], entry_filled_quantity=state["entry_quantity"],
        exit_filled_quantity=state["exit_quantity"], net_position_quantity=state["quantity"],
        net_confirmed_cash_flow=state["cash_flow"],
        realized_net_pnl=state["cash_flow"] if state["reconciled_flat"] else None,
        reconciled_flat=state["reconciled_flat"], fill_count=state["fill_count"],
    ) for (run_id, position_id), state in positions.items()), key=lambda row: (row.run_id, row.position_id)))
    realized = sum((row.realized_net_pnl for row in rows if row.realized_net_pnl is not None), Decimal("0"))
    return DashboardProjection(
        trades=rows, total_realized_net_pnl=realized,
        closed_trade_count=sum(row.reconciled_flat for row in rows),
        open_position_count=sum(not row.reconciled_flat for row in rows),
    )

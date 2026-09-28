"""Read-only projection for the live-shadow dashboard simulation ledger.

This is deliberately distinct from ``dashboard_projection``.  That module
projects confirmed venue facts and may report realized P&L.  This module only
projects a model decision and a hypothetical immediate book-walk result from
read-only market evidence.  It has no venue client, credentials, order path,
or claim that the displayed liquidity would have filled at a venue.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping


class DashboardShadowProjectionError(ValueError):
    pass


SHADOW_EVENT_SCHEMA_VERSION = "kxbtcd_candidate_e_dashboard_shadow_event.v1"
EXACT_OBSERVED_DEPTH_IOC = "EXACT_OBSERVED_DEPTH_IOC"
OFFICIAL_FINAL_SETTLEMENT_BASIS = "OFFICIAL_FINAL_MARKET_RESULT"


@dataclass(frozen=True)
class DashboardShadowTradeRow:
    run_id: str
    position_id: str
    market_ticker: str
    entry_simulated_quantity: Decimal
    exit_simulated_quantity: Decimal
    net_simulated_position_quantity: Decimal
    net_simulated_cash_flow: Decimal
    simulated_net_pnl: Decimal | None
    simulated_flat: bool
    simulation_fill_count: int
    fill_assumption: str


@dataclass(frozen=True)
class DashboardShadowProjection:
    trades: tuple[DashboardShadowTradeRow, ...]
    total_simulated_net_pnl: Decimal
    simulated_closed_trade_count: int
    simulated_open_position_count: int


def _text(event: Mapping[str, object], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DashboardShadowProjectionError(f"{field} is required")
    return value


def _decimal(event: Mapping[str, object], field: str) -> Decimal:
    try:
        value = Decimal(str(event[field]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise DashboardShadowProjectionError(f"{field} must be decimal") from exc
    if not value.is_finite() or value < 0:
        raise DashboardShadowProjectionError(f"{field} must be finite and nonnegative")
    return value


def _event_identity(event: Mapping[str, object], previous: tuple[str, int] | None) -> tuple[str, int]:
    if event.get("schema_version") != SHADOW_EVENT_SCHEMA_VERSION:
        raise DashboardShadowProjectionError("unexpected shadow dashboard event schema")
    run_id = _text(event, "run_id")
    sequence = event.get("event_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise DashboardShadowProjectionError("event_sequence must be a positive integer")
    if previous is not None and (run_id < previous[0] or (run_id == previous[0] and sequence <= previous[1])):
        raise DashboardShadowProjectionError("shadow ledger events are not in strict run sequence")
    return run_id, sequence


def project_shadow_ledger_events(events: Iterable[Mapping[str, object]]) -> DashboardShadowProjection:
    """Project simulation-only P&L from explicit book-walk assumptions.

    A simulation fill is allowed only when its event explicitly identifies the
    observed-depth IOC model.  This is a useful counterfactual for the 24-hour
    shadow run, but it does not establish queue priority, hidden liquidity,
    cancellation races, or an actual venue fill.
    """
    positions: dict[tuple[str, str], dict[str, object]] = {}
    previous: tuple[str, int] | None = None
    for raw in events:
        if not isinstance(raw, Mapping):
            raise DashboardShadowProjectionError("shadow ledger event must be an object")
        run_id, _ = _event_identity(raw, previous)
        previous = run_id, raw["event_sequence"]
        event_type = _text(raw, "event_type")
        if event_type == "shadow_simulated_fill":
            position_id = _text(raw, "position_id")
            market_ticker = _text(raw, "market_ticker")
            side = _text(raw, "side")
            if side not in {"buy", "sell"}:
                raise DashboardShadowProjectionError("shadow fill side is invalid")
            if raw.get("fill_assumption") != EXACT_OBSERVED_DEPTH_IOC:
                raise DashboardShadowProjectionError("shadow fill model is not approved")
            _text(raw, "observed_book_received_utc")
            quantity = _decimal(raw, "simulated_quantity")
            price = _decimal(raw, "simulated_price")
            fee = _decimal(raw, "simulated_fee")
            if quantity <= 0 or price <= 0 or price > Decimal("1"):
                raise DashboardShadowProjectionError("shadow fill quantity or price is invalid")
            key = run_id, position_id
            state = positions.setdefault(key, {
                "market_ticker": market_ticker, "quantity": Decimal("0"),
                "entry_quantity": Decimal("0"), "exit_quantity": Decimal("0"),
                "cash_flow": Decimal("0"), "fill_count": 0, "simulated_flat": False,
            })
            if state["market_ticker"] != market_ticker or state["simulated_flat"]:
                raise DashboardShadowProjectionError("shadow fill conflicts with position state")
            signed_quantity = quantity if side == "buy" else -quantity
            if side == "sell" and state["quantity"] < quantity:
                raise DashboardShadowProjectionError("shadow exit exceeds simulated position")
            state["quantity"] += signed_quantity
            if side == "buy":
                state["entry_quantity"] += quantity
            else:
                state["exit_quantity"] += quantity
            state["cash_flow"] += -(price * quantity + fee) if side == "buy" else price * quantity - fee
            state["fill_count"] += 1
        elif event_type == "shadow_position_closed":
            position_id = _text(raw, "position_id")
            state = positions.get((run_id, position_id))
            if state is None or state["quantity"] != 0 or state["simulated_flat"]:
                raise DashboardShadowProjectionError("shadow position is not simulated flat")
            state["simulated_flat"] = True
        elif event_type == "shadow_simulated_settlement":
            position_id = _text(raw, "position_id")
            market_ticker = _text(raw, "market_ticker")
            position_side = _text(raw, "position_side")
            result = _text(raw, "official_market_result")
            if raw.get("settlement_basis") != OFFICIAL_FINAL_SETTLEMENT_BASIS:
                raise DashboardShadowProjectionError("shadow settlement basis is not approved")
            if raw.get("official_market_status") != "finalized" or result not in {"yes", "no"}:
                raise DashboardShadowProjectionError("shadow settlement is not final")
            if position_side not in {"yes", "no"}:
                raise DashboardShadowProjectionError("shadow settlement side is invalid")
            quantity = _decimal(raw, "settlement_quantity")
            payout = _decimal(raw, "simulated_settlement_payout")
            key = run_id, position_id
            state = positions.get(key)
            if (
                state is None or state["market_ticker"] != market_ticker
                or state["simulated_flat"] or quantity <= 0 or state["quantity"] != quantity
            ):
                raise DashboardShadowProjectionError("shadow settlement conflicts with position state")
            expected_payout = quantity if position_side == result else Decimal("0")
            if payout != expected_payout:
                raise DashboardShadowProjectionError("shadow settlement payout is inconsistent")
            state["quantity"] = Decimal("0")
            state["cash_flow"] += payout
        elif event_type in {"shadow_decision", "shadow_no_fill", "shadow_runtime_metric"}:
            continue
        else:
            raise DashboardShadowProjectionError("unknown shadow dashboard ledger event")
    rows = tuple(sorted((DashboardShadowTradeRow(
        run_id=run_id, position_id=position_id, market_ticker=state["market_ticker"],
        entry_simulated_quantity=state["entry_quantity"], exit_simulated_quantity=state["exit_quantity"],
        net_simulated_position_quantity=state["quantity"], net_simulated_cash_flow=state["cash_flow"],
        simulated_net_pnl=state["cash_flow"] if state["simulated_flat"] else None,
        simulated_flat=state["simulated_flat"], simulation_fill_count=state["fill_count"],
        fill_assumption=EXACT_OBSERVED_DEPTH_IOC,
    ) for (run_id, position_id), state in positions.items()), key=lambda row: (row.run_id, row.position_id)))
    total = sum((row.simulated_net_pnl for row in rows if row.simulated_net_pnl is not None), Decimal("0"))
    return DashboardShadowProjection(
        trades=rows, total_simulated_net_pnl=total,
        simulated_closed_trade_count=sum(row.simulated_flat for row in rows),
        simulated_open_position_count=sum(not row.simulated_flat for row in rows),
    )

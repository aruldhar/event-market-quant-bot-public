"""Pure accounting helpers for the frozen July-10 Candidate-E P&L contract.

No network, settlement reader, strategy runner, or order-placement code exists here.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

CONTRACT_PATH = Path("configs/kxbtcd_candidate_e_v2_july10_pnl_evaluation_contract.json")
ZERO = Decimal("0")
ONE = Decimal("1")

class PnlContractError(RuntimeError):
    pass

def require(condition: bool, message: str) -> None:
    if not condition:
        raise PnlContractError(message)

def d(value: Any, name: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PnlContractError(f"{name} must be decimal-compatible") from exc
    require(out.is_finite(), f"{name} must be finite")
    return out

def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(
        payload.get("schema_version")
        == "kxbtcd_candidate_e_v2_july10_pnl_evaluation_contract.v1",
        "unexpected P&L contract schema",
    )
    return payload

def canonical_threshold(value: Any) -> str:
    x = d(value, "threshold")
    text = format(x, "f").rstrip("0").rstrip(".")
    return text if text else "0"

def scenario_key(row: Mapping[str, Any]) -> tuple[str, str, int]:
    return (
        str(row["event_ticker"]),
        canonical_threshold(row["threshold_dollars"]),
        int(row["latency_ms"]),
    )

def validate_binary_settlement(*, market_ticker: str, settlement: Mapping[str, Any]) -> Decimal:
    require(str(settlement.get("ticker")) == market_ticker, "settlement ticker mismatch")
    require(settlement.get("market_type") == "binary", "market_type must be binary")
    require(settlement.get("status") == "finalized", "market must be finalized")
    require(bool(settlement.get("settlement_ts")), "settlement_ts is required")
    require(settlement.get("is_provisional") in (False, None), "provisional settlement rejected")
    result = str(settlement.get("result", "")).lower()
    require(result in {"yes", "no"}, "result must be yes or no")
    value = d(settlement.get("settlement_value_dollars"), "settlement_value_dollars")
    require(value in {ZERO, ONE}, "binary settlement value must be exactly 0 or 1")
    require(
        (result == "yes" and value == ONE) or (result == "no" and value == ZERO),
        "result/settlement-value inconsistency",
    )
    return value

def terminal_cash_for_side(*, side: str, quantity: Any, yes_settlement_value: Decimal) -> Decimal:
    q = d(quantity, "quantity")
    require(q >= ZERO, "quantity must be nonnegative")
    require(yes_settlement_value in {ZERO, ONE}, "YES settlement value must be 0 or 1")
    s = str(side).upper()
    require(s in {"YES", "NO"}, "side must be YES or NO")
    per_contract = yes_settlement_value if s == "YES" else ONE - yes_settlement_value
    return q * per_contract

def exact_trade_pnl(
    trade: Mapping[str, Any],
    settlements: Mapping[str, Mapping[str, Any]],
) -> Decimal:
    entry = trade["entry"]
    ioc = entry.get("ioc")
    require(ioc is not None and ioc.get("status") == "FULL", "trade entry must be FULL")
    entry_cash = d(ioc["net_cash_change_total"], "entry net cash")
    liquidation = trade["liquidation"]
    status = liquidation.get("status")

    if status == "EXIT_FULL":
        exit_ioc = liquidation.get("exit_ioc")
        require(
            exit_ioc is not None and exit_ioc.get("status") == "FULL",
            "EXIT_FULL requires full exit IOC",
        )
        return entry_cash + d(exit_ioc["net_cash_change_total"], "exit net cash")

    if status == "EXIT_MISSED_SETTLEMENT_FALLBACK":
        ticker = str(trade["signal"]["market_ticker"])
        require(ticker in settlements, f"missing settlement for {ticker}")
        yes_value = validate_binary_settlement(
            market_ticker=ticker,
            settlement=settlements[ticker],
        )
        terminal_cash = terminal_cash_for_side(
            side=str(trade["signal"]["side"]),
            quantity=liquidation["settlement_fallback_quantity"],
            yes_settlement_value=yes_value,
        )
        return entry_cash + terminal_cash

    raise PnlContractError(f"non-exact or unrecognized liquidation status: {status!r}")

def exact_policy_pnl(
    policy_result: Mapping[str, Any],
    settlements: Mapping[str, Mapping[str, Any]],
) -> Decimal:
    return sum(
        (exact_trade_pnl(trade, settlements) for trade in policy_result.get("trades", [])),
        ZERO,
    )

def event_interval(
    *,
    path_observation_class: str,
    exact_pnl: Any | None,
    contract: Mapping[str, Any],
) -> tuple[Decimal, Decimal]:
    cls = str(path_observation_class)
    if cls == "EXACT":
        require(exact_pnl is not None, "EXACT scenario requires exact_pnl")
        x = d(exact_pnl, "exact_pnl")
        return x, x
    if cls == "CENSORED":
        require(exact_pnl is None, "CENSORED scenario forbids point P&L")
        c = contract["censored_path_accounting"]
        return d(c["pnl_lower_bound_dollars"], "lower bound"), d(
            c["pnl_upper_bound_dollars"], "upper bound"
        )
    raise PnlContractError(f"unknown path observation class {cls!r}")

def aggregate_four_event_intervals(
    intervals: Sequence[tuple[Decimal, Decimal]],
) -> dict[str, Any]:
    require(len(intervals) == 4, "policy setting must contain exactly four event intervals")
    lower_sum = sum((x[0] for x in intervals), ZERO)
    upper_sum = sum((x[1] for x in intervals), ZERO)
    require(lower_sum <= upper_sum, "invalid aggregate interval")
    lower_mean = lower_sum / Decimal("4")
    upper_mean = upper_sum / Decimal("4")
    if lower_mean > ZERO:
        cls = "ROBUST_POSITIVE"
    elif upper_mean < ZERO:
        cls = "ROBUST_NEGATIVE"
    else:
        cls = "INCONCLUSIVE"
    return {
        "sum_interval": (lower_sum, upper_sum),
        "event_equal_mean_interval": (lower_mean, upper_mean),
        "classification": cls,
    }

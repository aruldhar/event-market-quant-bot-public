"""Checkpoint 21N-R: outcome-blind executable convergence/liquidation simulator.

This module implements only the frozen execution mechanics for
``kxbtcd_candidate_e_executable_convergence_liquidation_v1``.  It has no
settlement-label reader, no realized-P&L scorer, no network client, and no
order-placement path.

Important implementation conventions frozen in 21N-R:
* exact fixed-point cash/fee arithmetic uses ``Decimal``;
* historical replay is right-continuous at millisecond resolution: all
  reconstructable evidence with one timestamp is collapsed to one final state;
* a counterfactual IOC consumes visible arrival depth for that order, but the
  later observed historical book path remains exogenous (small-order,
  non-impacting future-book assumption);
* latency failure never falls through to a later signal anchor;
* the liquidation trigger scan includes the entry-arrival state, then later
  distinct reconstructed millisecond states.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_predeclaration import (
    load_predeclaration as load_strategy_predeclaration,
    validate_predeclaration as validate_strategy_predeclaration,
)
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_fee_accounting_amendment import (
    load_amendment,
    validate_amendment,
)
from .kxbtcd_candidate_e_predeclaration import (
    btc_strike_log_distance_bps,
    market_logit_offset,
)
from .kxbtcd_preoutcome_materialization import (
    STRUCTURAL_QUANTILES,
    _nearest_rank_index,
)
from .predexon_full_ladder_replay import (
    audit_ticker,
    rows_by_snapshot_pair,
)
from .predexon_segment_safe_replay import (
    ReplayPairResult,
    ReplaySegment,
    apply_delta,
    mismatch_count,
    snapshot_book,
)


STRATEGY_ID = "kxbtcd_candidate_e_executable_convergence_liquidation_v1"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
CHAMPION_FINAL_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
BASE_PREDECLARATION_FINGERPRINT = "61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6"
FEE_AMENDMENT_FINGERPRINT = "5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1"
BETA_DISTANCE_TEXT = "0.014939489324405949"

FINAL_MODEL_PATH = Path("configs/kxbtcd_candidate_e_champion_final.json")
AMENDMENT_PATH = Path("configs/kxbtcd_candidate_e_executable_convergence_liquidation_v1_fee_accounting_amendment.json")

ANCHOR_ORDER = (55, 50, 45, 40, 35, 30)
STRUCTURAL_ROLES = ("q10", "q30", "q50", "q70", "q90")
SIDES = ("YES", "NO")
SIDE_ORDER = {"YES": 0, "NO": 1}
THRESHOLDS = (
    Decimal("0.00"),
    Decimal("0.01"),
    Decimal("0.02"),
    Decimal("0.03"),
    Decimal("0.05"),
)
LATENCY_MS = (0, 500, 1000)
PLANNED_QUANTITY = Decimal("1.00")

FEE_RATE = Decimal("0.07")
TRADE_FEE_QUANTUM = Decimal("0.000001")
BALANCE_QUANTUM = Decimal("0.0001")
PRICE_QUANTUM = Decimal("0.0001")
QUANTITY_QUANTUM = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")


class ExecutableConvergenceSimulatorError(RuntimeError):
    """Raised when frozen simulator inputs or invariants fail closed."""


def _error(message: str) -> None:
    raise ExecutableConvergenceSimulatorError(message)


def _d(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ExecutableConvergenceSimulatorError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _unit(value: Any, name: str) -> Decimal:
    result = _d(value, name)
    if result < ZERO or result > ONE:
        _error(f"{name} must lie in [0,1]")
    return result


def _positive(value: Any, name: str) -> Decimal:
    result = _d(value, name)
    if result <= ZERO:
        _error(f"{name} must be positive")
    return result


def _nonnegative(value: Any, name: str) -> Decimal:
    result = _d(value, name)
    if result < ZERO:
        _error(f"{name} must be nonnegative")
    return result


def _require_grid(value: Decimal, quantum: Decimal, name: str) -> None:
    if value % quantum != ZERO:
        _error(f"{name}={value} is not aligned to {quantum}")


def _ceil_quantum(value: Decimal, quantum: Decimal) -> Decimal:
    return (value / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum


def _floor_quantum(value: Decimal, quantum: Decimal) -> Decimal:
    return (value / quantum).to_integral_value(rounding=ROUND_FLOOR) * quantum


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." not in text:
        return text
    stripped = text.rstrip("0").rstrip(".")
    return stripped if stripped else "0"


def _same_book(a: "BookState", b: "BookState") -> bool:
    return a.yes_bids == b.yes_bids and a.yes_asks == b.yes_asks


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class BookState:
    timestamp_ms: int
    yes_bids: tuple[BookLevel, ...]
    yes_asks: tuple[BookLevel, ...]


@dataclass(frozen=True)
class FillAccounting:
    action: str
    price: Decimal
    quantity: Decimal
    gross_revenue: Decimal
    trade_fee: Decimal
    aligned_balance_change: Decimal
    rounding_fee: Decimal
    rebate: Decimal
    net_fee: Decimal
    net_cash_change: Decimal
    accumulator_after: Decimal


@dataclass(frozen=True)
class IocResult:
    action: str
    limit_price: Decimal
    requested_quantity: Decimal
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    status: str
    fills: tuple[FillAccounting, ...]
    vwap: Decimal | None
    gross_notional: Decimal
    net_fee_total: Decimal
    net_cash_change_total: Decimal
    worst_fill_price: Decimal | None


@dataclass(frozen=True)
class StructuralMarket:
    market_ticker: str
    strike: Decimal
    structural_role: str
    structural_quantile: Decimal
    strike_rank_zero_based: int
    event_market_count: int


@dataclass(frozen=True)
class SignalCandidate:
    event_ticker: str
    market_ticker: str
    structural_role: str
    ttc_target_minutes: int
    decision_timestamp_ms: int
    side: str
    candidate_probability: Decimal
    side_fair_probability: Decimal
    q_market: Decimal
    decision_yes_bid: Decimal
    decision_yes_ask: Decimal
    decision_limit_price: Decimal
    signal_entry_fee: Decimal
    net_edge_per_contract: Decimal


@dataclass(frozen=True)
class EntryAttempt:
    latency_ms: int
    decision_timestamp_ms: int
    arrival_timestamp_ms: int
    source_available: bool
    source_status: str
    ioc: IocResult | None


@dataclass(frozen=True)
class LiquidationTrigger:
    trigger_timestamp_ms: int
    exit_limit_price: Decimal
    hypothetical_net_cash: Decimal


@dataclass(frozen=True)
class LiquidationBranch:
    status: str
    trigger: LiquidationTrigger | None
    exit_arrival_timestamp_ms: int | None
    exit_ioc: IocResult | None
    settlement_fallback_quantity: Decimal
    source_available: bool


@dataclass(frozen=True)
class ScenarioResult:
    signal: SignalCandidate
    latency_ms: int
    entry: EntryAttempt
    liquidation: LiquidationBranch | None
    matched_hold_settlement_quantity: Decimal


@dataclass(frozen=True)
class VerifiedSegmentTimeline:
    segment_index: int
    start_timestamp_ms: int
    end_timestamp_ms: int
    states: tuple[BookState, ...]

    def __post_init__(self) -> None:
        if self.end_timestamp_ms < self.start_timestamp_ms:
            _error("verified segment moves backward")
        if not self.states:
            _error("verified segment timeline must contain at least one state")
        timestamps = [state.timestamp_ms for state in self.states]
        if timestamps != sorted(set(timestamps)):
            _error("timeline state timestamps must be unique and increasing")
        if timestamps[0] < self.start_timestamp_ms or timestamps[-1] > self.end_timestamp_ms:
            _error("timeline state lies outside verified segment")

    def contains_interval(self, start_ms: int, end_ms: int) -> bool:
        return (
            isinstance(start_ms, int)
            and isinstance(end_ms, int)
            and self.start_timestamp_ms <= start_ms <= end_ms <= self.end_timestamp_ms
        )

    def state_at(self, timestamp_ms: int) -> BookState:
        if not self.contains_interval(timestamp_ms, timestamp_ms):
            _error("requested timestamp lies outside verified segment")
        timestamps = [state.timestamp_ms for state in self.states]
        index = bisect_right(timestamps, timestamp_ms) - 1
        if index < 0:
            _error("no right-continuous state available at requested timestamp")
        state = self.states[index]
        return BookState(timestamp_ms=timestamp_ms, yes_bids=state.yes_bids, yes_asks=state.yes_asks)

    def state_changes(self, start_ms: int, end_ms: int) -> tuple[BookState, ...]:
        if not self.contains_interval(start_ms, end_ms):
            _error("state-change interval lies outside verified segment")
        first = self.state_at(start_ms)
        later = [
            state
            for state in self.states
            if start_ms < state.timestamp_ms <= end_ms
        ]
        output: list[BookState] = [first]
        for state in later:
            if not _same_book(output[-1], state):
                output.append(state)
        return tuple(output)


@dataclass(frozen=True)
class VerifiedTickerTimeline:
    ticker: str
    segments: tuple[VerifiedSegmentTimeline, ...]

    def unique_segment_for_interval(
        self, start_ms: int, end_ms: int
    ) -> VerifiedSegmentTimeline | None:
        matches = [segment for segment in self.segments if segment.contains_interval(start_ms, end_ms)]
        return matches[0] if len(matches) == 1 else None


def _book_state_from_maps(
    timestamp_ms: int,
    yes_bids: Mapping[Decimal, Decimal],
    yes_asks: Mapping[Decimal, Decimal],
) -> BookState:
    bids = tuple(
        BookLevel(price=price, quantity=quantity)
        for price, quantity in sorted(yes_bids.items(), key=lambda item: item[0], reverse=True)
        if quantity > ZERO
    )
    asks = tuple(
        BookLevel(price=price, quantity=quantity)
        for price, quantity in sorted(yes_asks.items(), key=lambda item: item[0])
        if quantity > ZERO
    )
    for level in (*bids, *asks):
        _unit(level.price, "book price")
        _nonnegative(level.quantity, "book quantity")
    return BookState(timestamp_ms=int(timestamp_ms), yes_bids=bids, yes_asks=asks)


def _maps_from_book_state(state: BookState) -> tuple[dict[Decimal, Decimal], dict[Decimal, Decimal]]:
    return (
        {level.price: level.quantity for level in state.yes_bids},
        {level.price: level.quantity for level in state.yes_asks},
    )


def _pair_replay_rows(
    start_snapshot: Mapping[str, Any],
    end_snapshot: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    result: ReplayPairResult,
) -> tuple[Mapping[str, Any], ...]:
    if not result.exact:
        _error("cannot construct timeline through unreconciled pair")
    start_ts = int(start_snapshot["timestamp"])
    end_ts = int(end_snapshot["timestamp"])
    ordered = sorted(rows, key=lambda row: (int(row["timestamp"]), int(row["sequence"])))

    if start_ts == end_ts:
        batch = [row for row in ordered if int(row["timestamp"]) == start_ts]
        return tuple(batch[result.start_cut:result.end_cut])

    start_batch = [row for row in ordered if int(row["timestamp"]) == start_ts]
    middle = [row for row in ordered if start_ts < int(row["timestamp"]) < end_ts]
    end_batch = [row for row in ordered if int(row["timestamp"]) == end_ts]
    return tuple(
        [
            *start_batch[result.start_cut:],
            *middle,
            *end_batch[:result.end_cut],
        ]
    )


def build_verified_ticker_timeline(
    *,
    ticker: str,
    snapshots: Sequence[Mapping[str, Any]],
    paid_rows: Sequence[Mapping[str, Any]],
) -> VerifiedTickerTimeline:
    """Build deterministic right-continuous millisecond book states.

    Every failed snapshot reconciliation remains a hard segment boundary.
    Within one exact segment, snapshots are authoritative boundary states and
    paid deltas reconstruct the path between them.  Multiple observations with
    the same millisecond are collapsed to the final reconstructable state for
    that millisecond; no sub-millisecond transient is exposed to the strategy.
    """
    summary, segments, pair_results = audit_ticker(
        ticker=ticker, snapshots=snapshots, paid_rows=paid_rows
    )
    del summary
    pair_rows = rows_by_snapshot_pair(snapshots, paid_rows)
    timelines: list[VerifiedSegmentTimeline] = []

    for segment_index, segment in enumerate(segments):
        by_timestamp: dict[int, BookState] = {}
        start_snapshot = snapshots[segment.start_snapshot_index]
        start_bids, start_asks = snapshot_book(start_snapshot)
        by_timestamp[int(start_snapshot["timestamp"])] = _book_state_from_maps(
            int(start_snapshot["timestamp"]), start_bids, start_asks
        )

        for pair_index in range(segment.start_snapshot_index, segment.end_snapshot_index):
            result = pair_results[pair_index]
            if not result.exact:
                _error("verified segment unexpectedly contains a failed pair")

            a = snapshots[pair_index]
            b = snapshots[pair_index + 1]
            bids, asks = snapshot_book(a)
            by_timestamp[int(a["timestamp"])] = _book_state_from_maps(
                int(a["timestamp"]), bids, asks
            )
            for row in _pair_replay_rows(a, b, pair_rows[pair_index], result):
                apply_delta(bids, asks, row)
                ts = int(row["timestamp"])
                by_timestamp[ts] = _book_state_from_maps(ts, bids, asks)

            expected_bids, expected_asks = snapshot_book(b)
            if mismatch_count(bids, expected_bids) or mismatch_count(asks, expected_asks):
                _error("exact replay pair failed independent timeline reconstruction")
            by_timestamp[int(b["timestamp"])] = _book_state_from_maps(
                int(b["timestamp"]), expected_bids, expected_asks
            )

        ordered = [by_timestamp[ts] for ts in sorted(by_timestamp)]
        compressed: list[BookState] = []
        for state in ordered:
            if not compressed or not _same_book(compressed[-1], state):
                compressed.append(state)
        timelines.append(
            VerifiedSegmentTimeline(
                segment_index=segment_index,
                start_timestamp_ms=int(segment.start_timestamp),
                end_timestamp_ms=int(segment.end_timestamp),
                states=tuple(compressed),
            )
        )

    return VerifiedTickerTimeline(ticker=ticker, segments=tuple(timelines))


def validate_frozen_parents(repository_root: str | Path = ".") -> dict[str, str]:
    repo = Path(repository_root)
    strategy = load_strategy_predeclaration(
        repo / "configs/kxbtcd_candidate_e_executable_convergence_liquidation_v1_predeclaration.json"
    )
    validate_strategy_predeclaration(strategy)
    if strategy.get("predeclaration_fingerprint") != BASE_PREDECLARATION_FINGERPRINT:
        _error("base strategy fingerprint mismatch")

    amendment = load_amendment(repo / AMENDMENT_PATH)
    validate_amendment(amendment)
    if amendment.get("amendment_fingerprint") != FEE_AMENDMENT_FINGERPRINT:
        _error("fee amendment fingerprint mismatch")

    model = json.loads((repo / FINAL_MODEL_PATH).read_text(encoding="utf-8"))
    if model.get("candidate_id") != CANDIDATE_ID:
        _error("Champion-Final candidate mismatch")
    if model.get("champion_final_fingerprint") != CHAMPION_FINAL_FINGERPRINT:
        _error("Champion-Final fingerprint mismatch")
    if model.get("model", {}).get("beta_distance") != BETA_DISTANCE_TEXT:
        _error("Champion-Final beta_distance mismatch")
    if model.get("model", {}).get("formula") != "logit(p)=market_logit_offset + beta_distance*d_BTC":
        _error("Champion-Final formula mismatch")
    if model.get("remaining_historical_reserve_accessed") is not False:
        _error("Champion-Final reserve boundary changed")
    return {
        "strategy_predeclaration_fingerprint": BASE_PREDECLARATION_FINGERPRINT,
        "fee_accounting_amendment_fingerprint": FEE_AMENDMENT_FINGERPRINT,
        "champion_final_fingerprint": CHAMPION_FINAL_FINGERPRINT,
    }


def account_synthetic_fill(
    *,
    action: str,
    price: Any,
    quantity: Any,
    accumulator_before: Any = ZERO,
) -> FillAccounting:
    action = str(action).upper()
    if action not in {"BUY", "SELL"}:
        _error("action must be BUY or SELL")
    p = _unit(price, "price")
    q = _positive(quantity, "quantity")
    accumulator = _nonnegative(accumulator_before, "accumulator_before")
    _require_grid(p, PRICE_QUANTUM, "price")
    _require_grid(q, QUANTITY_QUANTUM, "quantity")

    model_fee = FEE_RATE * q * p * (ONE - p)
    trade_fee = _ceil_quantum(model_fee, TRADE_FEE_QUANTUM)
    gross_revenue = p * q if action == "SELL" else -(p * q)
    pre_alignment = gross_revenue - trade_fee
    aligned = _floor_quantum(pre_alignment, BALANCE_QUANTUM)
    rounding_fee = pre_alignment - aligned
    if rounding_fee < ZERO or rounding_fee >= BALANCE_QUANTUM:
        _error("rounding fee escaped one balance quantum")

    accumulator_with_rounding = accumulator + rounding_fee
    rebate_cap = min(accumulator_with_rounding, trade_fee + rounding_fee)
    rebate = max(ZERO, _floor_quantum(rebate_cap, BALANCE_QUANTUM))
    net_fee = trade_fee + rounding_fee - rebate
    accumulator_after = accumulator_with_rounding - rebate
    net_cash_change = aligned + rebate

    if net_fee < ZERO:
        _error("net fee became negative")
    if accumulator_after < ZERO:
        _error("rounding accumulator became negative")
    if net_cash_change != gross_revenue - net_fee:
        _error("cash/fee accounting identity failed")

    return FillAccounting(
        action=action,
        price=p,
        quantity=q,
        gross_revenue=gross_revenue,
        trade_fee=trade_fee,
        aligned_balance_change=aligned,
        rounding_fee=rounding_fee,
        rebate=rebate,
        net_fee=net_fee,
        net_cash_change=net_cash_change,
        accumulator_after=accumulator_after,
    )


def simulate_ioc(
    *,
    action: str,
    levels: Sequence[BookLevel],
    limit_price: Any,
    requested_quantity: Any,
) -> IocResult:
    action = str(action).upper()
    if action not in {"BUY", "SELL"}:
        _error("IOC action must be BUY or SELL")
    limit = _unit(limit_price, "limit_price")
    requested = _positive(requested_quantity, "requested_quantity")
    _require_grid(limit, PRICE_QUANTUM, "limit_price")
    _require_grid(requested, QUANTITY_QUANTUM, "requested_quantity")

    normalized: list[BookLevel] = []
    for level in levels:
        price = _unit(level.price, "level.price")
        quantity = _nonnegative(level.quantity, "level.quantity")
        _require_grid(price, PRICE_QUANTUM, "level.price")
        _require_grid(quantity, QUANTITY_QUANTUM, "level.quantity")
        if quantity > ZERO:
            normalized.append(BookLevel(price, quantity))
    normalized.sort(key=lambda level: level.price, reverse=(action == "SELL"))

    remaining = requested
    accumulator = ZERO
    fills: list[FillAccounting] = []
    for level in normalized:
        eligible = level.price <= limit if action == "BUY" else level.price >= limit
        if not eligible:
            continue
        fill_qty = min(level.quantity, remaining)
        if fill_qty <= ZERO:
            continue
        accounting = account_synthetic_fill(
            action=action,
            price=level.price,
            quantity=fill_qty,
            accumulator_before=accumulator,
        )
        fills.append(accounting)
        accumulator = accounting.accumulator_after
        remaining -= fill_qty
        if remaining == ZERO:
            break

    filled = requested - remaining
    status = "MISSED" if filled == ZERO else ("FULL" if remaining == ZERO else "PARTIAL")
    gross_notional = sum((fill.price * fill.quantity for fill in fills), ZERO)
    vwap = gross_notional / filled if filled > ZERO else None
    return IocResult(
        action=action,
        limit_price=limit,
        requested_quantity=requested,
        filled_quantity=filled,
        unfilled_quantity=remaining,
        status=status,
        fills=tuple(fills),
        vwap=vwap,
        gross_notional=gross_notional,
        net_fee_total=sum((fill.net_fee for fill in fills), ZERO),
        net_cash_change_total=sum((fill.net_cash_change for fill in fills), ZERO),
        worst_fill_price=(fills[-1].price if fills else None),
    )


def best_yes_quote(state: BookState) -> tuple[BookLevel, BookLevel]:
    if not state.yes_bids or not state.yes_asks:
        _error("two-sided YES book required")
    bid = state.yes_bids[0]
    ask = state.yes_asks[0]
    if bid.price > ask.price:
        _error("crossed YES book")
    return bid, ask


def side_purchase_asks(state: BookState, side: str) -> tuple[BookLevel, ...]:
    side = str(side).upper()
    if side == "YES":
        return state.yes_asks
    if side == "NO":
        return tuple(
            sorted(
                (BookLevel(ONE - level.price, level.quantity) for level in state.yes_bids),
                key=lambda level: level.price,
            )
        )
    _error("side must be YES or NO")
    raise AssertionError


def side_sale_bids(state: BookState, side: str) -> tuple[BookLevel, ...]:
    side = str(side).upper()
    if side == "YES":
        return state.yes_bids
    if side == "NO":
        return tuple(
            sorted(
                (BookLevel(ONE - level.price, level.quantity) for level in state.yes_asks),
                key=lambda level: level.price,
                reverse=True,
            )
        )
    _error("side must be YES or NO")
    raise AssertionError


def candidate_e_probability(
    *,
    q_market: Any,
    btc_spot: Any,
    strike: Any,
) -> Decimal:
    q = _unit(q_market, "q_market")
    spot = _positive(btc_spot, "btc_spot")
    k = _positive(strike, "strike")
    offset = market_logit_offset(float(q))
    distance = btc_strike_log_distance_bps(float(spot), float(k))
    eta = offset + float(BETA_DISTANCE_TEXT) * distance
    if eta >= 0:
        exp_neg = math.exp(-eta)
        probability = 1.0 / (1.0 + exp_neg)
    else:
        exp_pos = math.exp(eta)
        probability = exp_pos / (1.0 + exp_pos)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        _error("Candidate-E probability became invalid")
    return Decimal(format(probability, ".17g"))


def side_fair_probability(side: str, candidate_probability: Any) -> Decimal:
    side = str(side).upper()
    p = _unit(candidate_probability, "candidate_probability")
    if side == "YES":
        return p
    if side == "NO":
        return ONE - p
    _error("side must be YES or NO")
    raise AssertionError


def select_structural_markets(
    markets: Sequence[tuple[str, Any]],
) -> tuple[StructuralMarket, ...]:
    """Apply the already-frozen nearest-rank-half-up structural role rule."""
    if len(markets) < len(STRUCTURAL_ROLES):
        _error("at least five distinct markets are required")
    normalized: list[tuple[Decimal, str]] = []
    seen_tickers: set[str] = set()
    seen_strikes: set[Decimal] = set()
    for ticker, strike_value in markets:
        ticker = str(ticker).strip()
        if not ticker or ticker in seen_tickers:
            _error("market tickers must be unique non-empty strings")
        strike = _positive(strike_value, "strike")
        if strike in seen_strikes:
            _error("market strikes must be distinct")
        seen_tickers.add(ticker)
        seen_strikes.add(strike)
        normalized.append((strike, ticker))
    normalized.sort(key=lambda item: (item[0], item[1]))

    indices = [_nearest_rank_index(len(normalized), quantile) for quantile in STRUCTURAL_QUANTILES]
    if len(indices) != len(set(indices)):
        _error("structural quantile ranks collapsed")

    result: list[StructuralMarket] = []
    for role, quantile, index in zip(STRUCTURAL_ROLES, STRUCTURAL_QUANTILES, indices):
        strike, ticker = normalized[index]
        result.append(
            StructuralMarket(
                market_ticker=ticker,
                strike=strike,
                structural_role=role,
                structural_quantile=quantile,
                strike_rank_zero_based=index,
                event_market_count=len(normalized),
            )
        )
    return tuple(result)


def build_signal_candidates(
    *,
    event_ticker: str,
    market_ticker: str,
    structural_role: str,
    ttc_target_minutes: int,
    decision_timestamp_ms: int,
    btc_spot: Any,
    strike: Any,
    timeline: VerifiedTickerTimeline,
) -> tuple[SignalCandidate, ...]:
    if structural_role not in STRUCTURAL_ROLES:
        _error("structural role outside frozen set")
    if int(ttc_target_minutes) not in ANCHOR_ORDER:
        _error("TTC anchor outside frozen set")
    if timeline.ticker != market_ticker:
        _error("timeline ticker does not match market ticker")

    segment = timeline.unique_segment_for_interval(decision_timestamp_ms, decision_timestamp_ms)
    if segment is None:
        return ()
    state = segment.state_at(decision_timestamp_ms)
    bid, ask = best_yes_quote(state)
    q_market = (bid.price + ask.price) / Decimal("2")
    probability = candidate_e_probability(q_market=q_market, btc_spot=btc_spot, strike=strike)

    candidates: list[SignalCandidate] = []
    for side in SIDES:
        purchase_asks = side_purchase_asks(state, side)
        if not purchase_asks:
            continue
        best_level = purchase_asks[0]
        # Frozen signal rule: the decision-time best purchase price level itself,
        # not cumulative deeper depth, must display at least 1.00 contract.
        if best_level.quantity < PLANNED_QUANTITY:
            continue
        fee = account_synthetic_fill(
            action="BUY",
            price=best_level.price,
            quantity=PLANNED_QUANTITY,
            accumulator_before=ZERO,
        ).net_fee
        fair = side_fair_probability(side, probability)
        edge = fair - best_level.price - fee
        candidates.append(
            SignalCandidate(
                event_ticker=str(event_ticker),
                market_ticker=market_ticker,
                structural_role=structural_role,
                ttc_target_minutes=int(ttc_target_minutes),
                decision_timestamp_ms=int(decision_timestamp_ms),
                side=side,
                candidate_probability=probability,
                side_fair_probability=fair,
                q_market=q_market,
                decision_yes_bid=bid.price,
                decision_yes_ask=ask.price,
                decision_limit_price=best_level.price,
                signal_entry_fee=fee,
                net_edge_per_contract=edge,
            )
        )
    return tuple(candidates)


def select_event_signal(
    candidates: Sequence[SignalCandidate],
    *,
    threshold: Any,
) -> SignalCandidate | None:
    threshold_d = _d(threshold, "threshold")
    if threshold_d not in THRESHOLDS:
        _error("threshold outside frozen menu")
    if not candidates:
        return None
    events = {candidate.event_ticker for candidate in candidates}
    if len(events) != 1:
        _error("event signal selection must contain exactly one event")
    for ttc in ANCHOR_ORDER:
        qualifying = [
            candidate
            for candidate in candidates
            if candidate.ttc_target_minutes == ttc
            and candidate.net_edge_per_contract >= threshold_d
        ]
        if qualifying:
            qualifying.sort(
                key=lambda candidate: (
                    -candidate.net_edge_per_contract,
                    candidate.market_ticker,
                    SIDE_ORDER[candidate.side],
                )
            )
            return qualifying[0]
    return None


def simulate_entry(
    *,
    signal: SignalCandidate,
    timeline: VerifiedTickerTimeline,
    latency_ms: int,
) -> EntryAttempt:
    if latency_ms not in LATENCY_MS:
        _error("latency outside frozen scenarios")
    arrival = signal.decision_timestamp_ms + latency_ms
    segment = timeline.unique_segment_for_interval(signal.decision_timestamp_ms, arrival)
    if segment is None:
        return EntryAttempt(
            latency_ms=latency_ms,
            decision_timestamp_ms=signal.decision_timestamp_ms,
            arrival_timestamp_ms=arrival,
            source_available=False,
            source_status="SOURCE_UNAVAILABLE_DECISION_TO_ARRIVAL",
            ioc=None,
        )
    state = segment.state_at(arrival)
    ioc = simulate_ioc(
        action="BUY",
        levels=side_purchase_asks(state, signal.side),
        limit_price=signal.decision_limit_price,
        requested_quantity=PLANNED_QUANTITY,
    )
    return EntryAttempt(
        latency_ms=latency_ms,
        decision_timestamp_ms=signal.decision_timestamp_ms,
        arrival_timestamp_ms=arrival,
        source_available=True,
        source_status="AVAILABLE",
        ioc=ioc,
    )


def _hypothetical_full_liquidation(
    *,
    state: BookState,
    side: str,
    quantity: Decimal,
) -> IocResult:
    return simulate_ioc(
        action="SELL",
        levels=side_sale_bids(state, side),
        limit_price=ZERO,
        requested_quantity=quantity,
    )


def simulate_liquidation_branch(
    *,
    signal: SignalCandidate,
    entry: EntryAttempt,
    timeline: VerifiedTickerTimeline,
    event_close_timestamp_ms: int,
) -> LiquidationBranch | None:
    if not entry.source_available or entry.ioc is None:
        return None
    open_quantity = entry.ioc.filled_quantity
    if open_quantity == ZERO:
        return None
    if event_close_timestamp_ms < entry.arrival_timestamp_ms:
        _error("event close precedes entry arrival")

    segment = timeline.unique_segment_for_interval(entry.arrival_timestamp_ms, entry.arrival_timestamp_ms)
    if segment is None:
        return LiquidationBranch(
            status="SOURCE_UNAVAILABLE_ENTRY_ARRIVAL",
            trigger=None,
            exit_arrival_timestamp_ms=None,
            exit_ioc=None,
            settlement_fallback_quantity=open_quantity,
            source_available=False,
        )

    scan_end = min(event_close_timestamp_ms, segment.end_timestamp_ms)
    trigger: LiquidationTrigger | None = None
    for state in segment.state_changes(entry.arrival_timestamp_ms, scan_end):
        hypothetical = _hypothetical_full_liquidation(
            state=state,
            side=signal.side,
            quantity=open_quantity,
        )
        if (
            hypothetical.status == "FULL"
            and hypothetical.net_cash_change_total
            >= signal.side_fair_probability * open_quantity
        ):
            if hypothetical.worst_fill_price is None:
                _error("full hypothetical liquidation missing worst fill price")
            trigger = LiquidationTrigger(
                trigger_timestamp_ms=state.timestamp_ms,
                exit_limit_price=hypothetical.worst_fill_price,
                hypothetical_net_cash=hypothetical.net_cash_change_total,
            )
            break

    if trigger is None:
        if event_close_timestamp_ms <= segment.end_timestamp_ms:
            return LiquidationBranch(
                status="HOLD_TO_SETTLEMENT_NO_TRIGGER",
                trigger=None,
                exit_arrival_timestamp_ms=None,
                exit_ioc=None,
                settlement_fallback_quantity=open_quantity,
                source_available=True,
            )
        return LiquidationBranch(
            status="SOURCE_UNAVAILABLE_MONITORING_GAP",
            trigger=None,
            exit_arrival_timestamp_ms=None,
            exit_ioc=None,
            settlement_fallback_quantity=open_quantity,
            source_available=False,
        )

    exit_arrival = trigger.trigger_timestamp_ms + entry.latency_ms
    if exit_arrival > event_close_timestamp_ms:
        return LiquidationBranch(
            status="SOURCE_UNAVAILABLE_EXIT_AFTER_CLOSE",
            trigger=trigger,
            exit_arrival_timestamp_ms=exit_arrival,
            exit_ioc=None,
            settlement_fallback_quantity=open_quantity,
            source_available=False,
        )
    exit_segment = timeline.unique_segment_for_interval(trigger.trigger_timestamp_ms, exit_arrival)
    if exit_segment is None:
        return LiquidationBranch(
            status="SOURCE_UNAVAILABLE_TRIGGER_TO_EXIT_ARRIVAL",
            trigger=trigger,
            exit_arrival_timestamp_ms=exit_arrival,
            exit_ioc=None,
            settlement_fallback_quantity=open_quantity,
            source_available=False,
        )
    state = exit_segment.state_at(exit_arrival)
    exit_ioc = simulate_ioc(
        action="SELL",
        levels=side_sale_bids(state, signal.side),
        limit_price=trigger.exit_limit_price,
        requested_quantity=open_quantity,
    )
    fallback = open_quantity - exit_ioc.filled_quantity
    if exit_ioc.status == "FULL":
        status = "EXIT_FULL"
    elif exit_ioc.status == "PARTIAL":
        status = "EXIT_PARTIAL_SETTLEMENT_FALLBACK"
    else:
        status = "EXIT_MISSED_SETTLEMENT_FALLBACK"
    return LiquidationBranch(
        status=status,
        trigger=trigger,
        exit_arrival_timestamp_ms=exit_arrival,
        exit_ioc=exit_ioc,
        settlement_fallback_quantity=fallback,
        source_available=True,
    )


def simulate_scenario(
    *,
    signal: SignalCandidate,
    timeline: VerifiedTickerTimeline,
    latency_ms: int,
    event_close_timestamp_ms: int,
) -> ScenarioResult:
    entry = simulate_entry(signal=signal, timeline=timeline, latency_ms=latency_ms)
    liquidation = simulate_liquidation_branch(
        signal=signal,
        entry=entry,
        timeline=timeline,
        event_close_timestamp_ms=event_close_timestamp_ms,
    )
    hold_quantity = (
        entry.ioc.filled_quantity
        if entry.source_available and entry.ioc is not None
        else ZERO
    )
    return ScenarioResult(
        signal=signal,
        latency_ms=latency_ms,
        entry=entry,
        liquidation=liquidation,
        matched_hold_settlement_quantity=hold_quantity,
    )

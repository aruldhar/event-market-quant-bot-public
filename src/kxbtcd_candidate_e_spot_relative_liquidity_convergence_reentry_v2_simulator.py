"""Checkpoint 21N-Y-A: settlement-blind V2 dynamic ATM-window simulator.

This module implements the exact 21N-X predeclaration for
kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2.

It contains no outcome reader, no settlement-value reader, no network client,
and no order-placement path.  Real July 10 nonstructural Candidate-E paths must
not be run until this implementation is frozen and committed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_continuous_btc_materialization import (
    EVENT_CLOSE_UTC,
    ContinuousBtcRow,
    btc_row_for_decision,
    epoch_ms,
    materialization_index,
    parse_utc,
    scan_bounds_ms,
)
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_predeclaration import (
    EXPECTED_PREDECLARATION_FINGERPRINT,
    validate_predeclaration,
)
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    LATENCY_MS,
    PLANNED_QUANTITY,
    SIDE_ORDER,
    THRESHOLDS,
    ZERO,
    EntryAttempt,
    ExecutableConvergenceSimulatorError,
    LiquidationBranch,
    SignalCandidate,
    VerifiedTickerTimeline,
    account_synthetic_fill,
    best_yes_quote,
    candidate_e_probability,
    side_fair_probability,
    side_purchase_asks,
    simulate_entry,
    simulate_liquidation_branch,
    validate_frozen_parents,
)
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_freeze import (
    validate_freeze as validate_21n_r_freeze,
)
from .kxbtcd_candidate_e_july10_outcome_blind_binding import (
    EXPECTED_EVENT_MARKET_COUNTS,
    parse_kxbtcd_threshold_ticker,
)

STRATEGY_ID = "kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2"
RANK_RADIUS = 5
MAX_WINDOW_MARKETS = 11
MIN_DEPTH = Decimal("1.00")
ORIGINAL_ANCHORS = (55, 50, 45, 40, 35, 30)
NONSTRUCTURAL_DOMAIN_LABEL = "nonstructural_spot_window_domain_extension"
STRUCTURAL_DOMAIN_LABEL = "historical_structural_role_inside_spot_window"


class SpotRelativeV2SimulatorError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise SpotRelativeV2SimulatorError(message)


@dataclass(frozen=True)
class LadderMarket:
    event_ticker: str
    market_ticker: str
    strike: Decimal
    strike_rank_zero_based: int
    event_market_count: int
    historical_structural_role: str | None


@dataclass(frozen=True)
class WindowMarket:
    event_ticker: str
    market_ticker: str
    strike: Decimal
    strike_rank_zero_based: int
    event_market_count: int
    atm_market_ticker: str
    atm_strike: Decimal
    atm_rank_zero_based: int
    rank_from_atm: int
    historical_structural_role: str | None
    market_domain_label: str


@dataclass(frozen=True)
class V2SideEvaluation:
    side: str
    purchase_price: Decimal
    decision_level_quantity: Decimal
    depth_qualifies: bool
    fair_probability: Decimal
    entry_fee: Decimal
    net_edge: Decimal


@dataclass(frozen=True)
class V2MarketEvaluation:
    event_ticker: str
    market_ticker: str
    strike: Decimal
    strike_rank_zero_based: int
    atm_market_ticker: str
    atm_strike: Decimal
    atm_rank_zero_based: int
    rank_from_atm: int
    historical_structural_role: str | None
    market_domain_label: str
    decision_timestamp_ms: int
    decision_ttc_ms: int
    btc_spot: Decimal
    btc_minute_start_ms: int
    btc_state_age_ms: int
    status: str
    q_market: Decimal | None
    candidate_probability: Decimal | None
    decision_yes_bid: Decimal | None
    decision_yes_ask: Decimal | None
    sides: tuple[V2SideEvaluation, ...]


@dataclass(frozen=True)
class V2Signal:
    event_ticker: str
    market_ticker: str
    strike: Decimal
    strike_rank_zero_based: int
    atm_market_ticker: str
    atm_strike: Decimal
    atm_rank_zero_based: int
    rank_from_atm: int
    historical_structural_role: str | None
    market_domain_label: str
    decision_timestamp_ms: int
    decision_ttc_ms: int
    ttc_bucket: str
    is_exact_original_anchor: bool
    continuous_time_domain_label: str
    late_window_extrapolation: bool
    side: str
    btc_spot: Decimal
    btc_minute_start_ms: int
    btc_state_age_ms: int
    q_market: Decimal
    candidate_probability: Decimal
    side_fair_probability: Decimal
    decision_yes_bid: Decimal
    decision_yes_ask: Decimal
    decision_limit_price: Decimal
    decision_level_quantity: Decimal
    signal_entry_fee: Decimal
    net_edge_per_contract: Decimal


@dataclass(frozen=True)
class V2EntryAttemptRecord:
    trade_number: int
    signal: V2Signal
    latency_ms: int
    entry: EntryAttempt


@dataclass(frozen=True)
class V2TradePath:
    trade_number: int
    signal: V2Signal
    latency_ms: int
    entry: EntryAttempt
    liquidation: LiquidationBranch | None
    fully_closed_round_trip_cash_change: Decimal | None
    matched_hold_settlement_quantity: Decimal


@dataclass(frozen=True)
class V2RearmRecord:
    reference_market_ticker: str
    reference_side: str
    rearm_timestamp_ms: int
    reason: str


@dataclass(frozen=True)
class V2PolicyResult:
    event_ticker: str
    threshold: Decimal
    latency_ms: int
    decision_clock_count: int
    entry_attempts: tuple[V2EntryAttemptRecord, ...]
    trades: tuple[V2TradePath, ...]
    rearm: V2RearmRecord | None
    terminal_state: str


def validate_parents(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)

    predecl = validate_predeclaration(repo)
    if predecl.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        _fail("21N-X V2 predeclaration fingerprint mismatch")

    parent = validate_frozen_parents(repo)
    r_freeze = validate_21n_r_freeze(repo)
    if (
        r_freeze.get("implementation_fingerprint")
        != "6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf"
    ):
        _fail("21N-R implementation fingerprint mismatch")

    return {
        "v2_predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "simulator_21n_r_implementation_fingerprint": r_freeze[
            "implementation_fingerprint"
        ],
        **parent,
    }


def ttc_bucket(ttc_ms: int) -> str:
    minutes = Decimal(int(ttc_ms)) / Decimal(60000)
    if 45 < minutes <= 55:
        return "55_to_45"
    if 30 < minutes <= 45:
        return "45_to_30"
    if 20 < minutes <= 30:
        return "30_to_20"
    if 10 < minutes <= 20:
        return "20_to_10"
    if 5 < minutes <= 10:
        return "10_to_5"
    if 2 <= minutes <= 5:
        return "5_to_2"
    _fail("TTC outside frozen T-55 to T-2 entry window")
    raise AssertionError


def exact_original_anchor(ttc_ms: int) -> bool:
    return int(ttc_ms) in {minute * 60000 for minute in ORIGINAL_ANCHORS}


def continuous_time_domain_label(ttc_ms: int) -> tuple[str, bool]:
    if exact_original_anchor(ttc_ms):
        return "exact_original_anchor", False
    if ttc_ms < 30 * 60000:
        return (
            "continuous_time_extrapolation__late_window_outside_historical_candidate_e_ttc_support",
            True,
        )
    return "continuous_time_extrapolation", False


def build_event_ladders(
    paid_tickers: Sequence[str],
    structural_rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[LadderMarket, ...]]:
    structural_role_by_ticker = {
        str(row["market_ticker"]): str(row["structural_role"])
        for row in structural_rows
    }

    by_event: dict[str, list[tuple[Decimal, str]]] = {}
    seen: set[str] = set()
    for raw_ticker in paid_tickers:
        ticker = str(raw_ticker)
        if ticker in seen:
            _fail(f"duplicate paid ticker: {ticker}")
        seen.add(ticker)
        event, strike = parse_kxbtcd_threshold_ticker(ticker)
        by_event.setdefault(event, []).append((Decimal(str(strike)), ticker))

    if set(by_event) != set(EXPECTED_EVENT_MARKET_COUNTS):
        _fail("full-ladder event set mismatch")

    output: dict[str, tuple[LadderMarket, ...]] = {}
    for event in sorted(by_event):
        ordered = sorted(by_event[event], key=lambda item: (item[0], item[1]))
        if len(ordered) != EXPECTED_EVENT_MARKET_COUNTS[event]:
            _fail(f"full-ladder market count mismatch for {event}")
        if len({strike for strike, _ in ordered}) != len(ordered):
            _fail(f"duplicate strike in full ladder for {event}")

        rows = []
        for rank, (strike, ticker) in enumerate(ordered):
            rows.append(
                LadderMarket(
                    event_ticker=event,
                    market_ticker=ticker,
                    strike=strike,
                    strike_rank_zero_based=rank,
                    event_market_count=len(ordered),
                    historical_structural_role=structural_role_by_ticker.get(ticker),
                )
            )
        output[event] = tuple(rows)

    return output


def spot_window(
    *,
    event_ticker: str,
    btc_spot: Decimal,
    event_ladder: Sequence[LadderMarket],
) -> tuple[WindowMarket, ...]:
    if not event_ladder:
        _fail("event ladder is empty")
    if any(m.event_ticker != event_ticker for m in event_ladder):
        _fail("event ladder contains another event")

    spot = Decimal(str(btc_spot))
    if not spot.is_finite() or spot <= 0:
        _fail("BTC spot must be positive and finite")

    atm = min(
        event_ladder,
        key=lambda market: (
            abs(market.strike - spot),
            market.strike,
            market.market_ticker,
        ),
    )
    atm_rank = atm.strike_rank_zero_based

    low = max(0, atm_rank - RANK_RADIUS)
    high = min(len(event_ladder) - 1, atm_rank + RANK_RADIUS)

    result = []
    for market in event_ladder[low : high + 1]:
        role = market.historical_structural_role
        result.append(
            WindowMarket(
                event_ticker=event_ticker,
                market_ticker=market.market_ticker,
                strike=market.strike,
                strike_rank_zero_based=market.strike_rank_zero_based,
                event_market_count=market.event_market_count,
                atm_market_ticker=atm.market_ticker,
                atm_strike=atm.strike,
                atm_rank_zero_based=atm_rank,
                rank_from_atm=market.strike_rank_zero_based - atm_rank,
                historical_structural_role=role,
                market_domain_label=(
                    STRUCTURAL_DOMAIN_LABEL if role is not None else NONSTRUCTURAL_DOMAIN_LABEL
                ),
            )
        )

    if len(result) > MAX_WINDOW_MARKETS:
        _fail("ATM window exceeded maximum 11 markets")
    if not any(row.market_ticker == atm.market_ticker for row in result):
        _fail("ATM market missing from its own window")
    if any(abs(row.rank_from_atm) > RANK_RADIUS for row in result):
        _fail("ATM window rank radius escaped ±5")

    return tuple(result)


def required_dynamic_tickers(
    *,
    event_ladders: Mapping[str, Sequence[LadderMarket]],
    btc_rows: Sequence[ContinuousBtcRow],
) -> tuple[str, ...]:
    index = materialization_index(btc_rows)
    selected: set[str] = set()

    for event in sorted(EVENT_CLOSE_UTC):
        ladder = event_ladders[event]
        lo, hi = scan_bounds_ms(event)
        for timestamp_ms in range(lo, hi + 1, 60000):
            btc = btc_row_for_decision(
                index,
                event_ticker=event,
                decision_timestamp_ms=timestamp_ms,
            )
            if btc is None:
                continue
            selected.update(
                row.market_ticker
                for row in spot_window(
                    event_ticker=event,
                    btc_spot=btc.close_price,
                    event_ladder=ladder,
                )
            )

    if not selected:
        _fail("dynamic ticker union is empty")
    return tuple(sorted(selected))


def _top_signature(state) -> tuple[Any, ...]:
    bid = state.yes_bids[0] if state.yes_bids else None
    ask = state.yes_asks[0] if state.yes_asks else None
    return (
        None if bid is None else bid.price,
        None if bid is None else bid.quantity,
        None if ask is None else ask.price,
        None if ask is None else ask.quantity,
    )


def decision_clock(
    *,
    event_ticker: str,
    event_ladder: Sequence[LadderMarket],
    timelines: Mapping[str, VerifiedTickerTimeline],
    btc_rows_or_index: Sequence[ContinuousBtcRow] | Mapping[tuple[str, int], ContinuousBtcRow],
) -> tuple[int, ...]:
    """Build the causal event-driven V2 clock.

    The ATM window is piecewise constant within each Coinbase minute.  At every
    minute boundary the new causal BTC row is used first to recompute the
    window.  Between boundaries, only best-level changes of markets in that
    current window create entry decisions.  Segment starts count as an
    availability/top-of-book transition.  Deep-book-only changes do not.
    """
    index = (
        btc_rows_or_index
        if isinstance(btc_rows_or_index, Mapping)
        else materialization_index(btc_rows_or_index)
    )
    lo, hi = scan_bounds_ms(event_ticker)

    minute_boundaries = list(range(lo, hi + 1, 60000))
    times: set[int] = set(minute_boundaries)
    times.add(lo)
    times.add(hi)

    for interval_start in minute_boundaries:
        if interval_start >= hi:
            break

        btc = btc_row_for_decision(
            index,
            event_ticker=event_ticker,
            decision_timestamp_ms=interval_start,
        )
        if btc is None:
            # Window cannot be known; remain fail-closed for this minute.
            continue

        interval_end = min(interval_start + 60000, hi)
        window = spot_window(
            event_ticker=event_ticker,
            btc_spot=btc.close_price,
            event_ladder=event_ladder,
        )

        for market in window:
            timeline = timelines.get(market.market_ticker)
            if timeline is None:
                _fail(f"timeline missing for dynamic market {market.market_ticker}")

            for segment in timeline.segments:
                start = max(interval_start, segment.start_timestamp_ms)
                end = min(interval_end, segment.end_timestamp_ms)
                if start > end:
                    continue

                # A verified segment becoming available is a causal top-of-book
                # availability transition.  Exact minute boundaries are already
                # present and will collapse in the set.
                if interval_start < start < interval_end:
                    times.add(start)

                first = segment.state_at(start)
                previous = _top_signature(first)

                for state in segment.states:
                    if not start < state.timestamp_ms < interval_end:
                        continue
                    signature = _top_signature(state)
                    if signature != previous:
                        times.add(state.timestamp_ms)
                        previous = signature

    return tuple(sorted(times))


def evaluate_market(
    *,
    market: WindowMarket,
    decision_timestamp_ms: int,
    event_close_timestamp_ms: int,
    timeline: VerifiedTickerTimeline,
    btc_row: ContinuousBtcRow,
) -> V2MarketEvaluation:
    ttc_ms = event_close_timestamp_ms - int(decision_timestamp_ms)
    ttc_bucket(ttc_ms)

    if timeline.ticker != market.market_ticker:
        _fail("timeline ticker does not match market")

    btc_age_ms = int(decision_timestamp_ms) - btc_row.minute_end_ms
    if btc_row.minute_end_ms > int(decision_timestamp_ms):
        _fail("future Coinbase state used")

    base = dict(
        event_ticker=market.event_ticker,
        market_ticker=market.market_ticker,
        strike=market.strike,
        strike_rank_zero_based=market.strike_rank_zero_based,
        atm_market_ticker=market.atm_market_ticker,
        atm_strike=market.atm_strike,
        atm_rank_zero_based=market.atm_rank_zero_based,
        rank_from_atm=market.rank_from_atm,
        historical_structural_role=market.historical_structural_role,
        market_domain_label=market.market_domain_label,
        decision_timestamp_ms=int(decision_timestamp_ms),
        decision_ttc_ms=ttc_ms,
        btc_spot=btc_row.close_price,
        btc_minute_start_ms=btc_row.minute_start_ms,
        btc_state_age_ms=btc_age_ms,
    )

    segment = timeline.unique_segment_for_interval(
        int(decision_timestamp_ms),
        int(decision_timestamp_ms),
    )
    if segment is None:
        return V2MarketEvaluation(
            **base,
            status="KALSHI_SOURCE_UNAVAILABLE",
            q_market=None,
            candidate_probability=None,
            decision_yes_bid=None,
            decision_yes_ask=None,
            sides=(),
        )

    state = segment.state_at(int(decision_timestamp_ms))
    try:
        bid, ask = best_yes_quote(state)
    except ExecutableConvergenceSimulatorError as exc:
        if str(exc) in {"two-sided YES book required", "crossed YES book"}:
            return V2MarketEvaluation(
                **base,
                status="INVALID_TWO_SIDED_BOOK",
                q_market=None,
                candidate_probability=None,
                decision_yes_bid=None,
                decision_yes_ask=None,
                sides=(),
            )
        raise

    q_market = (bid.price + ask.price) / Decimal(2)
    probability = candidate_e_probability(
        q_market=q_market,
        btc_spot=btc_row.close_price,
        strike=market.strike,
    )

    sides = []
    for side in ("YES", "NO"):
        purchase_levels = side_purchase_asks(state, side)
        if not purchase_levels:
            continue
        best = purchase_levels[0]
        fee = account_synthetic_fill(
            action="BUY",
            price=best.price,
            quantity=PLANNED_QUANTITY,
            accumulator_before=ZERO,
        ).net_fee
        fair = side_fair_probability(side, probability)
        sides.append(
            V2SideEvaluation(
                side=side,
                purchase_price=best.price,
                decision_level_quantity=best.quantity,
                depth_qualifies=best.quantity >= MIN_DEPTH,
                fair_probability=fair,
                entry_fee=fee,
                net_edge=fair - best.price - fee,
            )
        )

    return V2MarketEvaluation(
        **base,
        status="EVALUABLE",
        q_market=q_market,
        candidate_probability=probability,
        decision_yes_bid=bid.price,
        decision_yes_ask=ask.price,
        sides=tuple(sides),
    )


def signal_from_evaluation(
    evaluation: V2MarketEvaluation,
    side: V2SideEvaluation,
) -> V2Signal:
    if evaluation.status != "EVALUABLE":
        _fail("cannot create signal from unavailable evaluation")
    time_label, late = continuous_time_domain_label(evaluation.decision_ttc_ms)

    return V2Signal(
        event_ticker=evaluation.event_ticker,
        market_ticker=evaluation.market_ticker,
        strike=evaluation.strike,
        strike_rank_zero_based=evaluation.strike_rank_zero_based,
        atm_market_ticker=evaluation.atm_market_ticker,
        atm_strike=evaluation.atm_strike,
        atm_rank_zero_based=evaluation.atm_rank_zero_based,
        rank_from_atm=evaluation.rank_from_atm,
        historical_structural_role=evaluation.historical_structural_role,
        market_domain_label=evaluation.market_domain_label,
        decision_timestamp_ms=evaluation.decision_timestamp_ms,
        decision_ttc_ms=evaluation.decision_ttc_ms,
        ttc_bucket=ttc_bucket(evaluation.decision_ttc_ms),
        is_exact_original_anchor=exact_original_anchor(evaluation.decision_ttc_ms),
        continuous_time_domain_label=time_label,
        late_window_extrapolation=late,
        side=side.side,
        btc_spot=evaluation.btc_spot,
        btc_minute_start_ms=evaluation.btc_minute_start_ms,
        btc_state_age_ms=evaluation.btc_state_age_ms,
        q_market=evaluation.q_market,
        candidate_probability=evaluation.candidate_probability,
        side_fair_probability=side.fair_probability,
        decision_yes_bid=evaluation.decision_yes_bid,
        decision_yes_ask=evaluation.decision_yes_ask,
        decision_limit_price=side.purchase_price,
        decision_level_quantity=side.decision_level_quantity,
        signal_entry_fee=side.entry_fee,
        net_edge_per_contract=side.net_edge,
    )


def select_signal_at_timestamp(
    evaluations: Sequence[V2MarketEvaluation],
    *,
    threshold: Decimal,
) -> V2Signal | None:
    threshold = Decimal(str(threshold))
    if threshold not in THRESHOLDS:
        _fail("threshold outside frozen menu")

    candidates = [
        signal_from_evaluation(evaluation, side)
        for evaluation in evaluations
        if evaluation.status == "EVALUABLE"
        for side in evaluation.sides
        if side.depth_qualifies and side.net_edge >= threshold
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda signal: (
            -signal.net_edge_per_contract,
            signal.market_ticker,
            SIDE_ORDER[signal.side],
        )
    )
    return candidates[0]


def _parent_signal(signal: V2Signal) -> SignalCandidate:
    metadata_role = signal.historical_structural_role or NONSTRUCTURAL_DOMAIN_LABEL
    return SignalCandidate(
        event_ticker=signal.event_ticker,
        market_ticker=signal.market_ticker,
        structural_role=metadata_role,
        ttc_target_minutes=int(signal.decision_ttc_ms // 60000),
        decision_timestamp_ms=signal.decision_timestamp_ms,
        side=signal.side,
        candidate_probability=signal.candidate_probability,
        side_fair_probability=signal.side_fair_probability,
        q_market=signal.q_market,
        decision_yes_bid=signal.decision_yes_bid,
        decision_yes_ask=signal.decision_yes_ask,
        decision_limit_price=signal.decision_limit_price,
        signal_entry_fee=signal.signal_entry_fee,
        net_edge_per_contract=signal.net_edge_per_contract,
    )


def simulate_v2_entry(
    *,
    signal: V2Signal,
    timeline: VerifiedTickerTimeline,
    latency_ms: int,
) -> EntryAttempt:
    return simulate_entry(
        signal=_parent_signal(signal),
        timeline=timeline,
        latency_ms=latency_ms,
    )


def simulate_v2_liquidation(
    *,
    signal: V2Signal,
    entry: EntryAttempt,
    timeline: VerifiedTickerTimeline,
    event_close_timestamp_ms: int,
) -> LiquidationBranch | None:
    return simulate_liquidation_branch(
        signal=_parent_signal(signal),
        entry=entry,
        timeline=timeline,
        event_close_timestamp_ms=event_close_timestamp_ms,
    )


def _closed_cash_change(
    entry: EntryAttempt,
    liquidation: LiquidationBranch | None,
) -> Decimal | None:
    if (
        not entry.source_available
        or entry.ioc is None
        or entry.ioc.filled_quantity <= ZERO
        or liquidation is None
        or liquidation.status != "EXIT_FULL"
        or liquidation.exit_ioc is None
        or liquidation.exit_ioc.status != "FULL"
        or liquidation.settlement_fallback_quantity != ZERO
    ):
        return None
    return (
        entry.ioc.net_cash_change_total
        + liquidation.exit_ioc.net_cash_change_total
    )


def _evaluate_event_at_timestamp(
    *,
    event_ticker: str,
    event_ladder: Sequence[LadderMarket],
    timelines: Mapping[str, VerifiedTickerTimeline],
    btc_index: Mapping[tuple[str, int], ContinuousBtcRow],
    decision_timestamp_ms: int,
    event_close_timestamp_ms: int,
) -> tuple[tuple[V2MarketEvaluation, ...], tuple[WindowMarket, ...], bool]:
    btc = btc_row_for_decision(
        btc_index,
        event_ticker=event_ticker,
        decision_timestamp_ms=decision_timestamp_ms,
    )
    if btc is None:
        return (), (), False

    window = spot_window(
        event_ticker=event_ticker,
        btc_spot=btc.close_price,
        event_ladder=event_ladder,
    )

    evaluations = []
    for market in window:
        timeline = timelines.get(market.market_ticker)
        if timeline is None:
            _fail(f"timeline missing for current window market {market.market_ticker}")
        evaluations.append(
            evaluate_market(
                market=market,
                decision_timestamp_ms=decision_timestamp_ms,
                event_close_timestamp_ms=event_close_timestamp_ms,
                timeline=timeline,
                btc_row=btc,
            )
        )
    return tuple(evaluations), window, True


def _rearmed(
    *,
    evaluations: Sequence[V2MarketEvaluation],
    current_window: Sequence[WindowMarket],
    btc_available: bool,
    reference: V2Signal,
    threshold: Decimal,
) -> tuple[bool, str | None]:
    if not btc_available:
        return False, None

    window_tickers = {market.market_ticker for market in current_window}
    if reference.market_ticker not in window_tickers:
        return True, "REFERENCE_LEFT_SPOT_WINDOW"

    matches = [
        evaluation
        for evaluation in evaluations
        if evaluation.market_ticker == reference.market_ticker
    ]
    if len(matches) != 1:
        _fail("reference market is inside window but evaluation is missing")

    evaluation = matches[0]
    if evaluation.status != "EVALUABLE":
        return False, None

    sides = [side for side in evaluation.sides if side.side == reference.side]
    if len(sides) != 1:
        _fail("reference side missing from evaluable market")
    side = sides[0]

    if not side.depth_qualifies:
        return True, "REFERENCE_DEPTH_BELOW_ONE_CONTRACT"
    if side.net_edge < threshold:
        return True, "REFERENCE_EDGE_BELOW_THRESHOLD"
    return False, None


def simulate_policy(
    *,
    event_ticker: str,
    event_ladder: Sequence[LadderMarket],
    timelines: Mapping[str, VerifiedTickerTimeline],
    btc_rows: Sequence[ContinuousBtcRow],
    threshold: Decimal,
    latency_ms: int,
) -> V2PolicyResult:
    threshold = Decimal(str(threshold))
    if threshold not in THRESHOLDS:
        _fail("threshold outside frozen menu")
    if latency_ms not in LATENCY_MS:
        _fail("latency outside frozen scenarios")

    event_close_ms = epoch_ms(parse_utc(EVENT_CLOSE_UTC[event_ticker]))
    btc_index = materialization_index(btc_rows)

    clock = decision_clock(
        event_ticker=event_ticker,
        event_ladder=event_ladder,
        timelines=timelines,
        btc_rows_or_index=btc_index,
    )

    mode = "ARMED_FIRST"
    block_through_ms = -1
    attempts: list[V2EntryAttemptRecord] = []
    trades: list[V2TradePath] = []
    rearm: V2RearmRecord | None = None
    reference: V2Signal | None = None

    for timestamp_ms in clock:
        if timestamp_ms <= block_through_ms:
            continue

        evaluations, current_window, btc_available = _evaluate_event_at_timestamp(
            event_ticker=event_ticker,
            event_ladder=event_ladder,
            timelines=timelines,
            btc_index=btc_index,
            decision_timestamp_ms=timestamp_ms,
            event_close_timestamp_ms=event_close_ms,
        )

        if mode == "WAIT_REARM":
            if reference is None:
                _fail("WAIT_REARM missing reference signal")
            yes, reason = _rearmed(
                evaluations=evaluations,
                current_window=current_window,
                btc_available=btc_available,
                reference=reference,
                threshold=threshold,
            )
            if yes:
                rearm = V2RearmRecord(
                    reference_market_ticker=reference.market_ticker,
                    reference_side=reference.side,
                    rearm_timestamp_ms=timestamp_ms,
                    reason=str(reason),
                )
                mode = "ARMED_SECOND"
                block_through_ms = timestamp_ms
            continue

        if mode not in {"ARMED_FIRST", "ARMED_SECOND"}:
            break

        if not btc_available:
            continue

        signal = select_signal_at_timestamp(
            evaluations,
            threshold=threshold,
        )
        if signal is None:
            continue

        trade_number = 1 if mode == "ARMED_FIRST" else 2
        entry = simulate_v2_entry(
            signal=signal,
            timeline=timelines[signal.market_ticker],
            latency_ms=latency_ms,
        )
        attempts.append(
            V2EntryAttemptRecord(
                trade_number=trade_number,
                signal=signal,
                latency_ms=latency_ms,
                entry=entry,
            )
        )
        block_through_ms = entry.arrival_timestamp_ms

        if (
            not entry.source_available
            or entry.ioc is None
            or entry.ioc.filled_quantity == ZERO
        ):
            continue

        liquidation = simulate_v2_liquidation(
            signal=signal,
            entry=entry,
            timeline=timelines[signal.market_ticker],
            event_close_timestamp_ms=event_close_ms,
        )
        trades.append(
            V2TradePath(
                trade_number=trade_number,
                signal=signal,
                latency_ms=latency_ms,
                entry=entry,
                liquidation=liquidation,
                fully_closed_round_trip_cash_change=_closed_cash_change(
                    entry,
                    liquidation,
                ),
                matched_hold_settlement_quantity=entry.ioc.filled_quantity,
            )
        )

        if trade_number == 2:
            mode = "DONE_MAX_TWO_FILLED_ENTRIES"
            break

        reference = signal
        if (
            liquidation is not None
            and liquidation.status == "EXIT_FULL"
            and liquidation.exit_ioc is not None
            and liquidation.exit_ioc.status == "FULL"
            and liquidation.settlement_fallback_quantity == ZERO
            and liquidation.exit_arrival_timestamp_ms is not None
        ):
            mode = "WAIT_REARM"
            block_through_ms = liquidation.exit_arrival_timestamp_ms
        else:
            mode = "DONE_FIRST_POSITION_NOT_FULLY_EXITED"
            break

    terminal = (
        "NO_FILLED_ENTRY"
        if mode == "ARMED_FIRST"
        else "FIRST_TRADE_FULLY_EXITED_NO_REARM"
        if mode == "WAIT_REARM"
        else "REARMED_NO_SECOND_FILLED_ENTRY"
        if mode == "ARMED_SECOND"
        else mode
    )

    return V2PolicyResult(
        event_ticker=event_ticker,
        threshold=threshold,
        latency_ms=latency_ms,
        decision_clock_count=len(clock),
        entry_attempts=tuple(attempts),
        trades=tuple(trades),
        rearm=rearm,
        terminal_state=terminal,
    )


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    return value


FORBIDDEN_OUTPUT_KEYS = {
    "outcome",
    "outcomes",
    "winner",
    "settlement_value",
    "settlement_outcome",
    "realized_pnl",
    "pnl",
    "profit",
    "loss",
}


def assert_outcome_blind_payload(payload: Mapping[str, Any]) -> None:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_OUTPUT_KEYS:
                    found.add(str(key).lower())
                walk(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                walk(item)

    walk(payload)
    if found:
        _fail(f"forbidden settlement/economic keys in outcome-blind payload: {sorted(found)}")

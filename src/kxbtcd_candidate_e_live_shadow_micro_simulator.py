"""Read-only live-shadow simulation of the frozen V2 micro-probe economics.

The simulator consumes typed snapshots from the one-way collector feed. It
never creates an order intent or talks to Kalshi. Every live scenario is an
independent edge-threshold counterfactual over the same observed shadow path;
latency stress remains an offline-only sensitivity analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from .kxbtcd_candidate_e_dashboard_shadow_projection import (
    EXACT_OBSERVED_DEPTH_IOC,
    SHADOW_EVENT_SCHEMA_VERSION,
)
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    PRICE_QUANTUM,
    account_synthetic_fill,
    side_purchase_asks,
    side_sale_bids,
    simulate_ioc,
)
from .kxbtcd_candidate_e_live_shadow_snapshot_reader import LiveShadowCausalState
from .kxbtcd_candidate_e_shadow_causal_join import CausalShadowBookPoint
from .kxbtcd_candidate_e_shadow_coinbase_candle_replay import ReconstructedCoinbaseCandle
from .kxbtcd_candidate_e_shadow_kalshi_replay import ReconstructedKalshiBook
from .kxbtcd_candidate_e_shadow_v2_evaluator import evaluate_causal_v2_market
from .kxbtcd_candidate_e_shadow_v2_scenarios import (
    PRIMARY_SHADOW_V2_SCENARIO,
    ShadowV2Scenario,
)
from .kxbtcd_candidate_e_shadow_v2_selection import (
    select_candidates,
    select_frozen_primary_candidates,
)
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    STRUCTURAL_DOMAIN_LABEL,
    NONSTRUCTURAL_DOMAIN_LABEL,
    WindowMarket,
    spot_window,
)


class LiveShadowMicroSimulatorError(ValueError):
    pass


SIMULATED_ENTRY_BUDGET_DOLLARS = Decimal("100.00")
QUANTITY_QUANTUM = Decimal("0.01")
MAXIMUM_ENTRY_ATTEMPTS = 5
MAXIMUM_FILLED_ENTRIES_PER_EVENT = 2
ENTRY_WINDOW_START_MS = 55 * 60 * 1000
ENTRY_WINDOW_END_MS = 10 * 60 * 1000
MOVING_ATM_ELEVEN = "moving_atm_eleven"
FROZEN_ATM_FIVE = "frozen_atm_five"
FROZEN_ATM_ONE = "frozen_atm_one"
MARKET_UNIVERSES = frozenset({MOVING_ATM_ELEVEN, FROZEN_ATM_FIVE, FROZEN_ATM_ONE})
FROZEN_ATM_UNIVERSES = frozenset({FROZEN_ATM_FIVE, FROZEN_ATM_ONE})
STOP_LOSS_FRACTIONS = frozenset({
    Decimal("0.10"), Decimal("0.20"), Decimal("0.30"), Decimal("0.40"), Decimal("0.50"),
})
PROFIT_TARGET_MULTIPLIERS = frozenset({
    Decimal("1.00"), Decimal("1.50"), Decimal("2.00"),
})
DURATION_CAP_MINUTES = frozenset({
    Decimal("15"), Decimal("20"), Decimal("25"),
})
TRAILING_ACTIVATION_MARGINS = frozenset({
    Decimal("0.02"), Decimal("0.05"), Decimal("0.08"),
})
TRAILING_GIVE_BACK_FRACTION = Decimal("0.50")
MINIMUM_PARTIAL_FILL_FRACTION = Decimal("0.25")
NS_PER_MINUTE = 60 * 1_000_000_000


@dataclass(frozen=True)
class LiveShadowDecisionDiagnostics:
    """Bounded per-run explanation of snapshots that did not create an entry."""
    snapshots_evaluated: int = 0
    outside_entry_window: int = 0
    no_evaluable_market: int = 0
    insufficient_visible_depth: int = 0
    edge_below_threshold: int = 0
    eligible_candidate_selected: int = 0
    position_open: int = 0
    event_or_reentry_state: int = 0
    max_yes_net_edge: Decimal | None = None
    max_no_net_edge: Decimal | None = None
    closest_net_edge_deficit: Decimal | None = None

    def observe(
        self, *, reason: str, threshold: Decimal,
        max_yes_net_edge: Decimal | None = None,
        max_no_net_edge: Decimal | None = None,
    ) -> "LiveShadowDecisionDiagnostics":
        if reason not in {
            "OUTSIDE_ENTRY_WINDOW", "NO_EVALUABLE_MARKET",
            "INSUFFICIENT_VISIBLE_DEPTH", "EDGE_BELOW_THRESHOLD",
            "ELIGIBLE_CANDIDATE_SELECTED", "POSITION_OPEN", "EVENT_OR_REENTRY_STATE",
        }:
            raise LiveShadowMicroSimulatorError("decision diagnostic reason is invalid")
        values = {
            "snapshots_evaluated": self.snapshots_evaluated + 1,
            "max_yes_net_edge": _maximum(self.max_yes_net_edge, max_yes_net_edge),
            "max_no_net_edge": _maximum(self.max_no_net_edge, max_no_net_edge),
        }
        if reason == "EDGE_BELOW_THRESHOLD":
            best = _maximum(max_yes_net_edge, max_no_net_edge)
            if best is not None:
                values["closest_net_edge_deficit"] = _minimum(
                    self.closest_net_edge_deficit, threshold - best
                )
        key = {
            "OUTSIDE_ENTRY_WINDOW": "outside_entry_window",
            "NO_EVALUABLE_MARKET": "no_evaluable_market",
            "INSUFFICIENT_VISIBLE_DEPTH": "insufficient_visible_depth",
            "EDGE_BELOW_THRESHOLD": "edge_below_threshold",
            "ELIGIBLE_CANDIDATE_SELECTED": "eligible_candidate_selected",
            "POSITION_OPEN": "position_open",
            "EVENT_OR_REENTRY_STATE": "event_or_reentry_state",
        }[reason]
        values[key] = getattr(self, key) + 1
        return replace(self, **values)


def _maximum(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return right if left is None else left if right is None else max(left, right)


def _minimum(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return right if left is None else left if right is None else min(left, right)


@dataclass(frozen=True)
class LiveShadowPendingSettlement:
    event_ticker: str
    position_id: str
    market_ticker: str
    side: str
    remaining_quantity: Decimal
    entry_cost: Decimal
    required_total_net_proceeds: Decimal

    @classmethod
    def from_open_state(cls, state: "LiveShadowMicroState") -> "LiveShadowPendingSettlement":
        if (
            not state.event_ticker or not state.position_id or not state.market_ticker
            or state.side not in {"YES", "NO"} or state.remaining_quantity <= 0
            or state.required_total_net_proceeds is None
        ):
            raise LiveShadowMicroSimulatorError("open shadow position cannot await settlement")
        return cls(
            state.event_ticker, state.position_id, state.market_ticker, state.side,
            state.remaining_quantity, state.entry_cost, state.required_total_net_proceeds,
        )


@dataclass(frozen=True)
class LiveShadowMicroState:
    event_ticker: str | None
    position_id: str | None
    market_ticker: str | None
    side: str | None
    remaining_quantity: Decimal
    entry_cost: Decimal
    required_total_net_proceeds: Decimal | None
    entry_attempts: int
    closed_event_tickers: frozenset[str]
    filled_entry_count: int = 0
    reentry_reference_market_ticker: str | None = None
    reentry_reference_side: str | None = None
    reentry_not_before_snapshot_sequence: int = 0
    pending_settlements: tuple[LiveShadowPendingSettlement, ...] = ()
    decision_diagnostics: LiveShadowDecisionDiagnostics = field(
        default_factory=LiveShadowDecisionDiagnostics, compare=False
    )
    market_universe: str = MOVING_ATM_ELEVEN
    frozen_atm_event_ticker: str | None = None
    frozen_atm_market_tickers: tuple[str, ...] = ()
    stop_loss_fraction: Decimal | None = None
    profit_target_multiplier: Decimal = Decimal("1.00")
    duration_cap_minutes: Decimal | None = None
    trailing_activation_margin: Decimal | None = None
    entered_monotonic_ns: int | None = None
    peak_favorable_price: Decimal | None = None

    @classmethod
    def new(cls) -> "LiveShadowMicroState":
        return cls(None, None, None, None, Decimal("0"), Decimal("0"), None, 0, frozenset())


@dataclass(frozen=True)
class LiveShadowMicroStep:
    state: LiveShadowMicroState
    events: tuple[dict[str, object], ...]


def _event(
    state: LiveShadowCausalState,
    sequence: int,
    event_type: str,
    *,
    scenario: ShadowV2Scenario,
    **fields,
) -> dict[str, object]:
    return {
        "schema_version": SHADOW_EVENT_SCHEMA_VERSION,
        "run_id": state.run_id,
        "scenario_id": scenario.scenario_id,
        "scenario_edge_threshold": format(scenario.edge_threshold, "f"),
        "scenario_is_primary": scenario.is_primary,
        "execution_timing_basis": scenario.execution_timing_basis,
        "event_sequence": sequence,
        "input_snapshot_sequence": state.snapshot_sequence,
        "snapshot_generated_utc": state.generated_utc,
        "event_type": event_type,
        **fields,
    }


def _point(state: LiveShadowCausalState, ticker: str) -> CausalShadowBookPoint:
    candle = state.candle.minute
    return CausalShadowBookPoint(
        book=ReconstructedKalshiBook(
            ticker, state.generated_utc, state.generated_monotonic_ns, state.books[ticker],
        ),
        completed_candle=ReconstructedCoinbaseCandle(
            candle.minute_start_s,
            candle.close_price,
            candle.raw_received_utc,
            candle.available_monotonic_ns,
        ),
    )


def _entry_window_open(state: LiveShadowCausalState) -> bool:
    """Return whether this snapshot may create a new frozen-V2 entry.

    The frozen evaluator permits points through T-2. Live shadow deliberately
    uses the more conservative T-55 through T-10 subset so an entry cannot
    begin during the late, rapidly changing part of the event. In a live
    sidecar points outside that subset are expected, rather than corrupt:
    quietly defer entry evaluation until the window opens.
    Existing positions follow the separate exit branch in ``_advance``.
    """
    decision = datetime.fromisoformat(state.generated_utc.replace("Z", "+00:00"))
    if decision.tzinfo is None:
        raise LiveShadowMicroSimulatorError("snapshot UTC lacks timezone")
    decision_ms = int(decision.astimezone(timezone.utc).timestamp() * 1000)
    ttc_ms = state.event_ladder.close_timestamp_ms - decision_ms
    return ENTRY_WINDOW_END_MS <= ttc_ms <= ENTRY_WINDOW_START_MS


def _frozen_atm_window(
    state: LiveShadowCausalState, *, count: int,
) -> tuple[WindowMarket, ...]:
    """Freeze the nearest ``count`` strikes at first usable snapshot for an event."""
    ordered = tuple(sorted(state.event_ladder.markets, key=lambda item: item.strike_rank_zero_based))
    if count not in {1, 5} or len(ordered) < count:
        raise LiveShadowMicroSimulatorError("frozen ATM challenger requires a complete ladder")
    spot = state.candle.minute.close_price
    atm = min(ordered, key=lambda market: (
        abs(market.strike - spot), market.strike, market.market_ticker,
    ))
    start = min(max(0, atm.strike_rank_zero_based - count // 2), len(ordered) - count)
    selected = ordered[start : start + count]
    return tuple(
        WindowMarket(
            event_ticker=state.event_ladder.event_ticker,
            market_ticker=market.market_ticker,
            strike=market.strike,
            strike_rank_zero_based=market.strike_rank_zero_based,
            event_market_count=market.event_market_count,
            atm_market_ticker=atm.market_ticker,
            atm_strike=atm.strike,
            atm_rank_zero_based=atm.strike_rank_zero_based,
            rank_from_atm=market.strike_rank_zero_based - atm.strike_rank_zero_based,
            historical_structural_role=market.historical_structural_role,
            market_domain_label=(STRUCTURAL_DOMAIN_LABEL if market.historical_structural_role
                                 else NONSTRUCTURAL_DOMAIN_LABEL),
        )
        for market in selected
    )


def _prepare_market_universe(
    prior: LiveShadowMicroState, snapshot: LiveShadowCausalState, market_universe: str,
) -> LiveShadowMicroState:
    if market_universe not in MARKET_UNIVERSES:
        raise LiveShadowMicroSimulatorError("live-shadow market universe is invalid")
    untouched = prior.event_ticker is None and prior.position_id is None and prior.entry_attempts == 0
    if not untouched and prior.market_universe != market_universe:
        raise LiveShadowMicroSimulatorError("live-shadow market universe changed within a run")
    if market_universe not in FROZEN_ATM_UNIVERSES:
        return replace(prior, market_universe=market_universe)
    if prior.frozen_atm_event_ticker == snapshot.event_ladder.event_ticker:
        return replace(prior, market_universe=market_universe)
    window = _frozen_atm_window(
        snapshot, count=5 if market_universe == FROZEN_ATM_FIVE else 1,
    )
    return replace(
        prior,
        market_universe=market_universe,
        frozen_atm_event_ticker=snapshot.event_ladder.event_ticker,
        frozen_atm_market_tickers=tuple(item.market_ticker for item in window),
    )


def _prepare_stop_loss(
    prior: LiveShadowMicroState, stop_loss_fraction: Decimal | None,
) -> LiveShadowMicroState:
    """Bind an optional dynamic executable-loss limit for this lane.

    A configured stop is evaluated afresh at every snapshot.  It is deliberately
    not latched: a transient adverse book that cannot be exited is allowed to
    recover before a later snapshot is considered.
    """
    if stop_loss_fraction is not None and stop_loss_fraction not in STOP_LOSS_FRACTIONS:
        raise LiveShadowMicroSimulatorError("live-shadow stop loss is invalid")
    untouched = prior.event_ticker is None and prior.position_id is None and prior.entry_attempts == 0
    if not untouched and prior.stop_loss_fraction != stop_loss_fraction:
        raise LiveShadowMicroSimulatorError("live-shadow stop loss changed within a run")
    return replace(prior, stop_loss_fraction=stop_loss_fraction)


def _prepare_profit_target(
    prior: LiveShadowMicroState, profit_target_multiplier: Decimal,
) -> LiveShadowMicroState:
    """Bind the retained net-edge multiple for this lane."""
    if profit_target_multiplier not in PROFIT_TARGET_MULTIPLIERS:
        raise LiveShadowMicroSimulatorError("live-shadow profit target is invalid")
    untouched = prior.event_ticker is None and prior.position_id is None and prior.entry_attempts == 0
    if not untouched and prior.profit_target_multiplier != profit_target_multiplier:
        raise LiveShadowMicroSimulatorError("live-shadow profit target changed within a run")
    return replace(prior, profit_target_multiplier=profit_target_multiplier)


def _prepare_duration_cap(
    prior: LiveShadowMicroState, duration_cap_minutes: Decimal | None,
) -> LiveShadowMicroState:
    """Bind an optional maximum hold duration for this lane.

    Past this many minutes since entry, an exit attempt accepts a partial
    fill rather than requiring the full remaining quantity to clear.
    """
    if duration_cap_minutes is not None and duration_cap_minutes not in DURATION_CAP_MINUTES:
        raise LiveShadowMicroSimulatorError("live-shadow duration cap is invalid")
    untouched = prior.event_ticker is None and prior.position_id is None and prior.entry_attempts == 0
    if not untouched and prior.duration_cap_minutes != duration_cap_minutes:
        raise LiveShadowMicroSimulatorError("live-shadow duration cap changed within a run")
    return replace(prior, duration_cap_minutes=duration_cap_minutes)


def _prepare_trailing_lock(
    prior: LiveShadowMicroState, trailing_activation_margin: Decimal | None,
) -> LiveShadowMicroState:
    """Bind an optional trailing profit lock for this lane.

    Once the position has traded at least this far above entry, it starts
    tracking its own running peak; a later pullback of more than
    ``TRAILING_GIVE_BACK_FRACTION`` of the peak gain accepts a partial exit
    rather than waiting for the full profit target. A position that climbs
    straight to its target never triggers this, since the peak keeps pace.
    """
    if (
        trailing_activation_margin is not None
        and trailing_activation_margin not in TRAILING_ACTIVATION_MARGINS
    ):
        raise LiveShadowMicroSimulatorError("live-shadow trailing activation margin is invalid")
    untouched = prior.event_ticker is None and prior.position_id is None and prior.entry_attempts == 0
    if not untouched and prior.trailing_activation_margin != trailing_activation_margin:
        raise LiveShadowMicroSimulatorError("live-shadow trailing activation margin changed within a run")
    return replace(prior, trailing_activation_margin=trailing_activation_margin)


def _frozen_window_from_state(
    state: LiveShadowCausalState, prior: LiveShadowMicroState,
) -> tuple[WindowMarket, ...]:
    if prior.frozen_atm_event_ticker != state.event_ladder.event_ticker:
        raise LiveShadowMicroSimulatorError("frozen ATM event selection is missing")
    frozen = tuple(prior.frozen_atm_market_tickers)
    ordered = tuple(sorted(state.event_ladder.markets, key=lambda item: item.strike_rank_zero_based))
    by_ticker = {item.market_ticker: item for item in ordered}
    expected_count = 5 if prior.market_universe == FROZEN_ATM_FIVE else 1
    if (len(frozen) != expected_count or len(set(frozen)) != expected_count
            or any(ticker not in by_ticker for ticker in frozen)):
        raise LiveShadowMicroSimulatorError("frozen ATM ladder is incomplete")
    center = by_ticker[frozen[len(frozen) // 2]]
    return tuple(
        WindowMarket(
            event_ticker=state.event_ladder.event_ticker,
            market_ticker=by_ticker[ticker].market_ticker,
            strike=by_ticker[ticker].strike,
            strike_rank_zero_based=by_ticker[ticker].strike_rank_zero_based,
            event_market_count=by_ticker[ticker].event_market_count,
            atm_market_ticker=center.market_ticker,
            atm_strike=center.strike,
            atm_rank_zero_based=center.strike_rank_zero_based,
            rank_from_atm=by_ticker[ticker].strike_rank_zero_based - center.strike_rank_zero_based,
            historical_structural_role=by_ticker[ticker].historical_structural_role,
            market_domain_label=(STRUCTURAL_DOMAIN_LABEL if by_ticker[ticker].historical_structural_role
                                 else NONSTRUCTURAL_DOMAIN_LABEL),
        )
        for ticker in frozen
    )


def _evaluations(state: LiveShadowCausalState, prior: LiveShadowMicroState | None = None):
    if prior is not None and prior.market_universe in FROZEN_ATM_UNIVERSES:
        window = _frozen_window_from_state(state, prior)
    else:
        window = spot_window(
            event_ticker=state.event_ladder.event_ticker,
            btc_spot=state.candle.minute.close_price,
            event_ladder=state.event_ladder.markets,
        )
    return tuple(
        evaluate_causal_v2_market(
            event_ladder=state.event_ladder,
            point=_point(state, market.market_ticker),
            selected_market=market,
        )
        for market in window
    )


def _evaluations_for_state(
    state: LiveShadowCausalState, prior: LiveShadowMicroState,
):
    """Keep the accepted moving-universe callable seam stable for tests."""
    return (
        _evaluations(state, prior)
        if prior.market_universe in FROZEN_ATM_UNIVERSES
        else _evaluations(state)
    )


def _selected_candidate(state: LiveShadowCausalState, prior: LiveShadowMicroState | None = None):
    """Compatibility selector for the frozen $0.02 primary policy."""
    candidates = select_frozen_primary_candidates(
        _evaluations(state) if prior is None else _evaluations_for_state(state, prior)
    )
    return candidates[0] if candidates else None


def _selected_candidate_for_scenario(
    state: LiveShadowCausalState,
    scenario: ShadowV2Scenario,
    prior: LiveShadowMicroState | None = None,
):
    candidates = select_candidates(
        _evaluations(state) if prior is None else _evaluations_for_state(state, prior),
        net_edge_threshold=scenario.edge_threshold,
    )
    return candidates[0] if candidates else None


def _decision_diagnostics_after_snapshot(
    *, prior: LiveShadowMicroState, snapshot: LiveShadowCausalState,
    scenario: ShadowV2Scenario, selected_candidate: bool,
) -> LiveShadowDecisionDiagnostics:
    """Classify one processed snapshot without changing selection behaviour."""
    diagnostics = prior.decision_diagnostics
    if snapshot.snapshot_sequence <= prior.reentry_not_before_snapshot_sequence:
        return diagnostics
    if prior.remaining_quantity > 0:
        return diagnostics.observe(reason="POSITION_OPEN", threshold=scenario.edge_threshold)
    if (
        prior.event_ticker not in {None, snapshot.event_ladder.event_ticker}
        or snapshot.event_ladder.event_ticker in prior.closed_event_tickers
        or prior.reentry_reference_market_ticker is not None
    ):
        return diagnostics.observe(reason="EVENT_OR_REENTRY_STATE", threshold=scenario.edge_threshold)
    if not _entry_window_open(snapshot):
        return diagnostics.observe(reason="OUTSIDE_ENTRY_WINDOW", threshold=scenario.edge_threshold)

    evaluations = _evaluations_for_state(snapshot, prior)
    evaluable = tuple(item for item in evaluations if item.status == "EVALUABLE")
    if not evaluable:
        return diagnostics.observe(reason="NO_EVALUABLE_MARKET", threshold=scenario.edge_threshold)
    qualifying_sides = tuple(
        side for item in evaluable for side in item.sides if side.depth_qualifies
    )
    if not qualifying_sides:
        return diagnostics.observe(reason="INSUFFICIENT_VISIBLE_DEPTH", threshold=scenario.edge_threshold)
    max_yes = max(
        (side.net_edge for side in qualifying_sides if side.side == "YES"), default=None
    )
    max_no = max(
        (side.net_edge for side in qualifying_sides if side.side == "NO"), default=None
    )
    if selected_candidate:
        return diagnostics.observe(
            reason="ELIGIBLE_CANDIDATE_SELECTED", threshold=scenario.edge_threshold,
            max_yes_net_edge=max_yes, max_no_net_edge=max_no,
        )
    return diagnostics.observe(
        reason="EDGE_BELOW_THRESHOLD", threshold=scenario.edge_threshold,
        max_yes_net_edge=max_yes, max_no_net_edge=max_no,
    )


def _fill_events(
    *,
    state: LiveShadowCausalState,
    scenario: ShadowV2Scenario,
    sequence: int,
    position_id: str,
    market_ticker: str,
    side: str,
    action: str,
    fills,
) -> tuple[dict[str, object], ...]:
    emitted = []
    for fill in fills:
        emitted.append(_event(
            state,
            sequence + len(emitted),
            "shadow_simulated_fill",
            scenario=scenario,
            position_id=position_id,
            market_ticker=market_ticker,
            side="buy" if action == "BUY" else "sell",
            simulated_quantity=format(fill.quantity, "f"),
            simulated_price=format(fill.price, "f"),
            simulated_fee=format(fill.net_fee, "f"),
            fill_assumption=EXACT_OBSERVED_DEPTH_IOC,
            observed_book_received_utc=state.generated_utc,
        ))
    return tuple(emitted)


def _largest_budgeted_entry(*, levels, limit_price: Decimal):
    available_quantity = sum(
        (level.quantity for level in levels if level.price <= limit_price),
        Decimal("0"),
    )
    low, high = 1, int(available_quantity / QUANTITY_QUANTUM)
    best = None
    while low <= high:
        midpoint = (low + high) // 2
        result = simulate_ioc(
            action="BUY",
            levels=levels,
            limit_price=limit_price,
            requested_quantity=QUANTITY_QUANTUM * midpoint,
        )
        if (
            result.status == "FULL"
            and -result.net_cash_change_total <= SIMULATED_ENTRY_BUDGET_DOLLARS
        ):
            best = result
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


def _best_probability(levels, *, purchase: bool) -> Decimal | None:
    """Return the best currently displayed probability for the requested side."""
    prices = tuple(level.price for level in levels)
    if not prices:
        return None
    return min(prices) if purchase else max(prices)


@lru_cache(maxsize=128)
def _hypothetical_resting_exit_limit(
    required_total_net_proceeds: Decimal,
    quantity: Decimal,
) -> Decimal | None:
    """Lowest one-price sell limit that meets the retained cash target.

    This is an accounting-only reference point.  The shadow simulator never
    submits a resting order and never infers that an order at this price would
    fill; it exists solely to make the retained exit requirement legible in
    the dashboard.
    """
    ticks = int(Decimal("1") / PRICE_QUANTUM)
    for tick in range(ticks + 1):
        price = PRICE_QUANTUM * tick
        accounting = account_synthetic_fill(
            action="SELL",
            price=price,
            quantity=quantity,
        )
        if accounting.net_cash_change >= required_total_net_proceeds:
            return price
    return None


def _resting_exit_reference(prior: LiveShadowMicroState) -> str | None:
    price = _hypothetical_resting_exit_limit(
        prior.required_total_net_proceeds,
        prior.remaining_quantity,
    )
    return None if price is None else format(price, "f")


def _reentry_rearm_reason(
    snapshot: LiveShadowCausalState,
    prior: LiveShadowMicroState,
    scenario: ShadowV2Scenario,
) -> str | None:
    """Return the frozen V2 re-arm proof for a fully exited first position."""
    reference_ticker = prior.reentry_reference_market_ticker
    reference_side = prior.reentry_reference_side
    if not reference_ticker or reference_side not in {"YES", "NO"}:
        raise LiveShadowMicroSimulatorError("re-entry reference is invalid")
    # A completed first exit can occur after the conservative live entry window
    # has closed.  That is an ordinary no-reentry condition, not a corrupt
    # frozen-evaluator input: the evaluator itself permits a wider T-55 to T-2
    # window and raises outside it.
    if not _entry_window_open(snapshot):
        return None
    evaluations = _evaluations_for_state(snapshot, prior)
    matching = [item for item in evaluations if item.market_ticker == reference_ticker]
    if not matching:
        return "REFERENCE_LEFT_SPOT_WINDOW"
    if len(matching) != 1 or matching[0].status != "EVALUABLE":
        return None
    sides = [item for item in matching[0].sides if item.side == reference_side]
    if len(sides) != 1:
        raise LiveShadowMicroSimulatorError("re-entry reference side is unavailable")
    reference = sides[0]
    if not reference.depth_qualifies:
        return "REFERENCE_DEPTH_BELOW_ONE_CONTRACT"
    if reference.net_edge < scenario.edge_threshold:
        return "REFERENCE_EDGE_BELOW_THRESHOLD"
    return None


def _advance(
    *,
    prior: LiveShadowMicroState,
    snapshot: LiveShadowCausalState,
    first_event_sequence: int,
    scenario: ShadowV2Scenario,
    candidate_resolver,
    market_universe: str,
) -> LiveShadowMicroStep:
    if first_event_sequence < 1:
        raise LiveShadowMicroSimulatorError("first event sequence must be positive")
    if (
        prior.remaining_quantity < 0 or prior.entry_cost < 0
        or prior.filled_entry_count < 0
        or prior.filled_entry_count > MAXIMUM_FILLED_ENTRIES_PER_EVENT
    ):
        raise LiveShadowMicroSimulatorError("prior simulated state is invalid")

    event_ticker = snapshot.event_ladder.event_ticker
    sequence = first_event_sequence
    emitted: list[dict[str, object]] = []

    if prior.remaining_quantity > 0 and prior.event_ticker != event_ticker:
        emitted.append(_event(
            snapshot, sequence, "shadow_position_awaiting_official_settlement",
            scenario=scenario, position_id=prior.position_id,
            market_ticker=prior.market_ticker,
        ))
        sequence += 1
        prior = LiveShadowMicroState(
            None, None, None, None, Decimal("0"), Decimal("0"), None, 0,
            frozenset(), pending_settlements=(
                *prior.pending_settlements,
                LiveShadowPendingSettlement.from_open_state(prior),
            ),
        )

    if prior.remaining_quantity > 0:
        if prior.market_ticker not in snapshot.books:
            emitted.append(_event(
                snapshot,
                sequence,
                "shadow_no_fill",
                scenario=scenario,
                position_id=prior.position_id,
                reason="OPEN_POSITION_MARKET_NOT_IN_CURRENT_COMPLETE_LADDER",
            ))
            return LiveShadowMicroStep(prior, tuple(emitted))
        exit_levels = side_sale_bids(snapshot.books[prior.market_ticker], prior.side)
        observed_best_bid = _best_probability(exit_levels, purchase=False)
        hypothetical_resting_exit_limit = _resting_exit_reference(prior)

        entry_price = prior.entry_cost / prior.remaining_quantity
        peak = prior.peak_favorable_price
        if observed_best_bid is not None and (peak is None or observed_best_bid > peak):
            peak = observed_best_bid
        elif peak is None:
            peak = entry_price

        elapsed_minutes = (
            None if prior.entered_monotonic_ns is None
            else Decimal(snapshot.generated_monotonic_ns - prior.entered_monotonic_ns) / NS_PER_MINUTE
        )
        duration_cap_triggered = (
            prior.duration_cap_minutes is not None
            and elapsed_minutes is not None
            and elapsed_minutes >= prior.duration_cap_minutes
        )
        trailing_lock_triggered = False
        if (
            prior.trailing_activation_margin is not None
            and observed_best_bid is not None
            and peak >= entry_price + prior.trailing_activation_margin
        ):
            give_back_tolerance = (peak - entry_price) * TRAILING_GIVE_BACK_FRACTION
            trailing_lock_triggered = observed_best_bid <= peak - give_back_tolerance
        accept_partial = duration_cap_triggered or trailing_lock_triggered

        result = simulate_ioc(
            action="SELL",
            levels=exit_levels,
            limit_price=Decimal("0"),
            requested_quantity=prior.remaining_quantity,
        )
        stop_loss_proceeds = (
            None if prior.stop_loss_fraction is None
            else prior.entry_cost * (Decimal("1") - prior.stop_loss_fraction)
        )
        held_state = replace(prior, peak_favorable_price=peak)

        if result.status == "MISSED" or (result.status == "PARTIAL" and not accept_partial):
            emitted.append(_event(
                snapshot,
                sequence,
                "shadow_no_fill",
                scenario=scenario,
                position_id=prior.position_id,
                reason="FULL_VISIBLE_EXIT_DEPTH_UNAVAILABLE",
                remaining_quantity=format(prior.remaining_quantity, "f"),
                observed_best_bid_probability=(
                    None if observed_best_bid is None else format(observed_best_bid, "f")
                ),
                hypothetical_resting_exit_limit_probability=hypothetical_resting_exit_limit,
                required_total_net_proceeds=format(prior.required_total_net_proceeds, "f"),
            ))
            return LiveShadowMicroStep(held_state, tuple(emitted))

        if result.status == "PARTIAL":
            sold_fraction = result.filled_quantity / prior.remaining_quantity
            if sold_fraction < MINIMUM_PARTIAL_FILL_FRACTION:
                emitted.append(_event(
                    snapshot,
                    sequence,
                    "shadow_no_fill",
                    scenario=scenario,
                    position_id=prior.position_id,
                    reason="PARTIAL_EXIT_BELOW_MINIMUM_FRACTION",
                    remaining_quantity=format(prior.remaining_quantity, "f"),
                    observed_best_bid_probability=(
                        None if observed_best_bid is None else format(observed_best_bid, "f")
                    ),
                    hypothetical_resting_exit_limit_probability=hypothetical_resting_exit_limit,
                    required_total_net_proceeds=format(prior.required_total_net_proceeds, "f"),
                ))
                return LiveShadowMicroStep(held_state, tuple(emitted))
            decision_id = (
                f"{event_ticker}:{scenario.scenario_id}:{snapshot.snapshot_sequence}:partial_exit"
            )
            emitted.append(_event(
                snapshot,
                sequence,
                "shadow_decision",
                scenario=scenario,
                position_id=prior.position_id,
                decision_record_id=decision_id,
                action=(
                    "SIMULATED_DURATION_CAP_PARTIAL_EXIT" if duration_cap_triggered
                    else "SIMULATED_TRAILING_LOCK_PARTIAL_EXIT"
                ),
                remaining_quantity=format(prior.remaining_quantity, "f"),
                filled_quantity=format(result.filled_quantity, "f"),
                observed_best_bid_probability=(
                    None if observed_best_bid is None else format(observed_best_bid, "f")
                ),
                hypothetical_resting_exit_limit_probability=hypothetical_resting_exit_limit,
                visible_full_exit_net_proceeds=format(result.net_cash_change_total, "f"),
                required_total_net_proceeds=format(prior.required_total_net_proceeds, "f"),
            ))
            sequence += 1
            emitted.extend(_fill_events(
                state=snapshot,
                scenario=scenario,
                sequence=sequence,
                position_id=prior.position_id,
                market_ticker=prior.market_ticker,
                side=prior.side,
                action="SELL",
                fills=result.fills,
            ))
            sequence += len(result.fills)
            cost_of_sold_portion = prior.entry_cost * sold_fraction
            return LiveShadowMicroStep(
                replace(
                    prior,
                    remaining_quantity=prior.remaining_quantity - result.filled_quantity,
                    entry_cost=prior.entry_cost - cost_of_sold_portion,
                    required_total_net_proceeds=(
                        prior.required_total_net_proceeds * (Decimal("1") - sold_fraction)
                    ),
                    peak_favorable_price=peak,
                ),
                tuple(emitted),
            )

        stop_loss_triggered = (
            stop_loss_proceeds is not None
            and result.net_cash_change_total <= stop_loss_proceeds
        )
        if (
            result.net_cash_change_total < prior.required_total_net_proceeds
            and not stop_loss_triggered
            and not duration_cap_triggered
            and not trailing_lock_triggered
        ):
            emitted.append(_event(
                snapshot,
                sequence,
                "shadow_no_fill",
                scenario=scenario,
                position_id=prior.position_id,
                reason="VISIBLE_FULL_EXIT_MISSES_RETAINED_TARGET",
                remaining_quantity=format(prior.remaining_quantity, "f"),
                observed_best_bid_probability=(
                    None if observed_best_bid is None else format(observed_best_bid, "f")
                ),
                hypothetical_resting_exit_limit_probability=hypothetical_resting_exit_limit,
                visible_full_exit_net_proceeds=format(result.net_cash_change_total, "f"),
                required_total_net_proceeds=format(prior.required_total_net_proceeds, "f"),
                stop_loss_fraction=(
                    None if prior.stop_loss_fraction is None else format(prior.stop_loss_fraction, "f")
                ),
                stop_loss_net_proceeds=(
                    None if stop_loss_proceeds is None else format(stop_loss_proceeds, "f")
                ),
            ))
            return LiveShadowMicroStep(held_state, tuple(emitted))
        decision_id = f"{event_ticker}:{scenario.scenario_id}:{snapshot.snapshot_sequence}:exit"
        emitted.append(_event(
            snapshot,
            sequence,
            "shadow_decision",
            scenario=scenario,
            position_id=prior.position_id,
            decision_record_id=decision_id,
            action=(
                "SIMULATED_STOP_LOSS_FULL_EXIT" if stop_loss_triggered
                else "SIMULATED_DURATION_CAP_FULL_EXIT" if duration_cap_triggered
                else "SIMULATED_TRAILING_LOCK_FULL_EXIT" if trailing_lock_triggered
                else "SIMULATED_BACKEND_FULL_EXIT"
            ),
            remaining_quantity=format(prior.remaining_quantity, "f"),
            observed_best_bid_probability=(
                None if observed_best_bid is None else format(observed_best_bid, "f")
            ),
            hypothetical_resting_exit_limit_probability=hypothetical_resting_exit_limit,
            visible_full_exit_net_proceeds=format(result.net_cash_change_total, "f"),
            required_total_net_proceeds=format(prior.required_total_net_proceeds, "f"),
            stop_loss_fraction=(
                None if prior.stop_loss_fraction is None else format(prior.stop_loss_fraction, "f")
            ),
            stop_loss_net_proceeds=(
                None if stop_loss_proceeds is None else format(stop_loss_proceeds, "f")
            ),
            stop_loss_triggered=stop_loss_triggered,
        ))
        sequence += 1
        emitted.extend(_fill_events(
            state=snapshot,
            scenario=scenario,
            sequence=sequence,
            position_id=prior.position_id,
            market_ticker=prior.market_ticker,
            side=prior.side,
            action="SELL",
            fills=result.fills,
        ))
        sequence += len(result.fills)
        emitted.append(_event(
            snapshot,
            sequence,
            "shadow_position_closed",
            scenario=scenario,
            position_id=prior.position_id,
        ))
        completed_entries = prior.filled_entry_count
        return LiveShadowMicroStep(
            LiveShadowMicroState(
                event_ticker=prior.event_ticker,
                position_id=prior.position_id,
                market_ticker=prior.market_ticker,
                side=prior.side,
                remaining_quantity=Decimal("0"),
                entry_cost=prior.entry_cost,
                required_total_net_proceeds=prior.required_total_net_proceeds,
                entry_attempts=prior.entry_attempts,
                closed_event_tickers=(
                    prior.closed_event_tickers | {event_ticker}
                    if completed_entries >= MAXIMUM_FILLED_ENTRIES_PER_EVENT
                    else prior.closed_event_tickers
                ),
                filled_entry_count=completed_entries,
                reentry_reference_market_ticker=(
                    None if completed_entries >= MAXIMUM_FILLED_ENTRIES_PER_EVENT
                    else prior.market_ticker
                ),
                reentry_reference_side=(
                    None if completed_entries >= MAXIMUM_FILLED_ENTRIES_PER_EVENT
                    else prior.side
                ),
                reentry_not_before_snapshot_sequence=snapshot.snapshot_sequence,
                pending_settlements=prior.pending_settlements,
            ),
            tuple(emitted),
        )

    if event_ticker in prior.closed_event_tickers:
        return LiveShadowMicroStep(prior, ())
    if prior.event_ticker not in {None, event_ticker}:
        prior = LiveShadowMicroState(
            None, None, None, None, Decimal("0"), Decimal("0"), None, 0,
            frozenset(), pending_settlements=prior.pending_settlements,
        )

    if prior.reentry_reference_market_ticker is not None:
        reason = _reentry_rearm_reason(snapshot, prior, scenario)
        if reason is None:
            return LiveShadowMicroStep(prior, ())
        emitted.append(_event(
            snapshot,
            sequence,
            "shadow_decision",
            scenario=scenario,
            action="SIMULATED_REENTRY_REARMED",
            reentry_number=prior.filled_entry_count + 1,
            reference_market_ticker=prior.reentry_reference_market_ticker,
            reference_side=prior.reentry_reference_side,
            rearm_reason=reason,
        ))
        return LiveShadowMicroStep(
            LiveShadowMicroState(
                event_ticker=prior.event_ticker,
                position_id=prior.position_id,
                market_ticker=prior.market_ticker,
                side=prior.side,
                remaining_quantity=prior.remaining_quantity,
                entry_cost=prior.entry_cost,
                required_total_net_proceeds=prior.required_total_net_proceeds,
                entry_attempts=prior.entry_attempts,
                closed_event_tickers=prior.closed_event_tickers,
                filled_entry_count=prior.filled_entry_count,
                reentry_not_before_snapshot_sequence=snapshot.snapshot_sequence,
                pending_settlements=prior.pending_settlements,
            ),
            tuple(emitted),
        )

    if snapshot.snapshot_sequence <= prior.reentry_not_before_snapshot_sequence:
        return LiveShadowMicroStep(prior, ())

    if not _entry_window_open(snapshot):
        return LiveShadowMicroStep(prior, ())
    candidate = candidate_resolver(prior, snapshot)
    if (
        candidate is None
        or prior.entry_attempts >= MAXIMUM_ENTRY_ATTEMPTS
        or prior.filled_entry_count >= MAXIMUM_FILLED_ENTRIES_PER_EVENT
    ):
        return LiveShadowMicroStep(prior, ())

    signal = candidate.signal
    attempt_id = f"{event_ticker}:{scenario.scenario_id}:{snapshot.snapshot_sequence}:entry"
    entry_levels = side_purchase_asks(snapshot.books[candidate.market_ticker], candidate.side)
    observed_best_ask = _best_probability(entry_levels, purchase=True)
    emitted.append(_event(
        snapshot,
        sequence,
        "shadow_decision",
        scenario=scenario,
        decision_record_id=attempt_id,
        action=(
            "SIMULATED_ENTRY_IOC"
            if prior.filled_entry_count == 0 else "SIMULATED_REENTRY_IOC"
        ),
        entry_number=prior.filled_entry_count + 1,
        market_ticker=candidate.market_ticker,
        side=candidate.side,
        net_edge_per_contract=format(candidate.net_edge_per_contract, "f"),
        simulated_entry_budget_dollars=format(SIMULATED_ENTRY_BUDGET_DOLLARS, "f"),
        profit_target_multiplier=format(prior.profit_target_multiplier, "f"),
        decision_limit_price=format(signal.decision_limit_price, "f"),
        observed_best_ask_probability=(
            None if observed_best_ask is None else format(observed_best_ask, "f")
        ),
    ))
    sequence += 1
    result = _largest_budgeted_entry(
        levels=entry_levels,
        limit_price=signal.decision_limit_price,
    )
    next_attempts = prior.entry_attempts + 1
    if result is None:
        emitted.append(_event(
            snapshot,
            sequence,
            "shadow_no_fill",
            scenario=scenario,
            decision_record_id=attempt_id,
            reason="VISIBLE_ENTRY_DEPTH_OR_LIMIT_UNAVAILABLE",
        ))
        return LiveShadowMicroStep(
            LiveShadowMicroState(
                event_ticker=event_ticker,
                position_id=None,
                market_ticker=None,
                side=None,
                remaining_quantity=Decimal("0"),
                entry_cost=Decimal("0"),
                required_total_net_proceeds=None,
                entry_attempts=next_attempts,
                closed_event_tickers=prior.closed_event_tickers,
                filled_entry_count=prior.filled_entry_count,
                reentry_not_before_snapshot_sequence=prior.reentry_not_before_snapshot_sequence,
                pending_settlements=prior.pending_settlements,
            ),
            tuple(emitted),
        )

    position_id = (
        f"{market_universe}:{event_ticker}:shadow:{scenario.scenario_id}:"
        f"{snapshot.snapshot_sequence}"
    )
    emitted.extend(_fill_events(
        state=snapshot,
        scenario=scenario,
        sequence=sequence,
        position_id=position_id,
        market_ticker=candidate.market_ticker,
        side=candidate.side,
        action="BUY",
        fills=result.fills,
    ))
    entry_cost = -result.net_cash_change_total
    target = entry_cost + (
        candidate.net_edge_per_contract
        * result.filled_quantity
        * prior.profit_target_multiplier
    )
    return LiveShadowMicroStep(
        LiveShadowMicroState(
            event_ticker=event_ticker,
            position_id=position_id,
            market_ticker=candidate.market_ticker,
            side=candidate.side,
            remaining_quantity=result.filled_quantity,
            entry_cost=entry_cost,
            required_total_net_proceeds=target,
            entry_attempts=next_attempts,
            closed_event_tickers=prior.closed_event_tickers,
            filled_entry_count=prior.filled_entry_count + 1,
            reentry_not_before_snapshot_sequence=prior.reentry_not_before_snapshot_sequence,
            pending_settlements=prior.pending_settlements,
            entered_monotonic_ns=snapshot.generated_monotonic_ns,
        ),
        tuple(emitted),
    )


def advance_live_shadow_micro(
    *,
    prior: LiveShadowMicroState,
    snapshot: LiveShadowCausalState,
    first_event_sequence: int,
) -> LiveShadowMicroStep:
    """Advance the frozen primary ($0.02) policy on the observed shadow path."""
    prepared = _prepare_market_universe(prior, snapshot, MOVING_ATM_ELEVEN)
    step = _advance(
        prior=prepared,
        snapshot=snapshot,
        first_event_sequence=first_event_sequence,
        scenario=PRIMARY_SHADOW_V2_SCENARIO,
        candidate_resolver=lambda _state_before, current: _selected_candidate(current),
        market_universe=MOVING_ATM_ELEVEN,
    )
    if snapshot.snapshot_sequence <= prepared.reentry_not_before_snapshot_sequence:
        return step
    return replace(
        step,
        state=replace(
            step.state,
            decision_diagnostics=_decision_diagnostics_after_snapshot(
                prior=prepared, snapshot=snapshot, scenario=PRIMARY_SHADOW_V2_SCENARIO,
                selected_candidate=any(
                    event.get("action") in {"SIMULATED_ENTRY_IOC", "SIMULATED_REENTRY_IOC"}
                    for event in step.events
                ),
            ),
        ),
    )


def advance_live_shadow_micro_for_scenario(
    *,
    prior: LiveShadowMicroState,
    snapshot: LiveShadowCausalState,
    first_event_sequence: int,
    scenario: ShadowV2Scenario,
    market_universe: str = MOVING_ATM_ELEVEN,
    stop_loss_fraction: Decimal | None = None,
    profit_target_multiplier: Decimal = Decimal("1.00"),
    duration_cap_minutes: Decimal | None = None,
    trailing_activation_margin: Decimal | None = None,
) -> LiveShadowMicroStep:
    """Advance one edge-threshold scenario over the common observed snapshot.

    ``frozen_atm_five`` is an explicit challenger: it freezes the five
    nearest strikes when the event first becomes usable.  The default retains
    the accepted moving ATM +/-5 V2 universe.
    """
    prepared = _prepare_trailing_lock(
        _prepare_duration_cap(
            _prepare_profit_target(
                _prepare_stop_loss(
                    _prepare_market_universe(prior, snapshot, market_universe), stop_loss_fraction,
                ),
                profit_target_multiplier,
            ),
            duration_cap_minutes,
        ),
        trailing_activation_margin,
    )
    step = _advance(
        prior=prepared,
        snapshot=snapshot,
        first_event_sequence=first_event_sequence,
        scenario=scenario,
        candidate_resolver=lambda state_before, current: (
            _selected_candidate_for_scenario(current, scenario, state_before)
            if state_before.market_universe in FROZEN_ATM_UNIVERSES
            else _selected_candidate_for_scenario(current, scenario)
        ),
        market_universe=market_universe,
    )
    step = replace(
        step,
        state=replace(
            step.state,
            market_universe=prepared.market_universe,
            frozen_atm_event_ticker=prepared.frozen_atm_event_ticker,
            frozen_atm_market_tickers=prepared.frozen_atm_market_tickers,
            stop_loss_fraction=prepared.stop_loss_fraction,
            profit_target_multiplier=prepared.profit_target_multiplier,
            duration_cap_minutes=prepared.duration_cap_minutes,
            trailing_activation_margin=prepared.trailing_activation_margin,
        ),
    )
    if snapshot.snapshot_sequence <= prepared.reentry_not_before_snapshot_sequence:
        return step
    return replace(
        step,
        state=replace(
            step.state,
            decision_diagnostics=_decision_diagnostics_after_snapshot(
                prior=prepared, snapshot=snapshot, scenario=scenario,
                selected_candidate=any(
                    event.get("action") in {"SIMULATED_ENTRY_IOC", "SIMULATED_REENTRY_IOC"}
                    for event in step.events
                ),
            ),
        ),
    )

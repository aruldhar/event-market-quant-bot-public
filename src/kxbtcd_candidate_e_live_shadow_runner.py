"""One-step isolated runner for live-shadow simulation and dashboard projection."""
from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from decimal import Decimal

from .kxbtcd_candidate_e_dashboard_shadow_export import (
    export_multi_scenario_shadow_dashboard_snapshot,
)
from .kxbtcd_candidate_e_live_shadow_micro_simulator import (
    MARKET_UNIVERSES,
    MOVING_ATM_ELEVEN,
    advance_live_shadow_micro_for_scenario,
)
from .kxbtcd_candidate_e_live_shadow_simulation_store import (
    LiveShadowSimulationStore,
    LiveShadowStoredState,
)
from .kxbtcd_candidate_e_live_shadow_micro_simulator import LiveShadowMicroState
from .kxbtcd_candidate_e_live_shadow_snapshot_reader import LiveShadowCausalState
from .kxbtcd_candidate_e_live_shadow_settlement import settle_live_shadow_micro_for_scenario
from .kxbtcd_candidate_e_live_shadow_settlement import OfficialKalshiSettlement
from .kxbtcd_candidate_e_shadow_dashboard_read_model import (
    ShadowDashboardReadModelError,
    apply_shadow_dashboard_increment,
    apply_shadow_strategy_dashboard_increment,
    bootstrap_shadow_dashboard_read_model,
    read_shadow_dashboard_cursors,
    read_shadow_strategy_lane_cursors,
)
from .kxbtcd_candidate_e_shadow_strategy_lanes import SHADOW_STRATEGY_LANES
from .kxbtcd_candidate_e_shadow_v2_scenarios import (
    PRIMARY_SHADOW_V2_SCENARIO,
    SHADOW_V2_SCENARIOS,
    ShadowV2Scenario,
)


def _missing_store_events(
    *,
    store: LiveShadowSimulationStore,
    run_id: str,
    scenario_id: str,
    cursor_event_sequence: int,
    stored: LiveShadowStoredState,
):
    store_last_event_sequence = stored.next_event_sequence - 1
    if cursor_event_sequence > store_last_event_sequence:
        raise ShadowDashboardReadModelError(
            "dashboard cursor is ahead of the authoritative shadow ledger"
        )
    if cursor_event_sequence == store_last_event_sequence:
        return ()
    events = store.events(run_id, scenario_id)
    if len(events) != store_last_event_sequence:
        raise ShadowDashboardReadModelError(
            "authoritative shadow ledger length does not match its checkpoint"
        )
    return events[cursor_event_sequence:]


def _process_simulation_unit(
    *,
    store: LiveShadowSimulationStore,
    snapshot: LiveShadowCausalState,
    settlements: tuple[OfficialKalshiSettlement, ...],
    scenario: ShadowV2Scenario,
    storage_id: str,
    market_universe: str,
    stop_loss_fraction: Decimal | None,
    profit_target_multiplier: Decimal,
    duration_cap_minutes: Decimal | None,
    trailing_activation_margin: Decimal | None,
    lane_id: str | None,
    cursor: tuple[int, int] | None,
) -> tuple[LiveShadowStoredState, tuple[dict[str, object], ...], bool]:
    """Advance one independent simulation ledger from the common causal snapshot.

    ``storage_id`` is the ledger key: a legacy edge-scenario id for the
    five-scenario dashboard, or a strategy lane id for the strategy-lane matrix.
    When ``lane_id`` is set every emitted event is tagged with it so the lane
    read model can recover lineage independent of the edge-scenario id shared
    by several lanes.
    """

    def _tagged(events: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
        if lane_id is None:
            return events
        return tuple({**event, "lane_id": lane_id} for event in events)

    stored_after = store.load(snapshot.run_id, storage_id)
    advanced = False
    settlement_emitted: tuple[dict[str, object], ...] = ()
    for settlement in settlements:
        state = stored_after.simulation_state
        if state.remaining_quantity > 0 and state.market_ticker == settlement.market_ticker:
            step = settle_live_shadow_micro_for_scenario(
                prior=state, run_id=snapshot.run_id, scenario=scenario,
                first_event_sequence=stored_after.next_event_sequence,
                input_snapshot_sequence=stored_after.last_snapshot_sequence,
                settlement=settlement,
            )
        else:
            pending = next((item for item in state.pending_settlements
                            if item.market_ticker == settlement.market_ticker), None)
            if pending is None:
                continue
            pending_state = LiveShadowMicroState(
                event_ticker=pending.event_ticker, position_id=pending.position_id,
                market_ticker=pending.market_ticker, side=pending.side,
                remaining_quantity=pending.remaining_quantity, entry_cost=pending.entry_cost,
                required_total_net_proceeds=pending.required_total_net_proceeds,
                entry_attempts=0, closed_event_tickers=frozenset(),
            )
            settled = settle_live_shadow_micro_for_scenario(
                prior=pending_state, run_id=snapshot.run_id, scenario=scenario,
                first_event_sequence=stored_after.next_event_sequence,
                input_snapshot_sequence=stored_after.last_snapshot_sequence,
                settlement=settlement,
            )
            step = replace(
                settled,
                state=replace(
                    state,
                    pending_settlements=tuple(
                        item for item in state.pending_settlements if item != pending
                    ),
                ),
            )
        tagged_events = _tagged(step.events)
        stored_after = store.commit_settlement(
            run_id=snapshot.run_id, scenario_id=storage_id, previous=stored_after,
            next_state=step.state, events=tagged_events,
        )
        settlement_emitted = (*settlement_emitted, *tagged_events)
    if settlement_emitted:
        advanced = True

    catchup: tuple[dict[str, object], ...] = ()
    if cursor is not None:
        cursor_event_sequence, cursor_snapshot_sequence = cursor
        if cursor_snapshot_sequence > stored_after.last_snapshot_sequence:
            raise ShadowDashboardReadModelError(
                "dashboard snapshot cursor is ahead of the authoritative shadow checkpoint"
            )
        catchup = _missing_store_events(
            store=store,
            run_id=snapshot.run_id,
            scenario_id=storage_id,
            cursor_event_sequence=cursor_event_sequence,
            stored=stored_after,
        )

    emitted: tuple[dict[str, object], ...] = ()
    if snapshot.snapshot_sequence > stored_after.last_snapshot_sequence:
        step = advance_live_shadow_micro_for_scenario(
            prior=stored_after.simulation_state,
            snapshot=snapshot,
            first_event_sequence=stored_after.next_event_sequence,
            scenario=scenario,
            market_universe=market_universe,
            stop_loss_fraction=stop_loss_fraction,
            profit_target_multiplier=profit_target_multiplier,
            duration_cap_minutes=duration_cap_minutes,
            trailing_activation_margin=trailing_activation_margin,
        )
        tagged_events = _tagged(step.events)
        stored_after = store.commit_snapshot(
            run_id=snapshot.run_id,
            scenario_id=storage_id,
            snapshot_sequence=snapshot.snapshot_sequence,
            generated_utc=snapshot.generated_utc,
            previous=stored_after,
            next_state=step.state,
            events=tagged_events,
        )
        emitted = tagged_events
        advanced = True

    batch = (*catchup, *emitted) if cursor is not None else ()
    return stored_after, batch, advanced


def process_live_shadow_snapshot(
    *,
    store: LiveShadowSimulationStore,
    snapshot: LiveShadowCausalState,
    dashboard_output: str | Path | None = None,
    dashboard_read_model_output: str | Path | None = None,
    settlements: tuple[OfficialKalshiSettlement, ...] = (),
    market_universe: str = MOVING_ATM_ELEVEN,
    stop_loss_fraction: Decimal | None = None,
    profit_target_multiplier: Decimal = Decimal("1.00"),
) -> bool:
    """Advance every frozen edge policy, and the full strategy-lane matrix,
    from one common causal snapshot.

    Simulation commits remain authoritative and ledger-isolated, whether keyed
    by a legacy edge-scenario id or by a strategy lane id. The Grafana read
    model is incrementally advanced from only the newly committed events; a
    full ledger scan is reserved for initial bootstrap or restart catch-up.
    The legacy JSON snapshot is optional and is intentionally not required by
    the live Grafana path, and it carries only the five-scenario view: the
    strategy-lane matrix is Grafana-only.

    ``market_universe``, ``stop_loss_fraction``, and ``profit_target_multiplier``
    govern only the legacy five-scenario dashboard. Every strategy lane in
    ``SHADOW_STRATEGY_LANES`` carries its own policy, stop, and profit-target
    configuration and always runs, independent of these arguments.
    """
    if dashboard_output is None and dashboard_read_model_output is None:
        raise ValueError("at least one dashboard output is required")
    if market_universe not in MARKET_UNIVERSES:
        raise ValueError("live-shadow market universe is invalid")

    read_model_path = (
        None if dashboard_read_model_output is None
        else Path(dashboard_read_model_output)
    )
    scenario_cursors = (
        None if read_model_path is None
        else read_shadow_dashboard_cursors(read_model_path, snapshot.run_id)
    )
    lane_cursors = (
        None if read_model_path is None
        else read_shadow_strategy_lane_cursors(
            read_model_path, snapshot.run_id, SHADOW_STRATEGY_LANES,
        )
    )

    advanced = False

    scenario_batches: dict[str, tuple[dict[str, object], ...]] = {
        scenario.scenario_id: () for scenario in SHADOW_V2_SCENARIOS
    }
    final_scenario_states: dict[str, LiveShadowStoredState] = {}
    for scenario in SHADOW_V2_SCENARIOS:
        cursor = (
            None if scenario_cursors is None else scenario_cursors[scenario.scenario_id]
        )
        stored_after, batch, unit_advanced = _process_simulation_unit(
            store=store,
            snapshot=snapshot,
            settlements=settlements,
            scenario=scenario,
            storage_id=scenario.scenario_id,
            market_universe=market_universe,
            stop_loss_fraction=(
                stop_loss_fraction
                if scenario.scenario_id == PRIMARY_SHADOW_V2_SCENARIO.scenario_id
                else None
            ),
            profit_target_multiplier=(
                profit_target_multiplier
                if scenario.scenario_id == PRIMARY_SHADOW_V2_SCENARIO.scenario_id
                else Decimal("1.00")
            ),
            duration_cap_minutes=None,
            trailing_activation_margin=None,
            lane_id=None,
            cursor=cursor,
        )
        final_scenario_states[scenario.scenario_id] = stored_after
        if scenario_cursors is not None:
            scenario_batches[scenario.scenario_id] = batch
        advanced = advanced or unit_advanced

    lane_batches: dict[str, tuple[dict[str, object], ...]] = {
        lane.lane_id: () for lane in SHADOW_STRATEGY_LANES
    }
    final_lane_states: dict[str, LiveShadowStoredState] = {}
    for lane in SHADOW_STRATEGY_LANES:
        cursor = None if lane_cursors is None else lane_cursors[lane.lane_id]
        stored_after, batch, unit_advanced = _process_simulation_unit(
            store=store,
            snapshot=snapshot,
            settlements=settlements,
            scenario=lane.scenario,
            storage_id=lane.lane_id,
            market_universe=lane.policy_id,
            stop_loss_fraction=lane.stop_loss_fraction,
            profit_target_multiplier=lane.profit_target_multiplier,
            duration_cap_minutes=lane.duration_cap_minutes,
            trailing_activation_margin=lane.trailing_activation_margin,
            lane_id=lane.lane_id,
            cursor=cursor,
        )
        final_lane_states[lane.lane_id] = stored_after
        if lane_cursors is not None:
            lane_batches[lane.lane_id] = batch
        advanced = advanced or unit_advanced

    if read_model_path is not None:
        if scenario_cursors is None:
            operation = (
                apply_shadow_dashboard_increment
                if read_model_path.exists()
                else bootstrap_shadow_dashboard_read_model
            )
            operation(
                run_id=snapshot.run_id,
                scenario_events=store.all_events(snapshot.run_id),
                scenario_diagnostics={
                    scenario_id: state.simulation_state.decision_diagnostics
                    for scenario_id, state in final_scenario_states.items()
                },
                generated_utc=snapshot.generated_utc,
                input_snapshot_sequence=snapshot.snapshot_sequence,
                output_path=read_model_path,
            )
        else:
            apply_shadow_dashboard_increment(
                run_id=snapshot.run_id,
                scenario_events=scenario_batches,
                scenario_diagnostics={
                    scenario_id: state.simulation_state.decision_diagnostics
                    for scenario_id, state in final_scenario_states.items()
                },
                generated_utc=snapshot.generated_utc,
                input_snapshot_sequence=snapshot.snapshot_sequence,
                output_path=read_model_path,
            )

        lane_events_for_increment = (
            lane_batches
            if lane_cursors is not None
            else store.strategy_events(snapshot.run_id)
        )
        apply_shadow_strategy_dashboard_increment(
            run_id=snapshot.run_id,
            lane_events=lane_events_for_increment,
            lanes=SHADOW_STRATEGY_LANES,
            lane_diagnostics={
                lane_id: state.simulation_state.decision_diagnostics
                for lane_id, state in final_lane_states.items()
            },
            generated_utc=snapshot.generated_utc,
            input_snapshot_sequence=snapshot.snapshot_sequence,
            output_path=read_model_path,
        )

    if dashboard_output is not None:
        export_multi_scenario_shadow_dashboard_snapshot(
            scenario_events=store.all_events(snapshot.run_id),
            generated_utc=snapshot.generated_utc,
            input_snapshot_sequence=snapshot.snapshot_sequence,
            output_path=dashboard_output,
        )
    return advanced

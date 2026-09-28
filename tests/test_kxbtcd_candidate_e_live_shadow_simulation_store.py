import pytest
from decimal import Decimal

from src.kxbtcd_candidate_e_live_shadow_micro_simulator import (
    FROZEN_ATM_FIVE,
    LiveShadowMicroState,
    LiveShadowPendingSettlement,
)
from src.kxbtcd_candidate_e_live_shadow_simulation_store import (
    CANONICAL_STORE_FILENAME,
    LiveShadowSimulationStore,
    LiveShadowSimulationStoreError,
)
from src.kxbtcd_candidate_e_shadow_v2_scenarios import SHADOW_V2_SCENARIOS


def _event(*, scenario_id: str, sequence: int, snapshot_sequence: int):
    return {
        "run_id": "run-1",
        "scenario_id": scenario_id,
        "event_sequence": sequence,
        "input_snapshot_sequence": snapshot_sequence,
        "event_type": "shadow_runtime_metric",
    }


def test_store_keeps_scenario_checkpoints_and_event_sequences_independent(tmp_path):
    first, second = SHADOW_V2_SCENARIOS[:2]
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        first_previous = store.load("run-1", first.scenario_id)
        second_previous = store.load("run-1", second.scenario_id)
        store.commit_snapshot(
            run_id="run-1",
            scenario_id=first.scenario_id,
            snapshot_sequence=1,
            generated_utc="2026-09-09T00:00:01Z",
            previous=first_previous,
            next_state=LiveShadowMicroState.new(),
            events=(_event(scenario_id=first.scenario_id, sequence=1, snapshot_sequence=1),),
        )
        store.commit_snapshot(
            run_id="run-1",
            scenario_id=second.scenario_id,
            snapshot_sequence=1,
            generated_utc="2026-09-09T00:00:01Z",
            previous=second_previous,
            next_state=LiveShadowMicroState.new(),
            events=(),
        )
        assert store.load("run-1", first.scenario_id).next_event_sequence == 2
        assert store.load("run-1", second.scenario_id).next_event_sequence == 1
        assert len(store.events("run-1", first.scenario_id)) == 1
        assert store.events("run-1", second.scenario_id) == ()
    finally:
        store.close()


def test_store_rejects_cross_scenario_event_lineage(tmp_path):
    first, second = SHADOW_V2_SCENARIOS[:2]
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        previous = store.load("run-1", first.scenario_id)
        with pytest.raises(LiveShadowSimulationStoreError, match="lineage"):
            store.commit_snapshot(
                run_id="run-1",
                scenario_id=first.scenario_id,
                snapshot_sequence=1,
                generated_utc="2026-09-09T00:00:01Z",
                previous=previous,
                next_state=LiveShadowMicroState.new(),
                events=(_event(scenario_id=second.scenario_id, sequence=1, snapshot_sequence=1),),
            )
    finally:
        store.close()


def test_store_rejects_unknown_scenario_id(tmp_path):
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        with pytest.raises(LiveShadowSimulationStoreError, match="frozen catalog"):
            store.load("run-1", "edge_002_lat_0500")
    finally:
        store.close()


def test_store_read_only_mode_can_read_an_existing_shadow_ledger(tmp_path):
    path = tmp_path / CANONICAL_STORE_FILENAME
    writable = LiveShadowSimulationStore(path)
    writable.close()
    reader = LiveShadowSimulationStore(path, read_only=True)
    try:
        assert reader.all_events("run-1")
    finally:
        reader.close()


def test_store_persists_reentry_checkpoint_state(tmp_path):
    scenario = SHADOW_V2_SCENARIOS[0]
    state = LiveShadowMicroState(
        event_ticker="KXBTCD-TEST", position_id="position-1", market_ticker="T1", side="YES",
        remaining_quantity=Decimal("0"), entry_cost=Decimal("100"),
        required_total_net_proceeds=Decimal("104"), entry_attempts=1,
        closed_event_tickers=frozenset(), filled_entry_count=1,
        reentry_reference_market_ticker="T1", reentry_reference_side="YES",
        reentry_not_before_snapshot_sequence=7,
    )
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        previous = store.load("run-1", scenario.scenario_id)
        store.commit_snapshot(
            run_id="run-1", scenario_id=scenario.scenario_id, snapshot_sequence=7,
            generated_utc="2026-09-09T00:00:07Z", previous=previous,
            next_state=state, events=(),
        )
        assert store.load("run-1", scenario.scenario_id).simulation_state == state
    finally:
        store.close()


def test_store_persists_unsettled_prior_event_positions(tmp_path):
    scenario = SHADOW_V2_SCENARIOS[0]
    pending = LiveShadowPendingSettlement(
        "KXBTCD-OLD", "position-old", "T-OLD", "YES", Decimal("200"),
        Decimal("100"), Decimal("104"),
    )
    state = LiveShadowMicroState(
        "KXBTCD-NEXT", "position-next", "T-NEXT", "NO", Decimal("100"),
        Decimal("50"), Decimal("52"), 1, frozenset(), pending_settlements=(pending,),
    )
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        previous = store.load("run-1", scenario.scenario_id)
        store.commit_snapshot(
            run_id="run-1", scenario_id=scenario.scenario_id, snapshot_sequence=1,
            generated_utc="2026-09-09T00:00:01Z", previous=previous,
            next_state=state, events=(),
        )
        assert store.load("run-1", scenario.scenario_id).simulation_state == state
    finally:
        store.close()


def test_store_persists_frozen_atm_five_selection(tmp_path):
    scenario = SHADOW_V2_SCENARIOS[0]
    state = LiveShadowMicroState(
        None, None, None, None, Decimal("0"), Decimal("0"), None, 0, frozenset(),
        market_universe=FROZEN_ATM_FIVE,
        frozen_atm_event_ticker="KXBTCD-TEST",
        frozen_atm_market_tickers=("T2", "T3", "T4", "T5", "T6"),
        stop_loss_fraction=Decimal("0.20"),
        profit_target_multiplier=Decimal("1.50"),
    )
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        previous = store.load("run-1", scenario.scenario_id)
        store.commit_snapshot(
            run_id="run-1", scenario_id=scenario.scenario_id, snapshot_sequence=1,
            generated_utc="2026-09-09T00:00:01Z", previous=previous,
            next_state=state, events=(),
        )
        assert store.load("run-1", scenario.scenario_id).simulation_state == state
    finally:
        store.close()

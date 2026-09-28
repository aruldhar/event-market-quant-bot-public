import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState
from src.kxbtcd_candidate_e_live_shadow_runner import process_live_shadow_snapshot
from src.kxbtcd_candidate_e_live_shadow_micro_simulator import (
    LiveShadowMicroState,
    LiveShadowPendingSettlement,
)
from src.kxbtcd_candidate_e_live_shadow_simulation_store import (
    CANONICAL_STORE_FILENAME,
    LiveShadowSimulationStore,
)
from src.kxbtcd_candidate_e_live_shadow_snapshot import build_live_shadow_snapshot
from src.kxbtcd_candidate_e_live_shadow_settlement import OfficialKalshiSettlement
from src.kxbtcd_candidate_e_live_shadow_snapshot_reader import parse_live_shadow_snapshot
from src.kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose, EventLadder, LadderMarket
from src.kxbtcd_candidate_e_shadow_dashboard_read_model import CANONICAL_READ_MODEL_FILENAME
from src.kxbtcd_candidate_e_shadow_strategy_lanes import SHADOW_STRATEGY_LANES
from src.kxbtcd_candidate_e_shadow_v2_scenarios import (
    PRIMARY_SHADOW_V2_SCENARIO,
    SHADOW_V2_SCENARIOS,
)
from src.kxbtcd_candidate_e_shadow_v2_selection import ShadowV2Selection
from src.kxbtcd_candidate_e_v2_rest_candle_readiness import V2BoundRestCandle

BASELINE_MOVING_ATM_ELEVEN_LANE_ID = (
    "moving_atm_eleven:edge_002:stop=none:target=2.00:durcap=none:trail=none"
)


def _snapshot(sequence: int, run_id: str = "shadow-run"):
    # Five strikes are required so every strategy lane -- including the
    # frozen ATM-five and ATM-one challengers, which freeze a complete
    # nearest-strike window on first touch -- can build its window from this
    # ladder, not only the default moving ATM +/-5 policy.
    ladder = EventLadder("KXBTCD-TEST", "2026-09-09T01:30:00Z", 1788917400000, (
        LadderMarket("KXBTCD-TEST", "T-2", Decimal("99400"), 0, 5, None),
        LadderMarket("KXBTCD-TEST", "T-1", Decimal("99600"), 1, 5, None),
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 2, 5, None),
        LadderMarket("KXBTCD-TEST", "T+1", Decimal("100200"), 3, 5, None),
        LadderMarket("KXBTCD-TEST", "T+2", Decimal("100500"), 4, 5, None),
    ))
    candle = V2BoundRestCandle(run_id, CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal("100000"), sequence, "2026-09-09T00:59:01Z"))
    book = BookState(sequence, (BookLevel(Decimal("0.40"), Decimal("1000")),),
                      (BookLevel(Decimal("0.50"), Decimal("1000")),))
    return parse_live_shadow_snapshot(build_live_shadow_snapshot(
        run_id=run_id, snapshot_sequence=sequence,
        generated_utc=f"2026-09-09T00:59:{sequence:02d}Z",
        generated_monotonic_ns=sequence * 1_000_000_000,
        event_ladder=ladder, candle=candle,
        books={"T-2": book, "T-1": book, "T1": book, "T+1": book, "T+2": book},
    ))


def _candidate(monkeypatch):
    candidate = ShadowV2Selection(
        "T1", "YES", Decimal("0.05"),
        SimpleNamespace(decision_limit_price=Decimal("0.50")),
    )
    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_live_shadow_micro_simulator._selected_candidate_for_scenario",
        lambda *args, **kwargs: candidate,
    )


def test_runner_fans_one_snapshot_to_all_edge_scenarios_and_rebuilds_after_restart(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store_path = tmp_path / CANONICAL_STORE_FILENAME
    output = tmp_path / "shadow_dashboard_snapshot.json"
    first_store = LiveShadowSimulationStore(store_path)

    assert process_live_shadow_snapshot(
        store=first_store,
        snapshot=_snapshot(1),
        dashboard_output=output,
    ) is True
    for scenario in SHADOW_V2_SCENARIOS:
        stored = first_store.load("shadow-run", scenario.scenario_id)
        assert stored.last_snapshot_sequence == 1
    assert len(first_store.events("shadow-run", PRIMARY_SHADOW_V2_SCENARIO.scenario_id)) == 2

    dashboard = json.loads(output.read_text(encoding="utf-8"))
    assert dashboard["primary_scenario_id"] == PRIMARY_SHADOW_V2_SCENARIO.scenario_id
    assert dashboard["input_snapshot_sequence"] == 1
    assert dashboard["latency_sensitivity_scope"] == "OFFLINE_ONLY_NOT_LIVE_RANKED"
    assert len(dashboard["scenario_catalog"]) == 5
    assert len(dashboard["scenarios"]) == 5
    assert {row["scenario_id"] for row in dashboard["scenarios"]} == {
        scenario.scenario_id for scenario in SHADOW_V2_SCENARIOS
    }
    assert all(
        row["execution_timing_basis"] == "OBSERVED_SHADOW_PATH"
        for row in dashboard["scenarios"]
    )
    first_store.close()

    restarted = LiveShadowSimulationStore(store_path)
    assert process_live_shadow_snapshot(
        store=restarted,
        snapshot=_snapshot(1),
        dashboard_output=output,
    ) is False
    for scenario in SHADOW_V2_SCENARIOS:
        assert restarted.load("shadow-run", scenario.scenario_id).last_snapshot_sequence == 1
    assert output.is_file()
    restarted.close()


def test_runner_bootstraps_then_incrementally_advances_query_read_model(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    try:
        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(1),
            dashboard_read_model_output=read_model,
        ) is True
        connection = sqlite3.connect(read_model)
        try:
            assert connection.execute("SELECT COUNT(*) FROM scenario_catalog").fetchone()[0] == 5
            assert connection.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0] == 10
            cursors = connection.execute(
                "SELECT last_event_sequence, last_snapshot_sequence FROM scenario_cursor "
                "WHERE run_id='shadow-run'"
            ).fetchall()
            assert cursors == [(2, 1)] * 5
            diagnostics = connection.execute(
                "SELECT snapshots_evaluated, eligible_candidate_selected "
                "FROM decision_diagnostics WHERE run_id='shadow-run' "
                "ORDER BY scenario_id"
            ).fetchall()
            assert diagnostics == [(1, 1)] * 5
        finally:
            connection.close()

        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(2),
            dashboard_read_model_output=read_model,
        ) is True
        connection = sqlite3.connect(read_model)
        try:
            assert connection.execute(
                "SELECT value FROM dashboard_metadata WHERE key='input_snapshot_sequence'"
            ).fetchone()[0] == "2"
            assert connection.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0] >= 10
            assert all(
                row[0] == 2
                for row in connection.execute(
                    "SELECT last_snapshot_sequence FROM scenario_cursor WHERE run_id='shadow-run'"
                ).fetchall()
            )
        finally:
            connection.close()
    finally:
        store.close()


def test_runner_applies_only_official_final_settlement_without_a_new_snapshot(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        snapshot = _snapshot(1)
        process_live_shadow_snapshot(
            store=store, snapshot=snapshot,
            dashboard_read_model_output=tmp_path / CANONICAL_READ_MODEL_FILENAME,
        )
        assert process_live_shadow_snapshot(
            store=store, snapshot=snapshot,
            dashboard_read_model_output=tmp_path / CANONICAL_READ_MODEL_FILENAME,
            settlements=(OfficialKalshiSettlement("T1", "finalized", "no", "2026-09-09T01:01:00Z"),),
        ) is True
        for scenario in SHADOW_V2_SCENARIOS:
            stored = store.load("shadow-run", scenario.scenario_id)
            assert stored.simulation_state.remaining_quantity == 0
            assert "KXBTCD-TEST" in stored.simulation_state.closed_event_tickers
            assert store.events("shadow-run", scenario.scenario_id)[-2]["event_type"] == "shadow_simulated_settlement"
    finally:
        store.close()


def test_runner_settles_prior_event_without_closing_current_event(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    try:
        dashboard = tmp_path / "shadow_dashboard_snapshot.json"
        assert process_live_shadow_snapshot(
            store=store, snapshot=_snapshot(1), dashboard_output=dashboard,
        ) is True
        for scenario in SHADOW_V2_SCENARIOS:
            previous = store.load("shadow-run", scenario.scenario_id)
            pending = LiveShadowPendingSettlement.from_open_state(
                previous.simulation_state,
            )
            current = LiveShadowMicroState(
                "KXBTCD-CURRENT", "current-position", "T-CURRENT", "NO", Decimal("150"),
                Decimal("90"), Decimal("93"), 1, frozenset(),
                pending_settlements=(pending,),
            )
            store.commit_snapshot(
                run_id="shadow-run", scenario_id=scenario.scenario_id,
                snapshot_sequence=2, generated_utc="2026-09-09T01:00:02Z",
                previous=previous, next_state=current, events=(),
            )

        assert process_live_shadow_snapshot(
            store=store, snapshot=_snapshot(2), dashboard_output=dashboard,
            settlements=(OfficialKalshiSettlement(
                "T1", "finalized", "no", "2026-09-09T01:31:00Z",
            ),),
        ) is True
        for scenario in SHADOW_V2_SCENARIOS:
            stored = store.load("shadow-run", scenario.scenario_id)
            assert stored.simulation_state.position_id == "current-position"
            assert stored.simulation_state.remaining_quantity == Decimal("150")
            assert stored.simulation_state.pending_settlements == ()
            events = store.events("shadow-run", scenario.scenario_id)
            assert events[-2]["event_type"] == "shadow_simulated_settlement"
            assert events[-2]["market_ticker"] == "T1"
    finally:
        store.close()


def test_runner_catches_read_model_up_after_crash_between_store_and_projection(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    try:
        process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(1),
            dashboard_read_model_output=read_model,
        )
        # Simulate the authoritative store advancing while the dashboard projection is absent.
        process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(2),
            dashboard_output=tmp_path / "shadow_dashboard_snapshot.json",
        )
        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(2),
            dashboard_read_model_output=read_model,
        ) is False
        connection = sqlite3.connect(read_model)
        try:
            assert all(
                row[0] == 2
                for row in connection.execute(
                    "SELECT last_snapshot_sequence FROM scenario_cursor WHERE run_id='shadow-run'"
                ).fetchall()
            )
            for scenario in SHADOW_V2_SCENARIOS:
                projected_last = connection.execute(
                    "SELECT last_event_sequence FROM scenario_cursor "
                    "WHERE run_id=? AND scenario_id=?",
                    ("shadow-run", scenario.scenario_id),
                ).fetchone()[0]
                assert projected_last == store.load("shadow-run", scenario.scenario_id).next_event_sequence - 1
        finally:
            connection.close()
    finally:
        store.close()


def test_runner_retains_dashboard_history_and_uses_fresh_cursors_for_a_new_run(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    try:
        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(1, "shadow-run-a"),
            dashboard_read_model_output=read_model,
        ) is True
        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(1, "shadow-run-b"),
            dashboard_read_model_output=read_model,
        ) is True
        connection = sqlite3.connect(read_model)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM scenario_cursor"
            ).fetchone()[0] == 10
            assert connection.execute(
                "SELECT COUNT(DISTINCT run_id) FROM shadow_events"
            ).fetchone()[0] == 2
            assert connection.execute(
                "SELECT value FROM dashboard_metadata WHERE key='input_run_id'"
            ).fetchone()[0] == "shadow-run-b"
        finally:
            connection.close()
    finally:
        store.close()


def test_runner_records_a_negative_realized_pnl_for_a_duration_cap_exit(tmp_path, monkeypatch):
    """A duration-cap exit must book the actual realized dollar loss, not just
    close the position: the read model's simulated_net_pnl is the entry cash
    outflow plus the real executed exit proceeds, so it must come out
    negative when the exit fires below the entry price -- exactly the
    scenario the third-generation duration cap replaced price-based stop-loss
    to cut, once a position has been held past its cap with no recovery."""
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    try:
        # Enter at sequence 1 (ask 0.50). The book's bid stays fixed at 0.40
        # for every sequence, so once the duration cap forces an exit, the
        # position is valued at ~80% of what was paid to enter it -- a real
        # loss, not merely a below-target hold.
        first = _snapshot(1)
        process_live_shadow_snapshot(
            store=store, snapshot=first, dashboard_read_model_output=read_model,
        )
        # Advance monotonic time past the 15-minute duration cap without
        # touching generated_utc's seconds field (which _snapshot derives
        # from the sequence number and cannot exceed 59).
        later = replace(
            _snapshot(2),
            generated_monotonic_ns=first.generated_monotonic_ns + 16 * 60 * 1_000_000_000,
        )
        process_live_shadow_snapshot(
            store=store, snapshot=later, dashboard_read_model_output=read_model,
        )

        duration_cap_lane_id = "moving_atm_eleven:edge_002:stop=none:target=2.00:durcap=15:trail=none"
        lane_state = store.load("shadow-run", duration_cap_lane_id)
        assert lane_state.simulation_state.remaining_quantity == 0  # the cap fired and closed it

        connection = sqlite3.connect(read_model)
        try:
            row = connection.execute(
                "SELECT simulated_flat, simulated_net_pnl FROM strategy_lane_trades "
                "WHERE run_id='shadow-run' AND lane_id=?",
                (duration_cap_lane_id,),
            ).fetchone()
        finally:
            connection.close()
        assert row is not None
        simulated_flat, simulated_net_pnl = row
        assert simulated_flat == 1
        assert simulated_net_pnl < 0
    finally:
        store.close()


def test_runner_advances_every_strategy_lane_into_the_comparison_read_model(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    try:
        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(1),
            dashboard_read_model_output=read_model,
        ) is True

        lane_states = store.strategy_states("shadow-run")
        assert set(lane_states) == {lane.lane_id for lane in SHADOW_STRATEGY_LANES}
        assert all(state.last_snapshot_sequence == 1 for state in lane_states.values())
        # The stubbed candidate qualifies for every edge threshold, so every
        # lane's own market-universe policy should have opened a position.
        assert all(
            state.simulation_state.remaining_quantity > 0
            for state in lane_states.values()
        )

        connection = sqlite3.connect(read_model)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM strategy_lane_catalog"
            ).fetchone()[0] == 35
            assert connection.execute(
                "SELECT COUNT(*) FROM strategy_lane_cursor WHERE run_id='shadow-run'"
            ).fetchone()[0] == 35
            baseline_events = connection.execute(
                "SELECT event_type, market_ticker FROM strategy_lane_events "
                "WHERE run_id='shadow-run' AND lane_id=? ORDER BY event_sequence",
                (BASELINE_MOVING_ATM_ELEVEN_LANE_ID,),
            ).fetchall()
            assert ("shadow_decision", "T1") in baseline_events
            assert ("shadow_simulated_fill", "T1") in baseline_events
            trade = connection.execute(
                "SELECT market_ticker, simulated_flat FROM strategy_lane_trades "
                "WHERE run_id='shadow-run' AND lane_id=?",
                (BASELINE_MOVING_ATM_ELEVEN_LANE_ID,),
            ).fetchone()
            assert trade == ("T1", 0)
            # The catalog must carry the two new mechanism dimensions per
            # lane -- otherwise the Grafana comparison table can't tell a
            # duration-cap or trailing-lock lane apart from the baseline.
            assert connection.execute(
                "SELECT duration_cap_minutes, trailing_activation_margin "
                "FROM strategy_lane_catalog WHERE lane_id=?",
                (BASELINE_MOVING_ATM_ELEVEN_LANE_ID,),
            ).fetchone() == (None, None)
            assert connection.execute(
                "SELECT duration_cap_minutes, trailing_activation_margin "
                "FROM strategy_lane_catalog WHERE lane_id=?",
                ("moving_atm_eleven:edge_002:stop=none:target=2.00:durcap=15:trail=none",),
            ).fetchone() == (15.0, None)
            assert connection.execute(
                "SELECT duration_cap_minutes, trailing_activation_margin "
                "FROM strategy_lane_catalog WHERE lane_id=?",
                ("moving_atm_eleven:edge_002:stop=none:target=2.00:durcap=none:trail=0.02",),
            ).fetchone() == (None, 0.02)
        finally:
            connection.close()
    finally:
        store.close()


def test_runner_catches_strategy_lane_cursors_up_after_restart(tmp_path, monkeypatch):
    _candidate(monkeypatch)
    store = LiveShadowSimulationStore(tmp_path / CANONICAL_STORE_FILENAME)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    try:
        process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(1),
            dashboard_read_model_output=read_model,
        )
        # Simulate the authoritative store advancing while the dashboard projection is absent.
        process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(2),
            dashboard_output=tmp_path / "shadow_dashboard_snapshot.json",
        )
        assert process_live_shadow_snapshot(
            store=store,
            snapshot=_snapshot(2),
            dashboard_read_model_output=read_model,
        ) is False
        connection = sqlite3.connect(read_model)
        try:
            for lane in SHADOW_STRATEGY_LANES:
                projected_last_event, projected_last_snapshot = connection.execute(
                    "SELECT last_event_sequence, last_snapshot_sequence FROM strategy_lane_cursor "
                    "WHERE run_id=? AND lane_id=?",
                    ("shadow-run", lane.lane_id),
                ).fetchone()
                lane_state = store.load("shadow-run", lane.lane_id)
                assert projected_last_snapshot == 2
                assert projected_last_event == lane_state.next_event_sequence - 1
        finally:
            connection.close()
    finally:
        store.close()

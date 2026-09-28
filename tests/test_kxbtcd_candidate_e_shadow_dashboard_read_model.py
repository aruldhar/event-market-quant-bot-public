import sqlite3

from src.kxbtcd_candidate_e_dashboard_shadow_export import (
    build_multi_scenario_shadow_dashboard_snapshot,
)
from src.kxbtcd_candidate_e_dashboard_shadow_projection import (
    EXACT_OBSERVED_DEPTH_IOC,
    SHADOW_EVENT_SCHEMA_VERSION,
)
from src.kxbtcd_candidate_e_live_shadow_micro_simulator import LiveShadowDecisionDiagnostics
from src.kxbtcd_candidate_e_shadow_dashboard_read_model import (
    CANONICAL_READ_MODEL_FILENAME,
    READ_MODEL_SCHEMA_VERSION,
    apply_shadow_strategy_dashboard_increment,
    refresh_shadow_dashboard_read_model,
)
from src.kxbtcd_candidate_e_shadow_strategy_lanes import SHADOW_STRATEGY_LANES
from src.kxbtcd_candidate_e_shadow_v2_scenarios import SHADOW_V2_SCENARIOS


def _event(*, scenario_id, sequence, kind, **fields):
    return {
        "schema_version": SHADOW_EVENT_SCHEMA_VERSION,
        "run_id": "shadow-run",
        "scenario_id": scenario_id,
        "event_sequence": sequence,
        "input_snapshot_sequence": 9,
        "snapshot_generated_utc": "2026-09-09T01:02:03Z",
        "event_type": kind,
        **fields,
    }


def _fill(*, scenario_id, sequence, side):
    return _event(
        scenario_id=scenario_id,
        sequence=sequence,
        kind="shadow_simulated_fill",
        position_id="position-1",
        market_ticker="KXBTCD-TEST",
        side=side,
        simulated_quantity="1",
        simulated_price="0.40" if side == "buy" else "0.60",
        simulated_fee="0.01",
        fill_assumption=EXACT_OBSERVED_DEPTH_IOC,
        observed_book_received_utc="2026-09-09T01:02:03Z",
    )


def _settlement(*, scenario_id, sequence, result):
    return _event(
        scenario_id=scenario_id, sequence=sequence, kind="shadow_simulated_settlement",
        position_id="position-1", market_ticker="KXBTCD-TEST", position_side="yes",
        official_market_status="finalized", official_market_result=result,
        settlement_basis="OFFICIAL_FINAL_MARKET_RESULT", settlement_quantity="1",
        simulated_settlement_payout="1" if result == "yes" else "0",
    )


def test_read_model_materializes_five_scenarios_trades_and_event_lineage(tmp_path):
    primary = next(item for item in SHADOW_V2_SCENARIOS if item.is_primary)
    scenario_events = {item.scenario_id: () for item in SHADOW_V2_SCENARIOS}
    scenario_events[primary.scenario_id] = (
        _fill(scenario_id=primary.scenario_id, sequence=1, side="buy"),
        _fill(scenario_id=primary.scenario_id, sequence=2, side="sell"),
        _event(
            scenario_id=primary.scenario_id,
            sequence=3,
            kind="shadow_position_closed",
            position_id="position-1",
        ),
    )
    snapshot = build_multi_scenario_shadow_dashboard_snapshot(
        scenario_events=scenario_events,
        generated_utc="2026-09-09T01:02:03Z",
        input_snapshot_sequence=9,
    )
    output = tmp_path / CANONICAL_READ_MODEL_FILENAME
    refresh_shadow_dashboard_read_model(
        dashboard_snapshot=snapshot,
        scenario_events=scenario_events,
        output_path=output,
    )

    connection = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT value FROM dashboard_metadata WHERE key='schema_version'"
        ).fetchone()[0] == READ_MODEL_SCHEMA_VERSION
        assert connection.execute("SELECT COUNT(*) FROM scenario_catalog").fetchone()[0] == 5
        assert connection.execute(
            "SELECT scenario_id FROM scenario_catalog WHERE is_primary=1"
        ).fetchone()[0] == primary.scenario_id
        assert connection.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1
        pnl, entry_utc, exit_utc = connection.execute(
            "SELECT simulated_net_pnl, entry_utc, exit_utc FROM trades"
        ).fetchone()
        assert pnl == 0.18
        assert entry_utc == "2026-09-09T01:02:03Z"
        assert exit_utc == "2026-09-09T01:02:03Z"
        assert connection.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0] == 3
    finally:
        connection.close()


def test_read_model_uses_delete_journal_so_query_only_mount_does_not_require_wal_sidecars(tmp_path):
    scenario_events = {item.scenario_id: () for item in SHADOW_V2_SCENARIOS}
    snapshot = build_multi_scenario_shadow_dashboard_snapshot(
        scenario_events=scenario_events,
        generated_utc="2026-09-09T01:02:03Z",
        input_snapshot_sequence=1,
    )
    output = tmp_path / CANONICAL_READ_MODEL_FILENAME
    refresh_shadow_dashboard_read_model(
        dashboard_snapshot=snapshot,
        scenario_events=scenario_events,
        output_path=output,
    )
    connection = sqlite3.connect(output)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "delete"
    finally:
        connection.close()


def test_read_model_migrates_a_pre_duration_cap_strategy_lane_catalog_in_place(tmp_path):
    """This read model is a single file accumulated across every run this
    host has ever done, not a per-run store -- opening a pre-existing file
    that predates the duration-cap/trailing-lock columns must upgrade it in
    place (preserving its rows) rather than reject it as an incompatible
    schema, which would either wall off or destroy real accumulated run
    history."""
    output = tmp_path / CANONICAL_READ_MODEL_FILENAME
    connection = sqlite3.connect(output)
    try:
        connection.execute("""
            CREATE TABLE strategy_lane_catalog (
                lane_id TEXT PRIMARY KEY, policy_id TEXT NOT NULL, scenario_id TEXT NOT NULL,
                edge_threshold REAL NOT NULL, edge_threshold_text TEXT NOT NULL,
                stop_loss_fraction REAL, profit_target_multiplier REAL NOT NULL
            )
        """)
        connection.execute(
            "INSERT INTO strategy_lane_catalog VALUES "
            "('old-lane','moving_atm_eleven','edge_002',0.02,'0.02',0.2,1.0)"
        )
        connection.execute("CREATE TABLE dashboard_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO dashboard_metadata VALUES ('schema_version', ?)", (READ_MODEL_SCHEMA_VERSION,),
        )
        connection.commit()
    finally:
        connection.close()

    # This is the actual production call that crashed against the
    # pre-existing file on EC2 -- unlike refresh_shadow_dashboard_read_model
    # (a test-only full-rebuild helper that deletes the file first), this is
    # the real incremental path and must open the file in place.
    apply_shadow_strategy_dashboard_increment(
        run_id="shadow-run",
        lane_events={lane.lane_id: () for lane in SHADOW_STRATEGY_LANES},
        lanes=SHADOW_STRATEGY_LANES,
        lane_diagnostics={lane.lane_id: LiveShadowDecisionDiagnostics() for lane in SHADOW_STRATEGY_LANES},
        generated_utc="2026-09-09T01:02:03Z",
        input_snapshot_sequence=1,
        output_path=output,
    )
    connection = sqlite3.connect(output)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(strategy_lane_catalog)").fetchall()}
        assert {"duration_cap_minutes", "trailing_activation_margin"}.issubset(columns)
        assert connection.execute(
            "SELECT lane_id, duration_cap_minutes, trailing_activation_margin "
            "FROM strategy_lane_catalog WHERE lane_id='old-lane'"
        ).fetchone() == ("old-lane", None, None)
    finally:
        connection.close()


def test_read_model_marks_final_official_loss_as_negative_entry_outlay(tmp_path):
    primary = next(item for item in SHADOW_V2_SCENARIOS if item.is_primary)
    scenario_events = {item.scenario_id: () for item in SHADOW_V2_SCENARIOS}
    scenario_events[primary.scenario_id] = (
        _fill(scenario_id=primary.scenario_id, sequence=1, side="buy"),
        _settlement(scenario_id=primary.scenario_id, sequence=2, result="no"),
        _event(scenario_id=primary.scenario_id, sequence=3, kind="shadow_position_closed", position_id="position-1"),
    )
    snapshot = build_multi_scenario_shadow_dashboard_snapshot(
        scenario_events=scenario_events, generated_utc="2026-09-09T01:02:03Z", input_snapshot_sequence=9,
    )
    output = tmp_path / CANONICAL_READ_MODEL_FILENAME
    refresh_shadow_dashboard_read_model(
        dashboard_snapshot=snapshot, scenario_events=scenario_events, output_path=output,
    )
    connection = sqlite3.connect(output)
    try:
        assert connection.execute("SELECT simulated_net_pnl FROM trades").fetchone()[0] == -0.41
    finally:
        connection.close()

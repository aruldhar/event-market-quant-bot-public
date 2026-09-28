from decimal import Decimal

from src.kxbtcd_candidate_e_live_shadow_micro_simulator import (
    LiveShadowMicroState,
    LiveShadowPendingSettlement,
)
from src.kxbtcd_candidate_e_live_shadow_settlement_closeout import (
    CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME,
    LiveShadowSettlementCloseoutReceipt,
    read_live_shadow_settlement_closeout_receipt,
    run_live_shadow_settlement_closeout,
    unresolved_shadow_market_tickers,
    write_live_shadow_settlement_closeout_receipt,
    wait_for_terminal_soak_manifest,
)
from src.kxbtcd_candidate_e_live_shadow_simulation_store import (
    CANONICAL_STORE_FILENAME,
    LiveShadowSimulationStore,
)
from src.kxbtcd_candidate_e_shadow_strategy_lanes import SHADOW_STRATEGY_LANES
from src.kxbtcd_candidate_e_shadow_v2_scenarios import PRIMARY_SHADOW_V2_SCENARIO


class Response:
    status_code = 200
    text = '{"market":{"ticker":"T1","status":"finalized","result":"yes"}}'

    def raise_for_status(self):
        return None


class Session:
    def get(self, *args, **kwargs):
        return Response()


def _open_state():
    return LiveShadowMicroState(
        event_ticker="KXBTCD-TEST", position_id="position-1", market_ticker="T1", side="YES",
        remaining_quantity=Decimal("200"), entry_cost=Decimal("100"),
        required_total_net_proceeds=Decimal("104"), entry_attempts=1, closed_event_tickers=frozenset(),
    )


def _store_open_position(tmp_path):
    path = tmp_path / CANONICAL_STORE_FILENAME
    store = LiveShadowSimulationStore(path)
    previous = store.load("run-1", PRIMARY_SHADOW_V2_SCENARIO.scenario_id)
    store.commit_snapshot(
        run_id="run-1", scenario_id=PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
        snapshot_sequence=1, generated_utc="2026-09-09T01:00:00Z",
        previous=previous, next_state=_open_state(), events=(),
    )
    store.close()
    return path


def test_closeout_archives_and_publishes_official_final_market_result(tmp_path):
    store = _store_open_position(tmp_path)
    settlements = tmp_path / "official_final_settlements.json"
    receipt = tmp_path / CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME
    result = run_live_shadow_settlement_closeout(
        run_id="run-1", store_path=store, archive_root=tmp_path / "raw",
        settlements_output=settlements, receipt_output=receipt, session=Session(),
        wait_seconds=1, poll_seconds=1,
    )
    assert result.status == "SETTLED"
    assert result.unresolved_market_tickers == ()
    assert receipt.is_file()
    assert settlements.is_file()


def test_closeout_receipt_is_run_bound_and_tickers_are_derived_from_open_positions(tmp_path):
    store = _store_open_position(tmp_path)
    assert unresolved_shadow_market_tickers(store_path=store, run_id="run-1") == ("T1",)
    path = tmp_path / CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME
    expected = LiveShadowSettlementCloseoutReceipt("run-1", "DEADLINE_EXPIRED", ("T1",))
    write_live_shadow_settlement_closeout_receipt(output_path=path, receipt=expected)
    assert read_live_shadow_settlement_closeout_receipt(path=path, run_id="run-1") == expected


def test_closeout_detects_a_lane_only_open_position_no_legacy_scenario_has(tmp_path):
    """A stricter strategy lane (e.g. a higher profit-target multiplier) can
    still be open on a ticker its baseline legacy scenario already closed.
    Closeout must not be blind to that ticker just because the legacy
    5-scenario ledger has nothing open there -- this is exactly what left
    four lane positions permanently unsettled in run r33."""
    path = tmp_path / CANONICAL_STORE_FILENAME
    store = LiveShadowSimulationStore(path)
    try:
        lane_id = SHADOW_STRATEGY_LANES[0].lane_id
        previous = store.load("run-1", lane_id)
        store.commit_snapshot(
            run_id="run-1", scenario_id=lane_id,
            snapshot_sequence=1, generated_utc="2026-09-09T01:00:00Z",
            previous=previous, next_state=_open_state(), events=(),
        )
    finally:
        store.close()
    # No legacy scenario has anything open here -- only the lane does.
    assert unresolved_shadow_market_tickers(store_path=path, run_id="run-1") == ("T1",)


def test_closeout_includes_prior_event_awaiting_official_settlement(tmp_path):
    path = tmp_path / CANONICAL_STORE_FILENAME
    store = LiveShadowSimulationStore(path)
    try:
        pending = LiveShadowPendingSettlement(
            "KXBTCD-OLD", "position-old", "T-OLD", "NO", Decimal("200"),
            Decimal("100"), Decimal("104"),
        )
        current = LiveShadowMicroState(
            event_ticker="KXBTCD-NEW", position_id="position-new", market_ticker="T-NEW",
            side="YES", remaining_quantity=Decimal("150"), entry_cost=Decimal("90"),
            required_total_net_proceeds=Decimal("93"), entry_attempts=1,
            closed_event_tickers=frozenset(), pending_settlements=(pending,),
        )
        previous = store.load("run-1", PRIMARY_SHADOW_V2_SCENARIO.scenario_id)
        store.commit_snapshot(
            run_id="run-1", scenario_id=PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
            snapshot_sequence=1, generated_utc="2026-09-09T01:00:00Z",
            previous=previous, next_state=current, events=(),
        )
    finally:
        store.close()
    assert unresolved_shadow_market_tickers(store_path=path, run_id="run-1") == ("T-NEW", "T-OLD")


def test_closeout_waits_for_a_terminal_manifest_for_its_own_run(tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text(
        '{"run_id":"run-1","lifecycle_state":"TERMINAL","measurement_complete":true}',
        encoding="utf-8",
    )
    assert wait_for_terminal_soak_manifest(
        manifest_path=manifest, run_id="run-1", wait_seconds=1, poll_seconds=1,
    ) is True

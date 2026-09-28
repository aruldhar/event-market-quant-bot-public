import sqlite3
from decimal import Decimal

from src.kxbtcd_candidate_e_live_shadow_runner_cli import main
from src.kxbtcd_candidate_e_live_shadow_simulation_store import CANONICAL_STORE_FILENAME
from src.kxbtcd_candidate_e_live_shadow_snapshot import build_live_shadow_snapshot, write_live_shadow_snapshot
from src.kxbtcd_candidate_e_live_shadow_settlement_closeout import (
    CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME,
    LiveShadowSettlementCloseoutReceipt,
    write_live_shadow_settlement_closeout_receipt,
)
from src.kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose, EventLadder, LadderMarket
from src.kxbtcd_candidate_e_shadow_dashboard_read_model import CANONICAL_READ_MODEL_FILENAME
from src.kxbtcd_candidate_e_v2_rest_candle_readiness import V2BoundRestCandle
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState


def _snapshot_path(tmp_path):
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
    candle = V2BoundRestCandle("shadow-run", CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal("100000"), 1, "2026-09-09T00:59:01Z"))
    book = BookState(1, (BookLevel(Decimal("0.40"), Decimal("1")),),
                      (BookLevel(Decimal("0.50"), Decimal("1")),))
    snapshot_path = tmp_path / "latest_causal_snapshot.json"
    write_live_shadow_snapshot(output_path=snapshot_path, snapshot=build_live_shadow_snapshot(
        run_id="shadow-run", snapshot_sequence=1, generated_utc="2026-09-09T00:59:01Z",
        generated_monotonic_ns=1, event_ladder=ladder, candle=candle,
        books={"T-2": book, "T-1": book, "T1": book, "T+1": book, "T+2": book},
    ))
    return snapshot_path


def test_runner_cli_processes_a_snapshot_once(tmp_path):
    snapshot_path = _snapshot_path(tmp_path)
    output = tmp_path / "shadow_dashboard_snapshot.json"
    assert main(["--snapshot", str(snapshot_path), "--store", str(tmp_path / CANONICAL_STORE_FILENAME),
                 "--dashboard-output", str(output), "--once"]) == 0
    assert output.is_file()


def test_runner_cli_supports_read_model_only_dashboard_path(tmp_path):
    snapshot_path = _snapshot_path(tmp_path)
    read_model = tmp_path / CANONICAL_READ_MODEL_FILENAME
    assert main(["--snapshot", str(snapshot_path), "--store", str(tmp_path / CANONICAL_STORE_FILENAME),
                 "--dashboard-read-model", str(read_model), "--once"]) == 0
    assert read_model.is_file()


def test_runner_cli_accepts_the_primary_dynamic_stop_loss(tmp_path):
    snapshot_path = _snapshot_path(tmp_path)
    output = tmp_path / "shadow_dashboard_snapshot.json"
    assert main([
        "--snapshot", str(snapshot_path), "--store", str(tmp_path / CANONICAL_STORE_FILENAME),
        "--dashboard-output", str(output), "--primary-stop-loss", "0.20", "--once",
    ]) == 0


def _closeout_receipt(tmp_path):
    receipt = tmp_path / CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME
    write_live_shadow_settlement_closeout_receipt(
        output_path=receipt,
        receipt=LiveShadowSettlementCloseoutReceipt("shadow-run", "NO_OPEN_POSITIONS", ()),
    )
    return receipt


def test_runner_cli_retries_when_the_read_model_is_locked_by_a_concurrent_reader(tmp_path, monkeypatch):
    """A 24h run died at ~9.7h with `database is locked` because the poll loop
    only tolerated an unreadable snapshot. A locked projection is transient:
    the authoritative store is already committed and the next poll catches the
    read model up, so the process must keep running."""
    import src.kxbtcd_candidate_e_live_shadow_runner_cli as cli

    real = cli.process_live_shadow_snapshot
    calls = []

    def flaky(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real(**kwargs)

    monkeypatch.setattr(cli, "process_live_shadow_snapshot", flaky)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    snapshot_path = _snapshot_path(tmp_path)
    receipt = _closeout_receipt(tmp_path)
    assert main([
        "--snapshot", str(snapshot_path), "--store", str(tmp_path / CANONICAL_STORE_FILENAME),
        "--dashboard-read-model", str(tmp_path / CANONICAL_READ_MODEL_FILENAME),
        "--settlement-closeout-receipt", str(receipt),
    ]) == 0
    assert len(calls) == 2


def test_runner_cli_still_fails_on_other_sqlite_operational_errors(tmp_path, monkeypatch):
    import pytest
    import src.kxbtcd_candidate_e_live_shadow_runner_cli as cli

    def broken(**kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(cli, "process_live_shadow_snapshot", broken)
    snapshot_path = _snapshot_path(tmp_path)
    with pytest.raises(sqlite3.OperationalError):
        main([
            "--snapshot", str(snapshot_path), "--store", str(tmp_path / CANONICAL_STORE_FILENAME),
            "--dashboard-read-model", str(tmp_path / CANONICAL_READ_MODEL_FILENAME),
        ])


def test_runner_cli_accepts_a_terminal_settlement_closeout_receipt(tmp_path):
    snapshot_path = _snapshot_path(tmp_path)
    output = tmp_path / "shadow_dashboard_snapshot.json"
    receipt = tmp_path / CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME
    write_live_shadow_settlement_closeout_receipt(
        output_path=receipt,
        receipt=LiveShadowSettlementCloseoutReceipt("shadow-run", "NO_OPEN_POSITIONS", ()),
    )
    assert main([
        "--snapshot", str(snapshot_path), "--store", str(tmp_path / CANONICAL_STORE_FILENAME),
        "--dashboard-output", str(output), "--settlement-closeout-receipt", str(receipt),
    ]) == 0

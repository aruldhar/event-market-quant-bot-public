from dataclasses import dataclass
from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState
from src.kxbtcd_candidate_e_live_shadow_snapshot import (
    CANONICAL_SNAPSHOT_FILENAME,
    LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION,
    LiveShadowSnapshotError,
    build_live_shadow_snapshot,
    write_live_shadow_snapshot,
)
from src.kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose, EventLadder, LadderMarket
from src.kxbtcd_candidate_e_v2_rest_candle_readiness import V2BoundRestCandle


def event_ladder():
    return EventLadder("KXBTCD-TEST", "2026-09-09T01:00:00Z", 1788915600000, (
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 2, "BRR"),
        LadderMarket("KXBTCD-TEST", "T2", Decimal("100000"), 1, 2, "BRR"),
    ))


def candle():
    return V2BoundRestCandle("run-1", CoinbaseMinuteClose(
        1788915480, 1788915540, Decimal("100000"), 10, "2026-09-09T00:59:01Z"))


def books():
    state = lambda stamp: BookState(stamp, (BookLevel(Decimal("0.5"), Decimal("1")),),
                                    (BookLevel(Decimal("0.6"), Decimal("1")),))
    return {"T1": state(1), "T2": state(2)}


def test_snapshot_contains_complete_sanitized_causal_state_and_writes_atomically(tmp_path):
    snapshot = build_live_shadow_snapshot(run_id="run-1", snapshot_sequence=1,
        generated_utc="2026-09-09T00:59:02Z", generated_monotonic_ns=12,
        event_ladder=event_ladder(), candle=candle(), books=books())
    assert snapshot["schema_version"] == LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["completed_coinbase_candle"]["close"] == "100000"
    assert {book["market_ticker"] for book in snapshot["books"]} == {"T1", "T2"}
    output = tmp_path / CANONICAL_SNAPSHOT_FILENAME
    write_live_shadow_snapshot(snapshot=snapshot, output_path=output)
    assert output.exists()


def test_snapshot_rejects_incomplete_event_book_state_or_noncanonical_path(tmp_path):
    with pytest.raises(LiveShadowSnapshotError, match="complete event ladder"):
        build_live_shadow_snapshot(run_id="run-1", snapshot_sequence=1,
            generated_utc="2026-09-09T00:59:02Z", generated_monotonic_ns=12,
            event_ladder=event_ladder(), candle=candle(), books={"T1": books()["T1"]})
    with pytest.raises(LiveShadowSnapshotError, match="canonical"):
        write_live_shadow_snapshot(snapshot={"schema_version": LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION},
                                   output_path=tmp_path / "wrong.json")

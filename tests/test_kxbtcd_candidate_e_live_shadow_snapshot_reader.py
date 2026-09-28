from copy import deepcopy
from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState
from src.kxbtcd_candidate_e_live_shadow_snapshot import build_live_shadow_snapshot
from src.kxbtcd_candidate_e_live_shadow_snapshot_reader import (
    LiveShadowSnapshotReaderError,
    parse_live_shadow_snapshot,
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


def snapshot():
    return build_live_shadow_snapshot(run_id="run-1", snapshot_sequence=1,
        generated_utc="2026-09-09T00:59:02Z", generated_monotonic_ns=12,
        event_ladder=event_ladder(), candle=candle(), books=books())


def test_reader_reconstructs_complete_causal_types_without_raw_payloads():
    state = parse_live_shadow_snapshot(snapshot())
    assert state.event_ladder.event_ticker == "KXBTCD-TEST"
    assert state.candle.minute.close_price == 100000
    assert state.books["T1"].yes_bids[0].price == 0.5


@pytest.mark.parametrize("mutator", [
    lambda p: p.__setitem__("schema_version", "wrong"),
    lambda p: p["books"].pop(),
    lambda p: p["books"][0]["yes_bids"].append(dict(p["books"][0]["yes_bids"][0])),
])
def test_reader_rejects_untrusted_or_incomplete_state(mutator):
    payload = deepcopy(snapshot())
    mutator(payload)
    with pytest.raises(LiveShadowSnapshotReaderError):
        parse_live_shadow_snapshot(payload)

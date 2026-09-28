import json

import pytest

from src.kxbtcd_candidate_e_shadow_archive_reader import ArchivedRawRecord
from src.kxbtcd_candidate_e_shadow_kalshi_replay import (
    ShadowKalshiReplayError,
    reconstruct_kalshi_generation,
)


TICKERS = ("KXBTCD-TEST-T100", "KXBTCD-TEST-T101")


def record(payload, *, ns=1):
    return ArchivedRawRecord(
        source="kalshi_production_ws",
        descriptor_path=None,
        record={
            "source": "kalshi_production_ws",
            "received_utc": "2026-09-08T00:00:00Z",
            "received_monotonic_ns": ns,
            "raw_text": json.dumps(payload),
        },
    )


def snapshot(ticker, seq):
    return {
        "type": "orderbook_snapshot", "seq": seq,
        "msg": {"market_ticker": ticker, "yes_dollars_fp": [["0.60", "2"]],
                "no_dollars_fp": [["0.30", "3"]]},
    }


def test_replay_emits_only_after_entire_ladder_has_snapshots():
    rows = list(reconstruct_kalshi_generation((
        record({"type": "subscribed", "msg": {"channel": "orderbook_delta", "sid": 1}}),
        record(snapshot(TICKERS[0], 1), ns=2),
        record(snapshot(TICKERS[1], 2), ns=3),
        record({"type": "orderbook_delta", "seq": 3, "msg": {
            "market_ticker": TICKERS[0], "side": "yes", "price_dollars": "0.60",
            "delta_fp": "1", "ts_ms": 10}}, ns=4),
    ), subscribed_tickers=TICKERS))
    assert [row.market_ticker for row in rows] == [TICKERS[1], TICKERS[0]]
    assert rows[-1].book_state.yes_bids[0].quantity == 3


def test_replay_fails_closed_on_sequence_gap():
    with pytest.raises(ShadowKalshiReplayError, match="sequence gap"):
        list(reconstruct_kalshi_generation((
            record(snapshot(TICKERS[0], 1)),
            record(snapshot(TICKERS[1], 3)),
        ), subscribed_tickers=TICKERS))


def test_replay_rejects_wrapper_source_mismatch():
    bad = record(snapshot(TICKERS[0], 1))
    bad = ArchivedRawRecord(bad.source, bad.descriptor_path, {**bad.record, "source": "coinbase_exchange_ws"})
    with pytest.raises(ShadowKalshiReplayError, match="does not match"):
        list(reconstruct_kalshi_generation((bad,), subscribed_tickers=TICKERS))


def test_replay_rejects_missing_or_invalid_receipt_timing():
    missing_utc = record(snapshot(TICKERS[0], 1))
    missing_utc = ArchivedRawRecord(
        missing_utc.source,
        missing_utc.descriptor_path,
        {**missing_utc.record, "received_utc": ""},
    )
    with pytest.raises(ShadowKalshiReplayError, match="receipt UTC"):
        list(reconstruct_kalshi_generation((missing_utc,), subscribed_tickers=TICKERS))

    invalid_ns = record(snapshot(TICKERS[0], 1), ns=-1)
    with pytest.raises(ShadowKalshiReplayError, match="receipt monotonic"):
        list(reconstruct_kalshi_generation((invalid_ns,), subscribed_tickers=TICKERS))

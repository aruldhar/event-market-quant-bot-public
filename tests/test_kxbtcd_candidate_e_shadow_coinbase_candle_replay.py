import json
from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_shadow_archive_reader import ArchivedRawRecord
from src.kxbtcd_candidate_e_shadow_coinbase_candle_replay import (
    ShadowCoinbaseCandleReplayError,
    iter_exact_completed_candles,
)


def record(rows, *, status=200, start="2026-09-08T00:00:00Z", end="2026-09-08T00:01:00Z"):
    return ArchivedRawRecord(
        source="coinbase_exchange_rest", descriptor_path=None,
        record={"source": "coinbase_exchange_rest", "received_utc": "2026-09-08T00:01:02Z",
                "received_monotonic_ns": 9, "raw_text": json.dumps(rows),
                "request_identity": {"method": "GET", "status_code": status,
                    "params": {"granularity": 60, "start": start, "end": end}}},
    )


def test_replay_selects_only_the_exact_requested_completed_minute():
    candles = list(iter_exact_completed_candles((record([
        [1788825540, "1", "2", "1.5", "123", "4"],
        [1788825600, "1", "2", "1.5", "456", "4"],
    ]),)))
    assert [(item.minute_start_epoch_s, item.close) for item in candles] == [
        (1788825600, Decimal("456"))
    ]


def test_replay_rejects_empty_or_mismatched_exact_candle_response():
    with pytest.raises(ShadowCoinbaseCandleReplayError, match="lacks one exact"):
        list(iter_exact_completed_candles((record([]),)))
    with pytest.raises(ShadowCoinbaseCandleReplayError, match="not successful"):
        list(iter_exact_completed_candles((record([], status=503),)))

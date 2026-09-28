from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from src.kxbtcd_candidate_e_execution_archive_collector import (
    Cutoffs,
    ExecutionArchiveCollectionError,
    fetch_candles,
)


@dataclass(frozen=True)
class Ref:
    source: str = "kalshi_public_rest"
    session_id: str = "session"
    request_id: str = "request"


@dataclass(frozen=True)
class Resp:
    payload: object
    raw_record: Ref = Ref()


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, path, *, params=None, top_level_container="object"):
        self.calls.append((path, dict(params or {})))
        if not self.responses:
            raise AssertionError("unexpected request")
        payload = self.responses.pop(0)
        return Resp(payload, Ref(request_id=f"r{len(self.calls)}"))


def cutoff():
    dt = datetime.fromisoformat("2026-05-01T00:00:00+00:00")
    return Cutoffs(dt, dt, dt, None)


def test_short_lifecycle_stays_single_request():
    metadata = {
        "ticker": "M",
        "open_time": "1970-01-01T00:00:00Z",
        "close_time": "1970-01-01T01:00:00Z",
        "observed_route_tier": "historical",
    }
    client = FakeClient([{
        "ticker": "M",
        "candlesticks": [{"end_period_ts": 60}],
    }])

    result = fetch_candles(client, metadata=metadata, cutoffs=cutoff())

    assert result["request_count"] == 1
    assert client.calls == [(
        "/historical/markets/M/candlesticks",
        {"start_ts": 0, "end_ts": 3600, "period_interval": 1},
    )]


def test_10140_period_lifecycle_chunks_at_5000_period_cap():
    metadata = {
        "ticker": "M",
        "open_time": "1970-01-01T00:00:00Z",
        "close_time": "1970-01-08T01:00:00Z",
        "observed_route_tier": "historical",
    }
    client = FakeClient([
        {"ticker": "M", "candlesticks": [
            {"end_period_ts": 60},
            {"end_period_ts": 300000},
        ]},
        {"ticker": "M", "candlesticks": [
            {"end_period_ts": 300000},
            {"end_period_ts": 600000},
        ]},
        {"ticker": "M", "candlesticks": [
            {"end_period_ts": 600000},
            {"end_period_ts": 608400},
        ]},
    ])

    result = fetch_candles(client, metadata=metadata, cutoffs=cutoff())

    assert [params for _path, params in client.calls] == [
        {"start_ts": 0, "end_ts": 300000, "period_interval": 1},
        {"start_ts": 300000, "end_ts": 600000, "period_interval": 1},
        {"start_ts": 600000, "end_ts": 608400, "period_interval": 1},
    ]
    assert result["request_count"] == 3
    assert [row["end_period_ts"] for row in result["rows"]] == [
        60,
        300000,
        600000,
        608400,
    ]


def test_inconsistent_boundary_duplicate_fails_closed():
    metadata = {
        "ticker": "M",
        "open_time": "1970-01-01T00:00:00Z",
        "close_time": "1970-01-05T04:01:00Z",
        "observed_route_tier": "historical",
    }
    client = FakeClient([
        {"ticker": "M", "candlesticks": [{
            "end_period_ts": 300000,
            "yes_bid": {"close": "0.40"},
        }]},
        {"ticker": "M", "candlesticks": [{
            "end_period_ts": 300000,
            "yes_bid": {"close": "0.41"},
        }]},
    ])

    with pytest.raises(
        ExecutionArchiveCollectionError,
        match="inconsistent duplicate candle",
    ):
        fetch_candles(
            client,
            metadata=metadata,
            cutoffs=cutoff(),
            max_periods_per_request=5000,
        )

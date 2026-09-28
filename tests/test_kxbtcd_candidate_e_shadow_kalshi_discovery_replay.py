import json
from datetime import datetime, timezone

import pytest

from src.kxbtcd_candidate_e_shadow_archive_reader import ArchivedRawRecord
from src.kxbtcd_candidate_e_shadow_kalshi_discovery_replay import (
    ShadowKalshiDiscoveryReplayError,
    iter_current_event_ladders,
)

# The fixture markets close at this instant. Selection must land within the
# frozen 90-minute successor lead guard (kxbtcd_candidate_e_soak_source_lifecycle
# .MAXIMUM_HOURLY_SUCCESSOR_LEAD_MS), so tests pick a selection timestamp shortly
# before close rather than an arbitrary epoch that predates the fixture by decades.
CLOSE_TIME_MS = int(datetime(2026, 9, 8, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
SELECTION_TIMESTAMP_MS = CLOSE_TIME_MS - 30 * 60 * 1000


def record(payload):
    return ArchivedRawRecord(
        source="kalshi_production_rest", descriptor_path=None,
        record={"source": "kalshi_production_rest", "received_utc": "2026-09-08T00:00:00Z",
                "received_monotonic_ns": 1, "raw_text": json.dumps(payload),
                "request_identity": {"method": "GET", "status_code": 200}},
    )


def markets(*, cursor=None):
    return {"cursor": cursor, "markets": [
        {"ticker": "KXBTCD-26SEP0810-T99000", "event_ticker": "KXBTCD-26SEP0810",
         "status": "active", "close_time": "2026-09-08T10:00:00Z", "floor_strike": "99000"},
        {"ticker": "KXBTCD-26SEP0810-T100000", "event_ticker": "KXBTCD-26SEP0810",
         "status": "active", "close_time": "2026-09-08T10:00:00Z", "floor_strike": "100000"},
    ]}


def test_replay_recovers_full_ladder_and_numeric_strikes_from_archived_discovery():
    result = list(iter_current_event_ladders(
        (record(markets()),), selection_timestamp_ms=SELECTION_TIMESTAMP_MS,
    ))
    assert result[0].ladder.event_ticker == "KXBTCD-26SEP0810"
    assert [item.strike for item in result[0].ladder.markets] == [99000, 100000]


def test_replay_rejects_paginated_discovery_response():
    with pytest.raises(ShadowKalshiDiscoveryReplayError, match="paginated"):
        list(iter_current_event_ladders(
            (record(markets(cursor="more")),), selection_timestamp_ms=SELECTION_TIMESTAMP_MS,
        ))

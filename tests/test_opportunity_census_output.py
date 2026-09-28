from __future__ import annotations

import csv

import pytest

from src.opportunity_census_adapters import (
    CONTRACT_SNAPSHOT_COLUMNS,
    DISCOVERY_COLUMNS,
    KalshiDiscoveryAdapter,
    ObservationContext,
)
from src.opportunity_census_output import (
    CensusOutputError,
    write_contract_snapshot_csv,
    write_discovery_csv,
)


def _page():
    adapter = KalshiDiscoveryAdapter()
    obs = ObservationContext(
        raw_source="raw",
        raw_session_id="session",
        raw_request_id="request",
        request_started_at_utc="2026-08-09T03:00:00Z",
        request_started_monotonic_ns=1,
        received_at_utc="2026-08-09T03:00:00.1Z",
        received_monotonic_ns=2,
    )
    return adapter.parse_page(
        {
            "events": [{
                "event_ticker": "EVT",
                "series_ticker": "SERIES",
                "title": "Q",
                "markets": [{
                    "ticker": "EVT-A",
                    "status": "open",
                    "yes_bid_dollars": "0.4",
                    "yes_ask_dollars": "0.5",
                }],
            }],
            "cursor": None,
        },
        params=adapter.initial_params(),
        observation=obs,
    )


def test_discovery_csv_has_fixed_columns_event_identity_and_lineage(tmp_path):
    path = write_discovery_csv(tmp_path / "census.csv", [_page().rows[0]])
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert tuple(reader.fieldnames) == DISCOVERY_COLUMNS
    assert rows[0]["schema_version"] == "census_opportunity_identity.v1"
    assert rows[0]["source_opportunity_type"] == "event"
    assert rows[0]["source_event_id"] == "EVT"
    assert rows[0]["raw_request_id"] == "request"


def test_contract_snapshot_csv_has_fixed_source_native_schema_and_lineage(tmp_path):
    path = write_contract_snapshot_csv(
        tmp_path / "contracts.csv", [_page().contract_rows[0]]
    )
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert tuple(reader.fieldnames) == CONTRACT_SNAPSHOT_COLUMNS
    assert rows[0]["schema_version"] == "census_contract_snapshot.v1"
    assert rows[0]["source_event_id"] == "EVT"
    assert rows[0]["source_contract_id"] == "EVT-A"
    assert rows[0]["quote_semantics_source"] == "kalshi_yes_no_binary_market_quotes"
    assert rows[0]["raw_request_id"] == "request"


def test_discovery_csv_rejects_schema_column_drift(tmp_path):
    row = _page().rows[0]
    row.pop("raw_request_id")
    with pytest.raises(CensusOutputError, match="columns"):
        write_discovery_csv(tmp_path / "bad.csv", [row])


def test_contract_snapshot_csv_rejects_schema_column_drift(tmp_path):
    row = _page().contract_rows[0]
    row.pop("raw_request_id")
    with pytest.raises(CensusOutputError, match="columns"):
        write_contract_snapshot_csv(tmp_path / "bad-contracts.csv", [row])

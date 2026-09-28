from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import json
from pathlib import Path

import pytest

from src.kxbtcd_chronological_split_contract import TARGET_REGIME_ID
from src.kxbtcd_preoutcome_collector import (
    CHECKPOINT10_MODERN_RULE_REGIME_ID,
    CHECKPOINT10_OLD_RULE_REGIME_ID,
    EVENT_CENSUS_FIELDS,
    EVENT_CENSUS_SCHEMA_VERSION,
    MODERN_EVENT_FIELDS,
    REGIME_SCAN_MIN_CLOSE_UTC,
    KxbtcdPreoutcomeCollectorError,
    ModernRegimeEvidence,
    PreoutcomeCollectionRows,
    build_conservative_modern_sampling_frame,
    discover_settled_event_census,
    event_units_from_modern_events,
    load_checkpoint10_regime_evidence,
    normalize_quote_rows,
    provisional_modern_primitive_id,
    validate_and_normalize_selected_event_markets,
    write_preoutcome_collection,
)


@dataclass(frozen=True)
class _Ref:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class _Response:
    payload: dict
    raw_record: _Ref
    received_at_utc: str = "2026-08-14T08:00:00Z"
    received_monotonic_ns: int = 123456


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, path, *, params=None):
        self.calls.append((path, dict(params or {})))
        if not self.responses:
            raise AssertionError(f"unexpected call: {path} {params}")
        return self.responses.pop(0)


def _event(ticker: str, strike_date: str | None):
    return {
        "event_ticker": ticker,
        "series_ticker": "KXBTCD",
        "strike_date": strike_date,
    }


def _rule_market(
    ticker: str,
    event: str,
    close_time: str,
    *,
    simple: bool = True,
    strike=100000,
):
    dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
    zone = "EDT" if dt.month in {4, 5, 6, 7, 8, 9, 10} else "EST"
    offset = timedelta(hours=-4 if zone == "EDT" else -5)
    local = dt.astimezone(timezone(offset))
    hour12 = local.hour % 12 or 12
    clock = f"{hour12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'} {zone}"
    date = local.strftime("%b %d, %Y")
    if simple:
        primary = (
            f"If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
            f"before {clock} is above {strike} at {clock} on {date}, then the market resolves to Yes."
        )
        secondary = (
            "CF Benchmarks' corresponding Real Time Index (RTI) is used. In the last minute before "
            "expiration, 60 RTI prices are collected. The official and final value is the average of these prices"
        )
    else:
        primary = (
            f"If the average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before "
            f"{clock}, excluding the top 20% and bottom 20% of values is above {strike} at {clock} on {date}, "
            "then the market resolves to Yes."
        )
        secondary = (
            f"The average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before {clock}, "
            "excluding the top 20% and bottom 20% of values"
        )
    return {
        "ticker": ticker,
        "event_ticker": event,
        "close_time": close_time,
        "rules_primary": primary,
        "rules_secondary": secondary,
        "strike_type": "greater",
        "floor_strike": strike,
        "functional_strike": str(strike),
    }


def _resp(payload, request_id):
    return _Response(payload=payload, raw_record=_Ref("kalshi_public_rest", "s", request_id))


def _regime_evidence() -> ModernRegimeEvidence:
    return ModernRegimeEvidence(
        last_old_close_utc="2024-12-20T01:00:00Z",
        last_old_event_ticker="KXBTCD-24DEC1920",
        first_modern_close_utc="2025-03-22T17:00:00Z",
        first_modern_event_ticker="KXBTCD-25MAR2213",
        source_report_path="data/derived/btc_research_unit/report.json",
        source_report_sha256="a" * 64,
    )


def test_event_census_paginates_requires_strike_date_and_stays_preoutcome():
    client = _Client(
        [
            _resp({"events": [_event("KXBTCD-25MAR2213", "2025-03-22T17:00:00Z")], "cursor": "next"}, "r1"),
            _resp({"events": [_event("E2", "2025-03-22T18:00:00Z")], "cursor": ""}, "r2"),
        ]
    )
    rows = discover_settled_event_census(client, run_id="run")
    assert [row["event_ticker"] for row in rows] == ["KXBTCD-25MAR2213", "E2"]
    assert all(row["strike_date_utc"] for row in rows)
    assert all(set(row) == set(EVENT_CENSUS_FIELDS) for row in rows)
    assert all("result" not in row for row in rows)
    expected_min_close_ts = int(
        datetime.fromisoformat(REGIME_SCAN_MIN_CLOSE_UTC.replace("Z", "+00:00")).timestamp()
    ) - 1
    assert client.calls[0][1]["min_close_ts"] == expected_min_close_ts
    assert client.calls[1][1]["min_close_ts"] == expected_min_close_ts



def test_event_census_rejects_event_before_conservative_boundary():
    boundary = datetime.fromisoformat(
        REGIME_SCAN_MIN_CLOSE_UTC.replace("Z", "+00:00")
    )
    before = (boundary - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    client = _Client(
        [
            _resp(
                {
                    "events": [
                        _event("TOO-EARLY", before),
                    ],
                    "cursor": "",
                },
                "r",
            )
        ]
    )

    with pytest.raises(
        KxbtcdPreoutcomeCollectorError,
        match="precedes conservative modern start",
    ):
        discover_settled_event_census(client, run_id="run")



def test_event_census_rejects_missing_post_proof_strike_date():
    client = _Client([_resp({"events": [_event("E", None)], "cursor": ""}, "r")])
    with pytest.raises(KxbtcdPreoutcomeCollectorError, match="event.strike_date"):
        discover_settled_event_census(client, run_id="run")


def test_event_census_rejects_duplicate_strike_date():
    client = _Client(
        [
            _resp(
                {
                    "events": [
                        _event("E1", "2025-03-22T18:00:00Z"),
                        _event("E2", "2025-03-22T18:00:00Z"),
                    ],
                    "cursor": "",
                },
                "r",
            )
        ]
    )
    with pytest.raises(KxbtcdPreoutcomeCollectorError, match="duplicate strike_date"):
        discover_settled_event_census(client, run_id="run")


def test_conservative_sampling_frame_uses_event_time_and_provisional_primitive():
    evidence = _regime_evidence()
    census = (
        {
            "schema_version": EVENT_CENSUS_SCHEMA_VERSION,
            "run_id": "run",
            "event_ticker": evidence.first_modern_event_ticker,
            "strike_date_utc": evidence.first_modern_close_utc,
            "event_raw_ref": "raw:s:x:first",
        },
        {
            "schema_version": EVENT_CENSUS_SCHEMA_VERSION,
            "run_id": "run",
            "event_ticker": "E2",
            "strike_date_utc": "2025-03-22T18:00:00Z",
            "event_raw_ref": "raw:s:x:e2",
        },
    )
    rows = build_conservative_modern_sampling_frame(
        run_id="run",
        event_census=census,
        regime_evidence=evidence,
    )
    assert all(set(row) == set(MODERN_EVENT_FIELDS) for row in rows)
    assert [row["close_time_utc"] for row in rows] == [
        "2025-03-22T17:00:00Z",
        "2025-03-22T18:00:00Z",
    ]
    assert all(row["settlement_regime_id"] == TARGET_REGIME_ID for row in rows)
    assert rows[1]["settlement_primitive_id"] == provisional_modern_primitive_id(
        "2025-03-22T18:00:00Z"
    )
    units = event_units_from_modern_events(rows)
    assert all(len(row["settlement_primitive_ids"]) == 1 for row in units)
    assert evidence.lineage_ref in units[0]["source_lineage_refs"]


def test_sampling_frame_requires_first_sample_proven_modern_event():
    evidence = _regime_evidence()
    census = (
        {
            "schema_version": EVENT_CENSUS_SCHEMA_VERSION,
            "run_id": "run",
            "event_ticker": "LATER",
            "strike_date_utc": "2025-03-22T18:00:00Z",
            "event_raw_ref": "raw:s:x:later",
        },
    )
    with pytest.raises(KxbtcdPreoutcomeCollectorError, match="first sample-observed modern"):
        build_conservative_modern_sampling_frame(
            run_id="run", event_census=census, regime_evidence=evidence
        )


def test_checkpoint10_regime_evidence_loader_freezes_transition(tmp_path: Path):
    root = tmp_path / "data" / "derived" / "btc_research_unit"
    root.mkdir(parents=True)
    report = {
        "status": "PASS",
        "series_results": {
            "KXBTCD": {
                "status": "PASS",
                "observed_sample_transitions": [
                    {
                        "from_regime_id": CHECKPOINT10_OLD_RULE_REGIME_ID,
                        "last_observed_from_close_time": "2024-12-20T01:00:00Z",
                        "to_regime_id": CHECKPOINT10_MODERN_RULE_REGIME_ID,
                        "first_observed_to_close_time": "2025-03-22T17:00:00Z",
                    }
                ],
                "samples": [
                    {
                        "event_ticker": "KXBTCD-24DEC1920",
                        "close_time": "2024-12-20T01:00:00Z",
                        "regime_id": CHECKPOINT10_OLD_RULE_REGIME_ID,
                    },
                    {
                        "event_ticker": "KXBTCD-25MAR2213",
                        "close_time": "2025-03-22T17:00:00Z",
                        "regime_id": CHECKPOINT10_MODERN_RULE_REGIME_ID,
                    },
                ],
            }
        },
    }
    path = root / "x_btc_ladder_rule_regimes.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    evidence = load_checkpoint10_regime_evidence(tmp_path)
    assert evidence.last_old_close_utc == "2024-12-20T01:00:00Z"
    assert evidence.first_modern_close_utc == "2025-03-22T17:00:00Z"
    assert evidence.first_modern_event_ticker == "KXBTCD-25MAR2213"
    assert len(evidence.source_report_sha256) == 64


def _selected_event(event="E", close="2026-03-04T12:00:00Z", primitive=None):
    return {
        "schema_version": "kxbtcd_materialization_selected_event.v1",
        "materialization_fingerprint": "x",
        "split_fingerprint": "y",
        "event_ticker": event,
        "partition": "train",
        "utc_week_start": "2026-03-02T00:00:00Z",
        "close_time_utc": close,
        "settlement_regime_id": TARGET_REGIME_ID,
        "settlement_primitive_ids": [primitive or provisional_modern_primitive_id(close)],
        "source_lineage_refs": [f"raw:event:{event}"],
        "event_selection_hash": "h",
    }


def _five_markets(event="E", close="2026-03-04T12:00:00Z"):
    return [
        _rule_market(f"{event}-T{strike}", event, close, strike=strike)
        for strike in (90000, 100000, 110000, 120000, 130000)
    ]


def test_full_selected_event_validation_rejects_provisional_primitive_mismatch():
    selected = _selected_event(primitive="not-the-real-primitive")
    client = _Client([_resp({"markets": _five_markets(), "cursor": ""}, "all")])
    with pytest.raises(KxbtcdPreoutcomeCollectorError, match="provisional sampling frame"):
        validate_and_normalize_selected_event_markets(
            client,
            selected_event=selected,
            market_settled_cutoff_utc="2025-12-01T00:00:00Z",
        )


def test_full_selected_event_validation_accepts_matching_provisional_primitive():
    selected = _selected_event()
    client = _Client([_resp({"markets": _five_markets(), "cursor": ""}, "all")])
    rows, route, monotonic_ns = validate_and_normalize_selected_event_markets(
        client,
        selected_event=selected,
        market_settled_cutoff_utc="2025-12-01T00:00:00Z",
    )
    assert len(rows) == 5
    assert route == "live"
    assert monotonic_ns == 123456
    assert all(row["event_ticker"] == "E" for row in rows)


def test_full_selected_event_validation_rejects_non_target_regime():
    selected = _selected_event()
    markets = _five_markets()
    markets[0] = _rule_market("E-T90000", "E", "2026-03-04T12:00:00Z", simple=False, strike=90000)
    client = _Client([_resp({"markets": markets, "cursor": ""}, "all")])
    with pytest.raises(KxbtcdPreoutcomeCollectorError, match="non-target"):
        validate_and_normalize_selected_event_markets(
            client,
            selected_event=selected,
            market_settled_cutoff_utc="2025-12-01T00:00:00Z",
        )


def test_quote_normalization_keeps_invalid_rows_but_marks_them_unusable():
    payload = {
        "ticker": "E-T100",
        "candlesticks": [
            {
                "end_period_ts": 100,
                "yes_bid": {"close": "0.40"},
                "yes_ask": {"close": "0.44"},
            },
            {
                "end_period_ts": 160,
                "yes_bid": {"close": "0.60"},
                "yes_ask": {"close": "0.55"},
            },
        ],
    }
    rows = normalize_quote_rows(
        _resp(payload, "candles"),
        market_ticker="E-T100",
        route_tier="historical",
    )
    assert rows[0]["valid_quote_observation"] is True
    assert rows[0]["midpoint"] == "0.42"
    assert rows[1]["valid_quote_observation"] is False
    assert rows[1]["midpoint"] == ""
    assert rows[0]["raw_observation_id"] != rows[1]["raw_observation_id"]


def test_writer_keeps_all_manifest_derived_artifacts_csv(tmp_path):
    state = {
        "state_id": "state-1",
        "state_view": "historical_reconstructed",
        "as_of_utc": "2026-03-04T11:00:00Z",
        "product_context": {"event_ticker": "E", "market_ticker": "E-T100"},
    }
    rows = PreoutcomeCollectionRows(
        event_census=(),
        modern_events=(),
        split_rows=(),
        selected_events=(),
        selected_markets=(),
        quote_audit=(),
        states=(state,),
        dataset_rows=(),
        exclusions=(),
        summary={},
    )
    paths = write_preoutcome_collection(tmp_path, run_id="run", rows=rows)
    assert paths.states_csv.suffix == ".csv"
    assert all(path.suffix == ".csv" for path in paths.all())
    with paths.states_csv.open("r", encoding="utf-8", newline="") as handle:
        output = list(csv.DictReader(handle))
    assert output[0]["state_id"] == "state-1"
    assert json.loads(output[0]["state_json"])["state_view"] == "historical_reconstructed"


def test_historical_market_query_uses_only_event_primary_filter() -> None:
    response = _resp({"markets": [], "cursor": ""}, "hist-filter")
    client = _Client([response])
    from src.kxbtcd_preoutcome_collector import _market_query

    _market_query(
        client,
        event_ticker="KXBTCD-TEST",
        route_tier="historical",
        limit=1000,
    )

    path, params = client.calls[0]
    assert path == "/historical/markets"
    assert params == {"event_ticker": "KXBTCD-TEST", "limit": 1000}

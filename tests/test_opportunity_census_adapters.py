from __future__ import annotations

import pytest

from src.opportunity_census_adapters import (
    CensusAdapterError,
    CryptoComDiscoveryAdapter,
    GeminiDiscoveryAdapter,
    KalshiDiscoveryAdapter,
    ObservationContext,
    PolymarketUSDiscoveryAdapter,
    build_public_discovery_adapters,
)


def obs():
    return ObservationContext(
        raw_source="raw",
        raw_session_id="session",
        raw_request_id="request",
        request_started_at_utc="2026-08-09T03:00:00Z",
        request_started_monotonic_ns=100,
        received_at_utc="2026-08-09T03:00:00.100000Z",
        received_monotonic_ns=200,
    )


def test_build_adapters_matches_every_public_catalog_candidate():
    catalog = {
        "event_venue_candidates": [
            {"candidate_id": "kalshi", "public_discovery": "available"},
            {"candidate_id": "gemini_predictions", "public_discovery": "available"},
            {"candidate_id": "polymarket_us", "public_discovery": "available"},
            {"candidate_id": "crypto_com_predictions", "public_discovery": "available"},
            {"candidate_id": "forecastex", "public_discovery": "not_verified"},
        ]
    }
    adapters = build_public_discovery_adapters(catalog)
    assert [a.candidate_id for a in adapters] == [
        "kalshi",
        "gemini_predictions",
        "polymarket_us",
        "crypto_com_predictions",
    ]


def test_public_candidate_without_adapter_fails_closed():
    catalog = {
        "event_venue_candidates": [
            {"candidate_id": "unknown_public", "public_discovery": "available"}
        ]
    }
    with pytest.raises(CensusAdapterError, match="missing adapters"):
        build_public_discovery_adapters(catalog)


def test_kalshi_uses_event_endpoint_with_nested_markets_and_official_page_limit():
    adapter = KalshiDiscoveryAdapter()
    params = adapter.initial_params()
    assert adapter.path == "/events"
    assert params == {
        "status": "open",
        "limit": 200,
        "with_nested_markets": True,
    }


def test_kalshi_event_count_stays_event_first_and_contract_snapshot_is_separate():
    adapter = KalshiDiscoveryAdapter()
    payload = {
        "events": [{
            "event_ticker": "KXTEST-26AUG09",
            "series_ticker": "KXTEST",
            "title": "Test event",
            "sub_title": "Test subtitle",
            "category": "Economics",
            "strike_date": "2026-08-09T12:00:00Z",
            "markets": [
                {
                    "ticker": "KXTEST-A",
                    "title": "A",
                    "status": "open",
                    "market_type": "binary",
                    "yes_bid_dollars": "0.4900",
                    "yes_ask_dollars": "0.5100",
                    "yes_bid_size_fp": "10.00",
                    "yes_ask_size_fp": "11.00",
                    "no_bid_dollars": "0.4900",
                    "no_ask_dollars": "0.5100",
                    "last_price_dollars": "0.5000",
                    "volume_fp": "100.00",
                    "volume_24h_fp": "20.00",
                    "open_interest_fp": "30.00",
                    "liquidity_dollars": "40.00",
                    "open_time": "2026-08-09T00:00:00Z",
                    "close_time": "2026-08-10T00:00:00Z",
                    "updated_time": "2026-08-09T03:00:00Z",
                },
                {"ticker": "KXTEST-B", "status": "open"},
            ],
        }],
        "cursor": "next",
    }
    page = adapter.parse_page(payload, params=adapter.initial_params(), observation=obs())
    assert len(page.rows) == 1
    assert len(page.contract_rows) == 2
    event_row = page.rows[0]
    assert event_row["schema_version"] == "census_opportunity_identity.v1"
    assert event_row["source_event_id"] == "KXTEST-26AUG09"
    assert event_row["contract_count_source"] == 2
    contract_row = page.contract_rows[0]
    assert contract_row["schema_version"] == "census_contract_snapshot.v1"
    assert contract_row["source_event_id"] == "KXTEST-26AUG09"
    assert contract_row["source_contract_id"] == "KXTEST-A"
    assert contract_row["yes_bid_source"] == "0.4900"
    assert contract_row["yes_ask_source"] == "0.5100"
    assert contract_row["best_bid_source"] == ""
    assert contract_row["quote_semantics_source"] == "kalshi_yes_no_binary_market_quotes"
    assert contract_row["raw_request_id"] == "request"
    assert page.next_params["cursor"] == "next"


def test_gemini_emits_event_and_source_native_contract_snapshots():
    adapter = GeminiDiscoveryAdapter()
    params = adapter.initial_params()
    payload = {
        "data": [{
            "id": "evt_1",
            "ticker": "EVT1",
            "title": "Question",
            "type": "binary",
            "category": "sports",
            "series": "SERIES",
            "status": "active",
            "effectiveDate": "2026-08-09T00:00:00Z",
            "expiryDate": "2026-08-10T00:00:00Z",
            "volume": "10",
            "liquidity": "20",
            "contracts": [
                {
                    "id": "c1",
                    "instrumentSymbol": "GEMI-EVT1-YES",
                    "label": "Yes",
                    "status": "active",
                    "marketState": "open",
                    "totalShares": "100",
                    "prices": {
                        "bestBid": "0.26",
                        "bestAsk": "0.28",
                        "lastTradePrice": "0.29",
                    },
                    "effectiveDate": "2026-08-09T00:00:00Z",
                    "expiryDate": "2026-08-10T00:00:00Z",
                },
                {"id": "c2", "instrumentSymbol": "GEMI-EVT1-NO", "prices": {}},
            ],
        }],
        "pagination": {"limit": 500, "offset": 0, "total": 501},
    }
    page = adapter.parse_page(payload, params=params, observation=obs())
    assert len(page.rows) == 1
    assert len(page.contract_rows) == 2
    row = page.rows[0]
    assert row["source_event_id"] == "evt_1"
    assert row["contract_count_source"] == 2
    assert row["volume_source"] == "10"
    contract = page.contract_rows[0]
    assert contract["source_contract_ticker"] == "GEMI-EVT1-YES"
    assert contract["best_bid_source"] == "0.26"
    assert contract["best_ask_source"] == "0.28"
    assert contract["last_trade_price_source"] == "0.29"
    assert contract["total_shares_source"] == "100"
    assert contract["yes_price_source"] == ""
    assert contract["quote_semantics_source"] == "gemini_contract_best_bid_ask"
    assert page.next_params["offset"] == 500


def test_polymarket_event_and_market_quote_snapshots_keep_fee_coefficient_source_native():
    adapter = PolymarketUSDiscoveryAdapter()
    params = adapter.initial_params()
    params["limit"] = 2
    payload = {
        "events": [
            {
                "id": "evt123",
                "ticker": "EVT123",
                "slug": "event-123",
                "title": "Event 123",
                "subtitle": "Subtitle",
                "category": "sports",
                "active": True,
                "closed": False,
                "archived": False,
                "startDate": "2026-08-09T00:00:00Z",
                "endDate": "2026-08-10T00:00:00Z",
                "seriesSlug": "nfl",
                "markets": [
                    {
                        "id": "m1",
                        "slug": "market-1",
                        "question": "Market 1?",
                        "active": True,
                        "closed": False,
                        "archived": False,
                        "sportsMarketTypeV2": "MONEYLINE",
                        "bestBidQuote": {"value": "0.4910", "currency": "USD"},
                        "bestAskQuote": {"value": "0.4920", "currency": "USD"},
                        "feeCoefficient": 0.06,
                        "startDate": "2026-08-09T00:00:00Z",
                        "endDate": "2026-08-10T00:00:00Z",
                    }
                ],
            }
        ]
    }
    page = adapter.parse_page(payload, params=params, observation=obs())
    assert len(page.rows) == 1
    assert len(page.contract_rows) == 1
    assert page.rows[0]["contract_count_source"] == 1
    contract = page.contract_rows[0]
    assert contract["best_bid_source"] == "0.4910"
    assert contract["best_ask_source"] == "0.4920"
    assert contract["fee_coefficient_source"] == 0.06
    assert contract["quote_semantics_source"] == "polymarket_us_market_best_bid_ask"
    assert page.next_params is None


def test_polymarket_malformed_quote_object_fails_closed():
    adapter = PolymarketUSDiscoveryAdapter()
    payload = {
        "events": [{
            "id": "evt",
            "active": True,
            "markets": [{"id": "m1", "bestBidQuote": "0.4"}],
        }]
    }
    params = adapter.initial_params()
    params["limit"] = 2
    with pytest.raises(CensusAdapterError, match="bestBidQuote"):
        adapter.parse_page(payload, params=params, observation=obs())


def test_crypto_com_preserves_display_yes_no_chance_without_calling_them_bid_ask():
    adapter = CryptoComDiscoveryAdapter()
    payload = {
        "data": [{
            "id": "evt",
            "title": "Event",
            "kind": "NFL",
            "type": "match",
            "status": "active",
            "market_format": "head_to_head",
            "event_date": "2026-08-09T20:00:00Z",
            "contracts_count": 1,
            "contracts": [
                {
                    "id": "c1",
                    "symbol": "NFL-C1",
                    "title": "Team",
                    "status": "active",
                    "chance": "64.00",
                    "yes": "0.64",
                    "no": "0.42",
                    "payout_per_100": "156.25",
                    "market_type": {"name": "Moneyline"},
                }
            ],
        }],
        "pagination": {"has_more": False, "limit": 50, "next_cursor": None},
    }
    page = adapter.parse_page(
        payload, params=adapter.initial_params(), observation=obs()
    )
    assert len(page.rows) == 1
    assert len(page.contract_rows) == 1
    row = page.rows[0]
    assert row["contract_count_source"] == 1
    contract = page.contract_rows[0]
    assert contract["yes_price_source"] == "0.64"
    assert contract["no_price_source"] == "0.42"
    assert contract["reference_probability_source"] == "64.00"
    assert contract["payout_per_100_source"] == "156.25"
    assert contract["best_bid_source"] == ""
    assert contract["best_ask_source"] == ""
    assert contract["quote_semantics_source"] == "crypto_com_display_yes_no_chance"


def test_crypto_com_has_more_requires_cursor():
    adapter = CryptoComDiscoveryAdapter()
    payload = {"data": [], "pagination": {"has_more": True, "next_cursor": None}}
    with pytest.raises(CensusAdapterError, match="next_cursor"):
        adapter.parse_page(
            payload, params=adapter.initial_params(), observation=obs()
        )


def test_malformed_event_container_fails_closed():
    adapter = KalshiDiscoveryAdapter()
    with pytest.raises(CensusAdapterError, match="must be a list"):
        adapter.parse_page(
            {"events": {}},
            params=adapter.initial_params(),
            observation=obs(),
        )

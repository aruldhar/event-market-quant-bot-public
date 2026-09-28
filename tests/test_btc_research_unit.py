from __future__ import annotations

from dataclasses import dataclass
import json
import unittest

from src.btc_research_unit import (
    BtcResearchUnitError,
    collect_btc_research_unit_rows,
    classify_bitcoin_event,
    classify_bitcoin_series,
)


@dataclass(frozen=True)
class _RawRef:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class _Response:
    payload: dict
    raw_record: _RawRef


class _FakeClient:
    def __init__(self):
        self.calls = []
        self._counter = 0

    def _response(self, payload):
        self._counter += 1
        return _Response(
            payload,
            _RawRef("kalshi_public_rest", "s1", f"r{self._counter}"),
        )

    def get_json(self, path, *, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if path == "/historical/cutoff":
            return self._response({
                "market_settled_ts": "2026-06-09T00:00:00Z",
                "trades_created_ts": "2026-06-09T00:00:00Z",
                "orders_updated_ts": "2026-06-09T00:00:00Z",
            })
        if path == "/series":
            self.assert_series_params(params)
            return self._response({
                "series": [
                    {
                        "ticker": "KXBTC15M",
                        "category": "Crypto",
                        "title": "Bitcoin price up in next 15 minutes",
                        "tags": ["Bitcoin"],
                    },
                    {
                        "ticker": "KXBTCLADDER",
                        "category": "Crypto",
                        "title": "Bitcoin price ladder",
                        "tags": ["Bitcoin"],
                    },
                    {
                        "ticker": "KXETHMAXY",
                        "category": "Crypto",
                        "title": "Ethereum yearly maximum",
                        "tags": ["Ethereum"],
                    },
                ]
            })
        if path == "/events":
            series = params["series_ticker"]
            if series == "KXBTC15M":
                return self._response({
                    "events": [
                        {
                            "event_ticker": "KXBTC15M-E1",
                            "series_ticker": "KXBTC15M",
                            "category": "Crypto",
                            "title": "Bitcoin price up in next 15 mins?",
                            "sub_title": "BTC",
                            "mutually_exclusive": False,
                        },
                        {
                            "event_ticker": "KXBTC15M-E2",
                            "series_ticker": "KXBTC15M",
                            "category": "Crypto",
                            "title": "Bitcoin price up in next 15 mins?",
                            "sub_title": "BTC",
                            "mutually_exclusive": False,
                        },
                    ],
                    "cursor": "",
                })
            if series == "KXBTCLADDER":
                return self._response({
                    "events": [
                        {
                            "event_ticker": "KXBTCLADDER-E1",
                            "series_ticker": "KXBTCLADDER",
                            "category": "Crypto",
                            "title": "Price at noon",
                            "sub_title": "",
                            "mutually_exclusive": True,
                        }
                    ],
                    "cursor": "",
                })
            raise AssertionError(series)
        if path == "/historical/markets":
            event = params["event_ticker"]
            by_event = {
                "KXBTC15M-E1": [
                    {
                        "ticker": "KXBTC15M-M1",
                        "event_ticker": "KXBTC15M-E1",
                        "market_type": "binary",
                        "open_time": "2026-05-01T00:00:00Z",
                        "close_time": "2026-05-01T00:15:00Z",
                        "settlement_ts": "2026-05-01T00:16:00Z",
                        "rules_primary": "official rule text",
                        "rules_secondary": "secondary text",
                        "result": "yes",
                        "settlement_value_dollars": "99999.99",
                    }
                ],
                "KXBTC15M-E2": [
                    {
                        "ticker": "KXBTC15M-M2",
                        "event_ticker": "KXBTC15M-E2",
                        "market_type": "binary",
                        "open_time": "2026-05-01T00:15:00Z",
                        "close_time": "2026-05-01T00:30:00Z",
                        "settlement_ts": "2026-05-01T00:31:00Z",
                        "rules_primary": "official rule text",
                        "rules_secondary": "secondary text",
                        "result": "no",
                        "expiration_value": "12345.67",
                    }
                ],
                "KXBTCLADDER-E1": [
                    {
                        "ticker": "KXBTCLADDER-M1",
                        "event_ticker": "KXBTCLADDER-E1",
                        "market_type": "binary",
                        "open_time": "2026-05-02T00:00:00Z",
                        "close_time": "2026-05-03T00:00:00Z",
                        "settlement_ts": "2026-05-03T00:01:00Z",
                        "strike_type": "greater",
                        "floor_strike": 70000,
                        "result": "yes",
                    },
                    {
                        "ticker": "KXBTCLADDER-M2",
                        "event_ticker": "KXBTCLADDER-E1",
                        "market_type": "binary",
                        "open_time": "2026-05-02T00:00:00Z",
                        "close_time": "2026-05-03T00:00:00Z",
                        "settlement_ts": "2026-05-03T00:01:00Z",
                        "strike_type": "greater",
                        "floor_strike": 75000,
                        "result": "no",
                    },
                ],
            }
            return self._response({"markets": by_event.get(event, []), "cursor": ""})
        if path == "/markets":
            return self._response({"markets": [], "cursor": ""})
        raise AssertionError((path, params))

    @staticmethod
    def assert_series_params(params):
        assert params["category"] == "Crypto"
        assert params["include_product_metadata"] == "false"
        assert params["include_volume"] == "false"


class BtcResearchUnitTests(unittest.TestCase):
    def test_series_classifier_separates_bitcoin_and_cross_asset(self):
        self.assertEqual(
            classify_bitcoin_series({
                "category": "Crypto",
                "ticker": "KXBTCMINY",
                "title": "Bitcoin minimum",
                "tags": ["Bitcoin"],
            })["bitcoin_scope"],
            "bitcoin_only",
        )
        self.assertEqual(
            classify_bitcoin_series({
                "category": "Crypto",
                "ticker": "KXBTCETHATH",
                "title": "BTC versus ETH",
                "tags": [],
            })["bitcoin_scope"],
            "bitcoin_cross_asset",
        )
        self.assertEqual(
            classify_bitcoin_series({
                "category": "Crypto",
                "ticker": "KXETHMAXY",
                "title": "Ethereum max",
                "tags": ["Ethereum"],
            })["bitcoin_scope"],
            "not_bitcoin",
        )

    def test_event_classifier_can_inherit_selected_series_scope(self):
        scope = classify_bitcoin_event(
            {
                "category": "Crypto",
                "series_ticker": "KXLADDER",
                "title": "Price at noon",
            },
            series_scope={
                "bitcoin_scope": "bitcoin_only",
                "scope_confidence": "medium",
            },
        )
        self.assertEqual(scope["bitcoin_scope"], "bitcoin_only")
        self.assertEqual(
            scope["scope_reason"],
            "bitcoin_identity_inherited_from_selected_series_metadata",
        )

    def test_inventory_is_outcome_blind_and_clusters_contract_fanout(self):
        rows = collect_btc_research_unit_rows(_FakeClient(), run_id="run-1")
        self.assertEqual(rows.bitcoin_series_count, 2)
        self.assertEqual(len(rows.events), 3)
        self.assertEqual(len(rows.markets), 4)
        self.assertTrue(all("result" not in row for row in rows.markets))
        self.assertTrue(
            all("settlement_value_dollars" not in row for row in rows.markets)
        )
        ladder = [
            row for row in rows.markets if row["series_ticker"] == "KXBTCLADDER"
        ]
        self.assertEqual(len({row["settlement_cluster_id"] for row in ladder}), 1)
        self.assertEqual(
            ladder[0]["cluster_status"], "candidate_requires_rule_validation"
        )
        cluster = next(
            row
            for row in rows.clusters
            if row["settlement_cluster_id"] == ladder[0]["settlement_cluster_id"]
        )
        self.assertEqual(cluster["market_count"], "2")
        self.assertEqual(cluster["event_count"], "1")


    def test_mixed_strike_metadata_does_not_split_candidate_dependence_cluster(self):
        class MixedStrikeMetadataClient(_FakeClient):
            def get_json(self, path, *, params=None):
                params = dict(params or {})
                response = super().get_json(path, params=params)
                if (
                    path == "/historical/markets"
                    and params.get("event_ticker") == "KXBTCLADDER-E1"
                ):
                    payload = dict(response.payload)
                    markets = [dict(item) for item in payload["markets"]]
                    markets[1].pop("strike_type", None)
                    markets[1].pop("floor_strike", None)
                    payload["markets"] = markets
                    return _Response(payload, response.raw_record)
                return response

        rows = collect_btc_research_unit_rows(
            MixedStrikeMetadataClient(), run_id="run-mixed-strikes"
        )
        ladder = [
            row for row in rows.markets if row["series_ticker"] == "KXBTCLADDER"
        ]
        self.assertEqual(len(ladder), 2)
        self.assertEqual(len({row["settlement_cluster_id"] for row in ladder}), 1)
        self.assertEqual(
            {row["settlement_family"] for row in ladder},
            {"same_event_close_candidate"},
        )
        cluster = next(
            row
            for row in rows.clusters
            if row["settlement_cluster_id"] == ladder[0]["settlement_cluster_id"]
        )
        self.assertEqual(cluster["market_count"], "2")
        self.assertEqual(cluster["settlement_family"], "same_event_close_candidate")

    def test_adjacent_kxbtc15m_clusters_share_boundary_primitive(self):
        rows = collect_btc_research_unit_rows(_FakeClient(), run_id="run-2")
        resolved = [
            row for row in rows.markets if row["series_ticker"] == "KXBTC15M"
        ]
        self.assertEqual(len(resolved), 2)
        self.assertTrue(all(row["cluster_status"] == "resolved" for row in resolved))
        p1 = set(json.loads(resolved[0]["primitive_ids_json"]))
        p2 = set(json.loads(resolved[1]["primitive_ids_json"]))
        shared = p1.intersection(p2)
        self.assertEqual(len(shared), 1)
        self.assertEqual(len(rows.overlaps), 1)
        self.assertEqual(rows.overlaps[0]["primitive_id"], next(iter(shared)))
        self.assertEqual(
            rows.overlaps[0]["split_policy"], "same_partition_or_boundary_embargo"
        )

    def test_discovery_is_series_first_and_never_queries_non_btc_series_events(self):
        client = _FakeClient()
        rows = collect_btc_research_unit_rows(client, run_id="run-3")
        self.assertEqual(rows.bitcoin_series_count, 2)
        queried_event_series = {
            params["series_ticker"]
            for path, params in client.calls
            if path == "/events"
        }
        self.assertEqual(queried_event_series, {"KXBTC15M", "KXBTCLADDER"})
        self.assertNotIn("KXETHMAXY", queried_event_series)
        for path, params in client.calls:
            if path == "/events":
                self.assertEqual(params["status"], "settled")
                self.assertIn("series_ticker", params)


    def test_selected_crypto_series_can_return_deprecated_non_crypto_event_category(self):
        class DeprecatedEventCategoryClient(_FakeClient):
            def get_json(self, path, *, params=None):
                params = dict(params or {})
                response = super().get_json(path, params=params)
                if path == "/events" and params.get("series_ticker") == "KXBTC15M":
                    payload = dict(response.payload)
                    events = [dict(item) for item in payload["events"]]
                    events[0]["category"] = "Financials"
                    events[1]["category"] = ""
                    payload["events"] = events
                    return _Response(payload, response.raw_record)
                return response

        rows = collect_btc_research_unit_rows(
            DeprecatedEventCategoryClient(), run_id="run-category"
        )
        kxbtc15m_events = [
            row for row in rows.events if row["series_ticker"] == "KXBTC15M"
        ]
        self.assertEqual(len(kxbtc15m_events), 2)
        self.assertEqual(
            {row["category"] for row in kxbtc15m_events}, {"Financials", ""}
        )
        self.assertEqual(rows.event_category_mismatch_count, 2)
        self.assertTrue(
            all(row["bitcoin_scope"] == "bitcoin_only" for row in kxbtc15m_events)
        )

    def test_wrong_series_ticker_still_fails_closed(self):
        class WrongSeriesClient(_FakeClient):
            def get_json(self, path, *, params=None):
                params = dict(params or {})
                response = super().get_json(path, params=params)
                if path == "/events" and params.get("series_ticker") == "KXBTC15M":
                    payload = dict(response.payload)
                    events = [dict(item) for item in payload["events"]]
                    events[0]["series_ticker"] = "KXETHMAXY"
                    payload["events"] = events
                    return _Response(payload, response.raw_record)
                return response

        with self.assertRaises(BtcResearchUnitError) as ctx:
            collect_btc_research_unit_rows(WrongSeriesClient(), run_id="run-wrong-series")
        self.assertIn("returned event from KXETHMAXY", str(ctx.exception))


    def test_historical_market_query_is_event_scoped(self):
        client = _FakeClient()
        collect_btc_research_unit_rows(client, run_id="run-historical-filter")
        historical_calls = [
            params for path, params in client.calls if path == "/historical/markets"
        ]
        self.assertGreater(len(historical_calls), 0)
        for params in historical_calls:
            self.assertIn("event_ticker", params)
            self.assertNotIn("series_ticker", params)
            self.assertNotIn("mve_filter", params)
            self.assertNotIn("status", params)

    def test_live_market_query_keeps_supported_mve_exclusion(self):
        client = _FakeClient()
        collect_btc_research_unit_rows(client, run_id="run-live-filter")
        live_calls = [params for path, params in client.calls if path == "/markets"]
        self.assertGreater(len(live_calls), 0)
        for params in live_calls:
            self.assertIn("event_ticker", params)
            self.assertNotIn("series_ticker", params)
            self.assertEqual(params.get("mve_filter"), "exclude")
            self.assertEqual(params.get("status"), "settled")

    def test_per_series_event_pagination_guard_fails_closed(self):
        class EndlessBtcEvents(_FakeClient):
            def get_json(self, path, *, params=None):
                params = dict(params or {})
                if path == "/events" and params.get("series_ticker") == "KXBTC15M":
                    self.calls.append((path, params))
                    return self._response({"events": [], "cursor": "still-more"})
                return super().get_json(path, params=params)

        with self.assertRaises(BtcResearchUnitError) as ctx:
            collect_btc_research_unit_rows(
                EndlessBtcEvents(),
                run_id="run-4",
                max_event_pages_per_series=1,
            )
        self.assertIn("BTC series KXBTC15M", str(ctx.exception))
        self.assertIn("partial BTC structure inventory is not accepted", str(ctx.exception))

    def test_event_sample_cap_is_deterministic_and_bounds_market_requests(self):
        class ManyEventsClient(_FakeClient):
            def get_json(self, path, *, params=None):
                params = dict(params or {})
                if path == "/series":
                    self.calls.append((path, params))
                    return self._response({
                        "series": [{
                            "ticker": "KXBTCLADDER",
                            "category": "Crypto",
                            "title": "Bitcoin price ladder",
                            "tags": ["Bitcoin"],
                        }]
                    })
                if path == "/events":
                    self.calls.append((path, params))
                    events = [
                        {
                            "event_ticker": f"KXBTCLADDER-E{i:02d}",
                            "series_ticker": "KXBTCLADDER",
                            "category": "Crypto",
                            "title": "Bitcoin ladder",
                            "mutually_exclusive": True,
                        }
                        for i in range(30)
                    ]
                    return self._response({"events": events, "cursor": ""})
                if path == "/historical/markets":
                    self.calls.append((path, params))
                    event = params["event_ticker"]
                    return self._response({
                        "markets": [{
                            "ticker": f"{event}-M1",
                            "event_ticker": event,
                            "market_type": "binary",
                            "open_time": "2026-05-01T00:00:00Z",
                            "close_time": "2026-05-02T00:00:00Z",
                            "settlement_ts": "2026-05-02T00:01:00Z",
                        }],
                        "cursor": "",
                    })
                if path == "/markets":
                    self.calls.append((path, params))
                    return self._response({"markets": [], "cursor": ""})
                return super().get_json(path, params=params)

        client = ManyEventsClient()
        rows = collect_btc_research_unit_rows(
            client, run_id="run-sample", events_per_series=5
        )
        self.assertEqual(rows.discovered_settled_event_count, 30)
        self.assertEqual(rows.sampled_event_count, 5)
        self.assertEqual(len(rows.events), 5)
        historical_event_calls = [
            params["event_ticker"]
            for path, params in client.calls
            if path == "/historical/markets"
        ]
        self.assertEqual(set(historical_event_calls), {row["event_ticker"] for row in rows.events})
        summary = rows.series_summary[0]
        self.assertEqual(summary["discovered_settled_event_count"], "30")
        self.assertEqual(summary["sampled_event_count"], "5")
        self.assertEqual(summary["event_sampling_rule"], "sha256_event_ticker_ascending")

    def test_per_event_market_pagination_guard_fails_closed(self):
        class EndlessHistoricalMarkets(_FakeClient):
            def get_json(self, path, *, params=None):
                params = dict(params or {})
                if path == "/historical/markets":
                    self.calls.append((path, params))
                    event = params["event_ticker"]
                    return self._response({
                        "markets": [{
                            "ticker": f"{event}-M",
                            "event_ticker": event,
                            "market_type": "binary",
                            "open_time": "2026-05-01T00:00:00Z",
                            "close_time": "2026-05-01T00:15:00Z",
                            "settlement_ts": "2026-05-01T00:16:00Z",
                        }],
                        "cursor": "still-more",
                    })
                return super().get_json(path, params=params)

        with self.assertRaises(BtcResearchUnitError) as ctx:
            collect_btc_research_unit_rows(
                EndlessHistoricalMarkets(),
                run_id="run-market-guard",
                max_market_pages_per_event_per_tier=1,
            )
        self.assertIn("/historical/markets for event", str(ctx.exception))

    def test_no_btc_identifiable_series_fails_closed(self):
        class NoBtcSeries(_FakeClient):
            def get_json(self, path, *, params=None):
                if path == "/series":
                    return self._response({
                        "series": [
                            {
                                "ticker": "KXETHMAXY",
                                "category": "Crypto",
                                "title": "Ethereum max",
                                "tags": ["Ethereum"],
                            }
                        ]
                    })
                return super().get_json(path, params=params)

        with self.assertRaises(BtcResearchUnitError):
            collect_btc_research_unit_rows(NoBtcSeries(), run_id="run-5")


if __name__ == "__main__":
    unittest.main()

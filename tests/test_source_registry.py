from __future__ import annotations

import copy
import unittest

from src.source_registry import (
    SourceRegistryError,
    load_source_registry,
    summarize_source_registry,
    validate_source_registry_document,
)


PUBLIC_CENSUS_SOURCES = {
    "kalshi.public_rest.events.v1": "kalshi_public_rest",
    "gemini.prediction_markets.public_rest.events.v1": "gemini_predictions_public_rest",
    "polymarket_us.public_rest.markets.v1": "polymarket_us_public_rest",
    "polymarket_us.public_rest.events.v1": "polymarket_us_public_rest",
    "crypto_com.predictions.public_rest.events.v1": "crypto_com_predictions_public_rest",
}

CHECKPOINT08_HISTORICAL_SOURCES = {
    "kalshi.public_rest.historical_cutoff.v1",
    "kalshi.public_rest.historical_markets.v1",
    "kalshi.public_rest.historical_market.v1",
    "kalshi.public_rest.event.v1",
    "kalshi.public_rest.historical_market_candlesticks.v1",
    "kalshi.public_rest.historical_trades.v1",
    "kalshi.public_rest.market_candlesticks.v1",
}


class SourceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_source_registry("configs/source_registry.json")

    def test_bundled_registry_is_valid_and_summarized(self) -> None:
        summary = summarize_source_registry(self.registry)
        self.assertEqual(summary["schema"], "source_registry.v1")
        self.assertEqual(summary["source_count"], 23)
        self.assertEqual(summary["quality_policy_count"], 1)
        self.assertEqual(summary["validated_source_count"], 17)
        self.assertEqual(summary["unresolved_source_count"], 0)
        self.assertEqual(summary["unresolved_settlement_source_count"], 1)

    def test_public_census_sources_are_registered_and_unauthenticated(self) -> None:
        sources = {source["source_id"]: source for source in self.registry["sources"]}
        for source_id, raw_source_name in PUBLIC_CENSUS_SOURCES.items():
            with self.subTest(source_id=source_id):
                source = sources[source_id]
                self.assertEqual(source["transport"], "https_rest")
                self.assertEqual(source["endpoint_identity"]["method"], "GET")
                self.assertEqual(source["authentication"]["mode"], "none")
                self.assertEqual(source["settlement_role"], "none")
                self.assertEqual(source["raw_source_name"], raw_source_name)
                self.assertIn("opportunity_census", source["roles"])
                self.assertTrue(source["evidence"])

    def test_checkpoint08_sources_are_validated_active_public_sources(self) -> None:
        sources = {source["source_id"]: source for source in self.registry["sources"]}
        self.assertTrue(CHECKPOINT08_HISTORICAL_SOURCES.issubset(sources))
        for source_id in CHECKPOINT08_HISTORICAL_SOURCES:
            with self.subTest(source_id=source_id):
                source = sources[source_id]
                self.assertEqual(source["transport"], "https_rest")
                self.assertEqual(source["endpoint_identity"]["method"], "GET")
                self.assertEqual(source["authentication"]["mode"], "none")
                self.assertEqual(source["authentication"]["validation_state"], "validated")
                self.assertEqual(source["collection_state"], "active")
                self.assertEqual(source["validation_state"], "validated")
                self.assertEqual(source["raw_source_name"], "kalshi_public_rest")
                self.assertTrue(source["evidence"])

    def test_public_sources_are_in_fail_closed_policy_scope(self) -> None:
        policy = next(
            policy
            for policy in self.registry["quality_policies"]
            if policy["policy_id"] == "read_only_source_quality.v1"
        )
        scope = set(policy["scope_source_ids"])
        self.assertTrue(set(PUBLIC_CENSUS_SOURCES).issubset(scope))
        self.assertTrue(CHECKPOINT08_HISTORICAL_SOURCES.issubset(scope))
        self.assertEqual(policy["decision_use_default"], "blocked")

    def test_event_first_census_sources_use_event_endpoints(self) -> None:
        sources = {source["source_id"]: source for source in self.registry["sources"]}
        self.assertEqual(
            sources["kalshi.public_rest.events.v1"]["endpoint_identity"]["path_template"],
            "/events",
        )
        self.assertEqual(
            sources["polymarket_us.public_rest.events.v1"]["endpoint_identity"]["path_template"],
            "/v1/events",
        )

    def test_documented_websocket_source_uses_wss_subscription_identity(self) -> None:
        source = next(
            source
            for source in self.registry["sources"]
            if source["source_id"] == "kalshi.cfbenchmarks_value.websocket.v1"
        )
        self.assertEqual(source["transport"], "wss")
        self.assertEqual(source["endpoint_identity"]["method"], "SUBSCRIBE")
        self.assertTrue(source["endpoint_identity"]["base_url"].startswith("wss://"))
        self.assertEqual(source["authentication"]["mode"], "kalshi_signed")
        self.assertEqual(source["collection_state"], "documented_not_collected")

    def test_websocket_transport_rejects_non_subscription_method(self) -> None:
        registry = copy.deepcopy(self.registry)
        source = next(
            source
            for source in registry["sources"]
            if source["source_id"] == "kalshi.cfbenchmarks_value.websocket.v1"
        )
        source["endpoint_identity"]["method"] = "GET"
        with self.assertRaisesRegex(
            SourceRegistryError,
            "must be SUBSCRIBE when transport is 'wss'",
        ):
            validate_source_registry_document(registry)

    def test_websocket_transport_rejects_https_base_url(self) -> None:
        registry = copy.deepcopy(self.registry)
        source = next(
            source
            for source in registry["sources"]
            if source["source_id"] == "kalshi.cfbenchmarks_value.websocket.v1"
        )
        source["endpoint_identity"]["base_url"] = (
            "https://external-api-ws.kalshi.com/trade-api/ws/v2"
        )
        with self.assertRaisesRegex(SourceRegistryError, "must be a wss URL"):
            validate_source_registry_document(registry)

    def test_duplicate_source_id_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["sources"][1]["source_id"] = registry["sources"][0]["source_id"]
        with self.assertRaisesRegex(SourceRegistryError, "Duplicate source_id"):
            validate_source_registry_document(registry)

    def test_unknown_quality_policy_reference_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["quality_policy_id"] = "missing.policy.v1"
        with self.assertRaisesRegex(SourceRegistryError, "unknown quality policy"):
            validate_source_registry_document(registry)

    def test_non_https_official_url_is_rejected(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["official_urls"][0] = "http://example.invalid"
        with self.assertRaisesRegex(SourceRegistryError, "must be an https URL"):
            validate_source_registry_document(registry)

    def test_required_fail_closed_state_cannot_be_removed(self) -> None:
        registry = copy.deepcopy(self.registry)
        conditions = registry["quality_policies"][0]["conditions"]
        registry["quality_policies"][0]["conditions"] = [
            condition for condition in conditions if condition["state"] != "clock_error"
        ]
        with self.assertRaisesRegex(SourceRegistryError, "missing fail-closed states"):
            validate_source_registry_document(registry)

    def test_quality_condition_cannot_allow_decision_use(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["quality_policies"][0]["conditions"][0]["decision_action"] = "allow"
        with self.assertRaisesRegex(SourceRegistryError, "must be 'block'"):
            validate_source_registry_document(registry)

    def test_documented_source_requires_evidence(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["sources"][-1]["evidence"] = []
        with self.assertRaisesRegex(SourceRegistryError, "evidence must not be empty"):
            validate_source_registry_document(registry)

    def test_policy_scope_must_include_referencing_source(self) -> None:
        registry = copy.deepcopy(self.registry)
        source_id = registry["sources"][0]["source_id"]
        registry["quality_policies"][0]["scope_source_ids"].remove(source_id)
        with self.assertRaisesRegex(SourceRegistryError, "does not include source"):
            validate_source_registry_document(registry)


if __name__ == "__main__":
    unittest.main()

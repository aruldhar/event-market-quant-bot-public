from __future__ import annotations

import copy
import unittest

from src.checkpoint08_source_registry import (
    CHECKPOINT08_SOURCE_IDS,
    REVIEWED_AT_UTC,
    apply_checkpoint08_registry_updates,
    checkpoint08_sources,
)


class Checkpoint08SourceRegistryMigrationTests(unittest.TestCase):
    def _base_registry(self) -> dict:
        return {
            "schema": "source_registry.v1",
            "registry_id": "event_market_quant_bot.sources",
            "reviewed_at_utc": "2026-08-09T03:55:00Z",
            "sources": [
                {
                    "source_id": "kalshi.public_rest.events.v1",
                    "roles": ["event_discovery"],
                    "authentication": {"validation_state": "documented"},
                    "collection_state": "proposed",
                    "validation_state": "documented",
                    "notes": "old",
                }
            ],
            "quality_policies": [
                {
                    "policy_id": "read_only_source_quality.v1",
                    "scope_source_ids": ["kalshi.public_rest.events.v1"],
                }
            ],
        }

    def test_canonical_source_ids_are_unique(self) -> None:
        sources = checkpoint08_sources()
        ids = [source["source_id"] for source in sources]
        self.assertEqual(tuple(ids), CHECKPOINT08_SOURCE_IDS)
        self.assertEqual(len(ids), len(set(ids)))

    def test_migration_adds_sources_updates_event_source_and_policy_scope(self) -> None:
        original = self._base_registry()
        migrated = apply_checkpoint08_registry_updates(original)
        self.assertEqual(original["sources"][0]["collection_state"], "proposed")
        self.assertEqual(migrated["reviewed_at_utc"], REVIEWED_AT_UTC)

        by_id = {source["source_id"]: source for source in migrated["sources"]}
        self.assertTrue(set(CHECKPOINT08_SOURCE_IDS).issubset(by_id))
        event = by_id["kalshi.public_rest.events.v1"]
        self.assertEqual(event["collection_state"], "active")
        self.assertEqual(event["validation_state"], "validated")
        self.assertEqual(event["authentication"]["validation_state"], "validated")
        self.assertIn("sports_historical_validation", event["roles"])

        policy = migrated["quality_policies"][0]
        self.assertTrue(set(CHECKPOINT08_SOURCE_IDS).issubset(policy["scope_source_ids"]))

    def test_migration_is_idempotent(self) -> None:
        once = apply_checkpoint08_registry_updates(self._base_registry())
        twice = apply_checkpoint08_registry_updates(copy.deepcopy(once))
        self.assertEqual(once, twice)

    def test_partial_prior_migration_is_rejected(self) -> None:
        registry = self._base_registry()
        registry["sources"].append(checkpoint08_sources()[0])
        with self.assertRaisesRegex(ValueError, "partial Checkpoint-08 source migration"):
            apply_checkpoint08_registry_updates(registry)


if __name__ == "__main__":
    unittest.main()

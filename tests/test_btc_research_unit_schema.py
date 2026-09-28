from __future__ import annotations

import unittest

from src.btc_research_unit_schema import (
    CLUSTER_FIELDS,
    EVENT_FIELDS,
    FORBIDDEN_DERIVED_FIELDS,
    MARKET_FIELDS,
    OVERLAP_FIELDS,
    SERIES_SUMMARY_FIELDS,
    validate_schema_contract,
)


class BtcResearchUnitSchemaTests(unittest.TestCase):
    def test_schema_contract_is_valid(self):
        validate_schema_contract()

    def test_no_derived_schema_materializes_outcome_or_market_state_fields(self):
        for fields in (
            EVENT_FIELDS,
            MARKET_FIELDS,
            CLUSTER_FIELDS,
            OVERLAP_FIELDS,
            SERIES_SUMMARY_FIELDS,
        ):
            self.assertFalse(FORBIDDEN_DERIVED_FIELDS.intersection(fields))

    def test_market_schema_carries_cluster_identity(self):
        self.assertIn("settlement_cluster_id", MARKET_FIELDS)
        self.assertIn("cluster_status", MARKET_FIELDS)
        self.assertIn("primitive_ids_json", MARKET_FIELDS)


if __name__ == "__main__":
    unittest.main()

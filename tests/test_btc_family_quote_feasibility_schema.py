from __future__ import annotations

import unittest

from src.btc_family_quote_feasibility_schema import (
    CLUSTER_FIELDS, OBSERVATION_FIELDS, PROBE_FIELDS, SUMMARY_FIELDS, WINDOW_FIELDS,
)


class BtcFamilyQuoteFeasibilitySchemaTests(unittest.TestCase):
    def test_no_outcome_fields(self):
        for fields in (CLUSTER_FIELDS, PROBE_FIELDS, WINDOW_FIELDS, OBSERVATION_FIELDS, SUMMARY_FIELDS):
            self.assertNotIn("result", fields)
            self.assertNotIn("settlement_value", fields)

    def test_observation_keeps_exact_time(self):
        self.assertIn("time_to_close_seconds", OBSERVATION_FIELDS)
        self.assertIn("normalized_time_remaining", OBSERVATION_FIELDS)
        self.assertIn("end_period_ts", OBSERVATION_FIELDS)


if __name__ == "__main__":
    unittest.main()

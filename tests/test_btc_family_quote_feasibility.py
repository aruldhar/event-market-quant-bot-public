from __future__ import annotations

from dataclasses import dataclass
import json
import unittest

from src.btc_family_quote_feasibility import (
    BtcFamilyQuoteFeasibilityError,
    build_observation_rows,
    build_summary_rows,
    normalized_time_band,
    select_structural_probe_markets,
)
from src.btc_family_quote_feasibility_schema import (
    OBSERVATION_FIELDS,
    TARGET_CLUSTERS_PER_FAMILY,
)


@dataclass(frozen=True)
class _Raw:
    source: str = "kalshi_public_rest"
    session_id: str = "session"
    request_id: str = "request"


@dataclass(frozen=True)
class _Response:
    payload: dict
    raw_record: _Raw = _Raw()


class BtcFamilyQuoteFeasibilityTests(unittest.TestCase):
    def test_normalized_bands_use_exact_thirds(self):
        self.assertEqual(normalized_time_band(60, 60), "early")
        self.assertEqual(normalized_time_band(40, 60), "early")
        self.assertEqual(normalized_time_band(39, 60), "middle")
        self.assertEqual(normalized_time_band(20, 60), "middle")
        self.assertEqual(normalized_time_band(19, 60), "late")
        self.assertEqual(normalized_time_band(0, 60), "late")

    def test_time_outside_active_lifetime_fails(self):
        with self.assertRaises(BtcFamilyQuoteFeasibilityError):
            normalized_time_band(61, 60)

    def test_structural_probes_are_q25_q50_q75(self):
        rows = [
            {
                "ticker": f"T{i:02d}",
                "floor_strike": str(i * 100),
                "cap_strike": str(i * 100 + 99),
                "functional_strike": "",
            }
            for i in range(9)
        ]
        selected = select_structural_probe_markets(rows)
        self.assertEqual([row["ticker"] for row in selected], ["T02", "T04", "T06"])

    def test_structural_probe_selection_never_uses_quote_or_outcome_fields(self):
        rows = [
            {
                "ticker": f"T{i}", "floor_strike": str(i), "cap_strike": "",
                "functional_strike": "", "result": "yes" if i % 2 else "no",
                "yes_bid": str(0.99 - i / 100),
            }
            for i in range(8)
        ]
        selected_a = [row["ticker"] for row in select_structural_probe_markets(rows)]
        for row in rows:
            row["result"] = "CHANGED"
            row["yes_bid"] = "0.01"
        selected_b = [row["ticker"] for row in select_structural_probe_markets(rows)]
        self.assertEqual(selected_a, selected_b)

    def test_observation_builder_preserves_exact_time_to_close(self):
        from datetime import datetime, timezone
        open_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        close_time = datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc)
        response = _Response({
            "ticker": "T",
            "candlesticks": [
                {
                    "end_period_ts": int(datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc).timestamp()),
                    "yes_bid": {"close": "0.40"},
                    "yes_ask": {"close": "0.42"},
                }
            ],
        })
        rows = build_observation_rows(
            run_id="run", inventory_run_id="inventory", family="KXBTC",
            event_ticker="E", cluster_id="C", ticker="T", probe_role="q50",
            open_time=open_time, close_time=close_time, route_tier="historical",
            response=response,
        )
        self.assertEqual(rows[0]["time_to_close_seconds"], "120")
        self.assertEqual(rows[0]["normalized_time_remaining"], "0.666667")
        self.assertEqual(rows[0]["time_band"], "early")
        self.assertEqual(rows[0]["q_mid"], "0.41")
        self.assertEqual(tuple(rows[0].keys()), OBSERVATION_FIELDS)

    def test_crossed_quote_is_invalid(self):
        from datetime import datetime, timezone
        open_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        close_time = datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)
        response = _Response({
            "ticker": "T",
            "candlesticks": [{
                "end_period_ts": int(datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc).timestamp()),
                "yes_bid": {"close": "0.60"}, "yes_ask": {"close": "0.50"},
            }],
        })
        row = build_observation_rows(
            run_id="run", inventory_run_id="inventory", family="KXBTC",
            event_ticker="E", cluster_id="C", ticker="T", probe_role="q50",
            open_time=open_time, close_time=close_time, route_tier="historical",
            response=response,
        )[0]
        self.assertEqual(row["valid_quote_observation"], "false")
        self.assertEqual(row["exclusion_reason"], "crossed_quote")

    def test_summary_uses_cluster_not_observation_count_as_gate_unit(self):
        clusters = []
        probes = []
        observations = []
        for family in ("KXBTC15M", "KXBTC", "KXBTCD"):
            probe_count = 1 if family == "KXBTC15M" else 3
            for i in range(TARGET_CLUSTERS_PER_FAMILY):
                cluster_id = f"{family}-C{i}"
                clusters.append({"family": family, "source_cluster_id": cluster_id, "duration_seconds": "60"})
                for p in range(probe_count):
                    ticker = f"{family}-T{i}-{p}"
                    probes.append({"family": family, "source_cluster_id": cluster_id, "ticker": ticker})
                    for band in ("early", "middle", "late"):
                        observations.append({
                            "family": family, "source_cluster_id": cluster_id,
                            "ticker": ticker, "time_band": band,
                            "valid_quote_observation": "true",
                        })
        summaries = build_summary_rows(clusters, probes, observations)
        self.assertTrue(all(row["base_quote_feasibility_pass"] == "true" for row in summaries))
        self.assertTrue(all(row["status"] == "quote_feasibility_pass" for row in summaries))

    def test_ladder_breadth_can_fail_while_base_passes(self):
        clusters = []
        probes = []
        observations = []
        for family in ("KXBTC15M", "KXBTC", "KXBTCD"):
            probe_count = 1 if family == "KXBTC15M" else 3
            for i in range(20):
                cid = f"{family}-{i}"
                clusters.append({"family": family, "source_cluster_id": cid, "duration_seconds": "60"})
                for p in range(probe_count):
                    ticker = f"{cid}-{p}"
                    probes.append({"family": family, "source_cluster_id": cid, "ticker": ticker})
                    # Every cluster and probe has quotes, but ladders only have all-probe
                    # coverage in every band for 8/20 clusters.
                    bands = ("early", "middle", "late") if (family == "KXBTC15M" or i < 8 or p == 0) else ("early",)
                    for band in bands:
                        observations.append({
                            "family": family, "source_cluster_id": cid, "ticker": ticker,
                            "time_band": band, "valid_quote_observation": "true",
                        })
        summaries = {row["family"]: row for row in build_summary_rows(clusters, probes, observations)}
        self.assertEqual(summaries["KXBTC"]["base_quote_feasibility_pass"], "true")
        self.assertEqual(summaries["KXBTC"]["ladder_breadth_pass"], "false")
        self.assertEqual(summaries["KXBTC"]["status"], "quote_feasibility_pass_ladder_breadth_failed")
        self.assertEqual(summaries["KXBTC15M"]["ladder_breadth_gate_applicable"], "false")

    def test_schema_has_no_outcome_field(self):
        self.assertNotIn("result", OBSERVATION_FIELDS)


if __name__ == "__main__":
    unittest.main()

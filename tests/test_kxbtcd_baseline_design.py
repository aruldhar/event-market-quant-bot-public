from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.kxbtcd_baseline_design import (
    BAND_TARGET_NORMALIZED_REMAINING,
    CLUSTER_OUTPUT_FIELDS,
    CROSS_SECTION_OUTPUT_FIELDS,
    EXPERIMENT_ID,
    FORBIDDEN_PREOUTCOME_FIELDS,
    KxbtcdBaselineDesignError,
    PROBE_ROLES,
    assign_chronological_partitions,
    binary_log_loss,
    brier_score,
    design_fingerprint,
    frozen_design_contract,
    prepare_preoutcome_inputs,
    SourceArtifacts,
    project_nonincreasing_l2,
    select_synchronized_cross_section,
    validate_design_contract,
)


def _probe(role: str, strike: str) -> dict[str, str]:
    return {
        "source_cluster_id": "cluster-1",
        "ticker": f"T-{role}",
        "probe_role": role,
        "strike_type": "greater",
        "floor_strike": strike,
        "cap_strike": "",
        "functional_strike": "",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-01-01T01:00:00Z",
    }


def _obs(role: str, ts: int, band: str, norm: str, q: str = "0.5") -> dict[str, str]:
    return {
        "source_cluster_id": "cluster-1",
        "ticker": f"T-{role}",
        "probe_role": role,
        "time_band": band,
        "valid_quote_observation": "true",
        "end_period_ts": str(ts),
        "normalized_time_remaining": norm,
        "q_mid": q,
        "yes_bid_close": "0.49",
        "yes_ask_close": "0.51",
        "spread": "0.02",
        "raw_source": "kalshi_public_rest",
        "raw_session_id": "session",
        "raw_request_id": f"req-{role}-{ts}",
        "route_tier": "historical",
    }


class KxbtcdBaselineDesignTests(unittest.TestCase):
    def test_design_contract_validates_and_preoutcome_schema_forbids_outcomes(self) -> None:
        validate_design_contract()
        self.assertFalse(FORBIDDEN_PREOUTCOME_FIELDS.intersection(CLUSTER_OUTPUT_FIELDS))
        self.assertFalse(FORBIDDEN_PREOUTCOME_FIELDS.intersection(CROSS_SECTION_OUTPUT_FIELDS))

    def test_fingerprint_is_stable_for_contract(self) -> None:
        self.assertEqual(
            design_fingerprint(),
            "bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4",
        )
        self.assertEqual(frozen_design_contract()["experiment_id"], EXPERIMENT_ID)

    def test_projection_leaves_monotone_vector_unchanged(self) -> None:
        actual = project_nonincreasing_l2([Decimal("0.8"), Decimal("0.5"), Decimal("0.2")])
        self.assertEqual(actual, (Decimal("0.8"), Decimal("0.5"), Decimal("0.2")))

    def test_projection_pools_adjacent_violation(self) -> None:
        actual = project_nonincreasing_l2([Decimal("0.6"), Decimal("0.7"), Decimal("0.2")])
        self.assertEqual(actual, (Decimal("0.65"), Decimal("0.65"), Decimal("0.2")))

    def test_projection_pools_full_vector_when_needed(self) -> None:
        actual = project_nonincreasing_l2([Decimal("0.2"), Decimal("0.5"), Decimal("0.8")])
        self.assertEqual(actual, (Decimal("0.5"), Decimal("0.5"), Decimal("0.5")))

    def test_synchronized_selection_uses_exact_common_timestamp_nearest_band_center(self) -> None:
        probes = [_probe("q25", "50000"), _probe("q50", "51000"), _probe("q75", "52000")]
        target = BAND_TARGET_NORMALIZED_REMAINING["early"]
        self.assertGreater(target, Decimal("0.8"))
        observations = []
        for role in PROBE_ROLES:
            observations.extend(
                [
                    _obs(role, 100, "early", "0.80"),
                    _obs(role, 200, "early", "0.84"),
                ]
            )
        section = select_synchronized_cross_section(
            cluster_id="cluster-1",
            probes=probes,
            observations=observations,
            time_band="early",
        )
        self.assertEqual({row["end_period_ts"] for row in section.values()}, {"200"})

    def test_synchronized_selection_requires_common_timestamp(self) -> None:
        probes = [_probe("q25", "50000"), _probe("q50", "51000"), _probe("q75", "52000")]
        observations = [
            _obs("q25", 100, "middle", "0.5"),
            _obs("q50", 101, "middle", "0.5"),
            _obs("q75", 102, "middle", "0.5"),
        ]
        section = select_synchronized_cross_section(
            cluster_id="cluster-1",
            probes=probes,
            observations=observations,
            time_band="middle",
        )
        self.assertEqual(section, {})

    def test_synchronized_selection_ignores_invalid_quote(self) -> None:
        probes = [_probe("q25", "50000"), _probe("q50", "51000"), _probe("q75", "52000")]
        observations = [_obs(role, 100, "middle", "0.5") for role in PROBE_ROLES]
        observations[1]["valid_quote_observation"] = "false"
        section = select_synchronized_cross_section(
            cluster_id="cluster-1",
            probes=probes,
            observations=observations,
            time_band="middle",
        )
        self.assertEqual(section, {})

    def test_chronological_split_uses_first_two_thirds_as_development(self) -> None:
        clusters = []
        for idx in range(15):
            clusters.append(
                {
                    "source_cluster_id": f"c{idx:02d}",
                    "event_ticker": f"E{idx:02d}",
                    "close_time": f"2026-01-{idx+1:02d}T00:00:00Z",
                }
            )
        split = assign_chronological_partitions(clusters)
        self.assertEqual(sum(value[0] == "development" for value in split.values()), 10)
        self.assertEqual(sum(value[0] == "holdout" for value in split.values()), 5)
        self.assertEqual(split["c00"], ("development", 1))
        self.assertEqual(split["c14"], ("holdout", 15))

    def test_chronological_split_rejects_single_cluster(self) -> None:
        with self.assertRaises(KxbtcdBaselineDesignError):
            assign_chronological_partitions(
                [{"source_cluster_id": "c", "event_ticker": "E", "close_time": "2026-01-01T00:00:00Z"}]
            )


    def test_prepare_preoutcome_inputs_freezes_all_twenty_clusters(self) -> None:
        import csv
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clusters_path = root / "run_btc_family_clusters.csv"
            probes_path = root / "run_btc_family_probe_markets.csv"
            observations_path = root / "run_btc_family_quote_observations.csv"
            summaries_path = root / "run_btc_family_quote_summary.csv"
            manifest_path = root / "manifest.json"

            cluster_fields = [
                "schema_version", "run_id", "inventory_run_id", "family", "series_ticker",
                "event_ticker", "source_cluster_id", "regime_id", "primitive_ids_json",
                "open_time", "close_time", "duration_seconds", "selection_hash",
                "probe_market_count", "cluster_selection_rule",
            ]
            probe_fields = [
                "schema_version", "run_id", "inventory_run_id", "family", "event_ticker",
                "source_cluster_id", "ticker", "probe_role", "strike_type", "floor_strike",
                "cap_strike", "functional_strike", "open_time", "close_time", "settlement_ts",
                "inventory_raw_source", "inventory_raw_session_id", "inventory_raw_request_id",
            ]
            observation_fields = [
                "schema_version", "run_id", "inventory_run_id", "raw_source", "raw_session_id",
                "raw_request_id", "route_tier", "family", "event_ticker", "source_cluster_id",
                "ticker", "probe_role", "source_field_family", "end_period_ts", "open_time",
                "close_time", "duration_seconds", "time_to_close_seconds",
                "normalized_time_remaining", "time_band", "period_interval_minutes",
                "yes_bid_close", "yes_ask_close", "q_mid", "spread", "quote_pair_present",
                "crossed_close", "valid_quote_observation", "exclusion_reason",
            ]
            summary_fields = [
                "schema_version", "family", "target_cluster_count", "cluster_count",
                "probe_market_count", "valid_quote_observation_count", "clusters_with_valid_quote",
                "probe_markets_with_valid_quote", "cluster_any_quote_coverage",
                "probe_market_any_quote_coverage", "early_cluster_coverage",
                "middle_cluster_coverage", "late_cluster_coverage",
                "all_three_band_cluster_coverage", "all_probe_early_cluster_coverage",
                "all_probe_middle_cluster_coverage", "all_probe_late_cluster_coverage",
                "all_probe_all_three_band_cluster_coverage", "median_duration_seconds",
                "min_duration_seconds", "max_duration_seconds", "sample_target_met",
                "base_quote_feasibility_pass", "ladder_breadth_gate_applicable",
                "ladder_breadth_pass", "status",
            ]
            clusters=[]; probes=[]; observations=[]
            for i in range(20):
                day=i+1
                event=f"E{i:02d}"; cid=f"C{i:02d}"
                open_time=f"2026-01-{day:02d}T00:00:00Z"
                close_time=f"2026-01-{day:02d}T01:00:00Z"
                clusters.append({
                    "schema_version":"v", "run_id":"run", "inventory_run_id":"inventory",
                    "family":"KXBTCD", "series_ticker":"KXBTCD", "event_ticker":event,
                    "source_cluster_id":cid, "regime_id":"brti_60s_simple_mean_untrimmed",
                    "primitive_ids_json":json.dumps([f"p{i:02d}"]), "open_time":open_time,
                    "close_time":close_time, "duration_seconds":"3600", "selection_hash":f"h{i}",
                    "probe_market_count":"3", "cluster_selection_rule":"rule",
                })
                for role, strike, q in zip(PROBE_ROLES, ("50000","51000","52000"), ("0.7","0.5","0.3")):
                    ticker=f"{event}-{role}"
                    probes.append({
                        "schema_version":"v", "run_id":"run", "inventory_run_id":"inventory",
                        "family":"KXBTCD", "event_ticker":event, "source_cluster_id":cid,
                        "ticker":ticker, "probe_role":role, "strike_type":"greater",
                        "floor_strike":strike, "cap_strike":"", "functional_strike":"",
                        "open_time":open_time, "close_time":close_time, "settlement_ts":close_time,
                        "inventory_raw_source":"s", "inventory_raw_session_id":"ss",
                        "inventory_raw_request_id":f"m-{ticker}",
                    })
                    for band, ts_offset, norm in (("early",600,"0.833333333333333333"),("middle",1800,"0.5"),("late",3000,"0.166666666666666667")):
                        observations.append({
                            "schema_version":"v", "run_id":"run", "inventory_run_id":"inventory",
                            "raw_source":"s", "raw_session_id":"ss",
                            "raw_request_id":f"q-{ticker}-{band}", "route_tier":"historical",
                            "family":"KXBTCD", "event_ticker":event, "source_cluster_id":cid,
                            "ticker":ticker, "probe_role":role, "source_field_family":"historical_plain",
                            "end_period_ts":str(1000000+i*10000+ts_offset), "open_time":open_time,
                            "close_time":close_time, "duration_seconds":"3600",
                            "time_to_close_seconds":"0", "normalized_time_remaining":norm,
                            "time_band":band, "period_interval_minutes":"1",
                            "yes_bid_close":str(Decimal(q)-Decimal("0.01")),
                            "yes_ask_close":str(Decimal(q)+Decimal("0.01")), "q_mid":q,
                            "spread":"0.02", "quote_pair_present":"true", "crossed_close":"false",
                            "valid_quote_observation":"true", "exclusion_reason":"",
                        })
            summaries=[{field:"" for field in summary_fields}]
            summaries[0].update({
                "schema_version":"v", "family":"KXBTCD", "target_cluster_count":"20",
                "cluster_count":"20", "probe_market_count":"60",
                "valid_quote_observation_count":"180", "clusters_with_valid_quote":"20",
                "probe_markets_with_valid_quote":"60", "cluster_any_quote_coverage":"1.0",
                "probe_market_any_quote_coverage":"1.0", "early_cluster_coverage":"1.0",
                "middle_cluster_coverage":"1.0", "late_cluster_coverage":"1.0",
                "all_three_band_cluster_coverage":"1.0", "all_probe_early_cluster_coverage":"1.0",
                "all_probe_middle_cluster_coverage":"1.0", "all_probe_late_cluster_coverage":"1.0",
                "all_probe_all_three_band_cluster_coverage":"1.0", "median_duration_seconds":"3600",
                "min_duration_seconds":"3600", "max_duration_seconds":"3600",
                "sample_target_met":"true", "base_quote_feasibility_pass":"true",
                "ladder_breadth_gate_applicable":"true", "ladder_breadth_pass":"true",
                "status":"quote_feasibility_pass",
            })
            for path, fields, rows in ((clusters_path,cluster_fields,clusters),(probes_path,probe_fields,probes),(observations_path,observation_fields,observations),(summaries_path,summary_fields,summaries)):
                with path.open("w", newline="", encoding="utf-8") as h:
                    w=csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)
            manifest_path.write_text(json.dumps({"run_id":"run"}), encoding="utf-8")
            artifacts=SourceArtifacts(manifest_path, {"run_id":"run"}, clusters_path, probes_path, observations_path, summaries_path)
            result=prepare_preoutcome_inputs(artifacts)
            self.assertEqual(result.summary["primary_eligible_cluster_count"], "20")
            self.assertEqual(result.summary["development_cluster_count"], "13")
            self.assertEqual(result.summary["holdout_cluster_count"], "7")
            self.assertEqual(result.summary["selected_cross_section_count"], "60")
            self.assertEqual(result.summary["selected_prediction_row_count"], "180")

    def test_log_loss_uses_finite_epsilon(self) -> None:
        value = binary_log_loss(Decimal("0"), 1)
        self.assertTrue(value.is_finite())
        self.assertGreater(value, Decimal("10"))

    def test_brier_score(self) -> None:
        self.assertEqual(brier_score(Decimal("0.7"), 1), Decimal("0.09"))


if __name__ == "__main__":
    unittest.main()

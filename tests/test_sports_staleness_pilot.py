from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from src.sports_historical_schema import ANCHOR_FIELDS, EVENT_FIELDS, MARKET_FIELDS
from src.sports_staleness_pilot import (
    FREEZE_MIN_UNIQUE_EVENTS,
    SportsStalenessPilotError,
    analyze_staleness_manifest,
    write_staleness_report,
)


class SportsStalenessPilotTests(unittest.TestCase):
    def _fixture(self, root: Path, *, event_count: int, ages_by_anchor: dict[str, int | None], outcomes=False):
        run_id = "collect_sports_historical_20260809T000000000000Z_test0001"
        derived = root / "data" / "derived" / "sports_historical" / "2026" / "08" / "09"
        derived.mkdir(parents=True)
        events_path = derived / f"{run_id}_events.csv"
        markets_path = derived / f"{run_id}_markets.csv"
        anchors_path = derived / f"{run_id}_anchors.csv"
        candles_path = derived / f"{run_id}_candles.csv"

        events = []
        markets = []
        anchors = []
        for i in range(event_count):
            event_ticker = f"EV{i:03d}"
            ticker = f"MKT{i:03d}"
            events.append({
                "run_id": run_id, "raw_source": "kalshi_public_rest", "raw_session_id": "s", "raw_request_id": f"e{i}",
                "route_tier": "metadata", "event_ticker": event_ticker, "series_ticker": "SER", "category": "Sports",
                "mutually_exclusive": "false", "strike_date": "",
            })
            markets.append({
                "run_id": run_id, "raw_source": "kalshi_public_rest", "raw_session_id": "s", "raw_request_id": f"m{i}",
                "route_tier": "historical", "ticker": ticker, "event_ticker": event_ticker, "market_type": "binary",
                "status": "finalized", "open_time": "2026-01-01T00:00:00Z", "close_time": "2026-01-10T00:00:00Z",
                "settlement_ts": "2026-01-10T01:00:00Z", "mve_collection_ticker": "", "is_provisional": "false",
            })
            for anchor_name, age in ages_by_anchor.items():
                quote_count = 0 if age is None else 1
                anchors.append({
                    "run_id": run_id, "raw_source": "kalshi_public_rest", "raw_session_id": "s", "raw_request_id": f"a{i}{anchor_name}",
                    "route_tier": "historical", "ticker": ticker, "anchor_name": anchor_name, "anchor_ts": "100000",
                    "window_start_ts": str(100000 - 24*3600), "window_end_ts": "100000", "candle_count": str(quote_count),
                    "quote_pair_count": str(quote_count), "latest_real_candle_ts": "" if age is None else str(100000-age),
                    "latest_quote_pair_ts": "" if age is None else str(100000-age),
                    "latest_quote_age_seconds": "" if age is None else str(age),
                })

        self._write(events_path, EVENT_FIELDS, events)
        self._write(markets_path, MARKET_FIELDS, markets)
        self._write(anchors_path, ANCHOR_FIELDS, anchors)
        candles_path.write_text("POISON: pilot must never open this file\n", encoding="utf-8")

        manifest = {
            "run_id": run_id,
            "collector": {"name": "collect_sports_historical"},
            "status": "completed",
            "arguments": {"anchor_lookback_hours": 24},
            "result": {
                "outcomes_materialized": outcomes,
                "calibration_run": False,
                "staleness_threshold_frozen": False,
            },
            "files": [
                {"role": "derived_csv", "path": {"kind": "repository_relative", "value": str(events_path.relative_to(root)).replace('\\','/')}},
                {"role": "derived_csv", "path": {"kind": "repository_relative", "value": str(markets_path.relative_to(root)).replace('\\','/')}},
                {"role": "derived_csv", "path": {"kind": "repository_relative", "value": str(anchors_path.relative_to(root)).replace('\\','/')}},
                {"role": "derived_csv", "path": {"kind": "repository_relative", "value": str(candles_path.relative_to(root)).replace('\\','/')}},
            ],
        }
        manifest_path = root / "data" / "manifests" / "run.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path

    @staticmethod
    def _write(path: Path, fields, rows):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fields))
            writer.writeheader()
            writer.writerows(rows)

    def test_small_sample_is_preliminary_and_does_not_open_candles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=25, ages_by_anchor={"7d":300,"3d":300,"1d":300})
            result = analyze_staleness_manifest(manifest, repository_root=root)
            self.assertEqual(result.report["recommendation"]["status"], "preliminary_sample_too_small")
            self.assertEqual(result.report["recommendation"]["candidate_threshold_seconds"], 300)
            self.assertFalse(result.report["recommendation"]["freeze_eligible"])
            self.assertEqual(result.report["analysis_scope"]["opened_tables"], ["events","markets","anchors"])
            self.assertFalse(result.report["analysis_scope"]["candles_opened"])

    def test_100_events_can_produce_freeze_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=FREEZE_MIN_UNIQUE_EVENTS, ages_by_anchor={"7d":300,"3d":300,"1d":300})
            result = analyze_staleness_manifest(manifest, repository_root=root)
            self.assertEqual(result.report["recommendation"]["status"], "freeze_candidate_available")
            self.assertEqual(result.report["recommendation"]["candidate_threshold_seconds"], 300)
            self.assertTrue(result.report["recommendation"]["freeze_eligible"])

    def test_smallest_threshold_must_pass_every_anchor_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=100, ages_by_anchor={"7d":300,"3d":300,"1d":1800})
            result = analyze_staleness_manifest(manifest, repository_root=root)
            self.assertEqual(result.report["recommendation"]["candidate_threshold_seconds"], 1800)

    def test_no_candidate_above_one_hour_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=100, ages_by_anchor={"7d":7200,"3d":7200,"1d":7200})
            result = analyze_staleness_manifest(manifest, repository_root=root)
            self.assertEqual(result.report["recommendation"]["status"], "blocked_no_freshness_candidate_meets_retention_gates")
            self.assertIsNone(result.report["recommendation"]["candidate_threshold_seconds"])

    def test_missing_quotes_are_preserved_in_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=10, ages_by_anchor={"7d":300,"3d":None,"1d":300})
            result = analyze_staleness_manifest(manifest, repository_root=root)
            self.assertEqual(result.report["sample"]["anchors"], 30)
            self.assertEqual(result.report["sample"]["quote_anchors"], 20)
            self.assertEqual(result.report["sample"]["missing_quote_anchors"], 10)
            self.assertEqual(result.report["by_anchor"]["3d"]["quote_anchor_rows"], 0)

    def test_outcomes_materialized_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=1, ages_by_anchor={"7d":300,"3d":300,"1d":300}, outcomes=True)
            with self.assertRaisesRegex(SportsStalenessPilotError, "outcomes_materialized"):
                analyze_staleness_manifest(manifest, repository_root=root)

    def test_age_with_zero_quote_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=1, ages_by_anchor={"7d":None,"3d":300,"1d":300})
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            anchor_path = root / manifest_data["files"][2]["path"]["value"]
            rows = list(csv.DictReader(anchor_path.open("r", newline="", encoding="utf-8")))
            rows[0]["latest_quote_age_seconds"] = "30"
            self._write(anchor_path, ANCHOR_FIELDS, rows)
            with self.assertRaisesRegex(SportsStalenessPilotError, "zero quote_pair_count"):
                analyze_staleness_manifest(manifest, repository_root=root)

    def test_report_outputs_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._fixture(root, event_count=25, ages_by_anchor={"7d":300,"3d":300,"1d":300})
            result = analyze_staleness_manifest(manifest, repository_root=root)
            json_path, csv_path = write_staleness_report(result, output_root=root / "reports")
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(saved["analysis_scope"]["outcome_blind"])
            self.assertFalse(saved["recommendation"]["threshold_frozen"])


if __name__ == "__main__":
    unittest.main()

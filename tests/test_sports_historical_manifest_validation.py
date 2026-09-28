from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.sports_historical_collector import collect_sports_historical_rows, write_collected_csvs
from src.sports_historical_manifest_validation import (
    SportsHistoricalManifestValidationError,
    validate_sports_historical_manifest,
)
from tests.test_sports_historical_collector import FakeClient, base_routes


class SportsHistoricalManifestValidationTests(unittest.TestCase):
    def _fixture(self, root: Path):
        client = FakeClient(base_routes())
        rows = collect_sports_historical_rows(
            client,
            run_id="run1",
            max_sports_events=1,
        )
        derived = write_collected_csvs(root / "derived", run_id="run1", rows=rows)

        # Recreate the minimal raw_http_exchange fields needed by the semantic validator.
        raw_path = root / "raw.jsonl"
        records = []
        for index, (path, params) in enumerate(client.calls, start=1):
            payload = client.routes[(path, tuple(sorted(params.items())))]
            records.append(
                {
                    "source": "kalshi_public_rest",
                    "session_id": "session1",
                    "request": {
                        "request_id": f"r{index}",
                        "method": "GET",
                        "path": path,
                        "params": params,
                    },
                    "response": {
                        "status_code": 200,
                        "body_text": json.dumps(payload),
                        "json_parse_error": None,
                    },
                    "error": None,
                }
            )
        raw_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

        manifest = {
            "run_id": "run1",
            "collector": {"name": "collect_sports_historical"},
            "status": "completed",
            "files": [
                {"role": "raw_api_archive", "path": {"kind": "absolute", "value": str(raw_path)}},
                *[
                    {"role": "derived_csv", "path": {"kind": "absolute", "value": str(path)}}
                    for path in derived.all()
                ],
            ],
            "result": {
                "market_settled_cutoff": rows.cutoff.market_settled_ts.isoformat(),
                "trades_created_cutoff": rows.cutoff.trades_created_ts.isoformat(),
                "orders_updated_cutoff": rows.cutoff.orders_updated_ts.isoformat(),
                "market_positions_last_updated_cutoff": rows.cutoff.market_positions_last_updated_ts.isoformat(),
                "cutoff_raw_source": rows.cutoff_raw_source,
                "cutoff_raw_session_id": rows.cutoff_raw_session_id,
                "cutoff_raw_request_id": rows.cutoff_raw_request_id,
                "event_pages_scanned": rows.event_pages_scanned,
                "outcomes_materialized": False,
                "calibration_run": False,
            },
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path, derived

    def test_manifest_reconciles_all_pre_staleness_rows_to_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _ = self._fixture(Path(tmp))
            result = validate_sports_historical_manifest(manifest, repository_root=tmp)
            self.assertEqual(result["validation"], "PASS")
            self.assertEqual(result["event_rows"], 1)
            self.assertEqual(result["market_rows"], 1)
            self.assertEqual(result["anchor_rows"], 3)
            self.assertFalse(result["outcomes_materialized"])

    def test_tampered_candle_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, derived = self._fixture(Path(tmp))
            text = derived.candles.read_text(encoding="utf-8")
            derived.candles.write_text(text.replace("0.40", "0.39", 1), encoding="utf-8")
            with self.assertRaisesRegex(
                SportsHistoricalManifestValidationError,
                "differs from raw evidence",
            ):
                validate_sports_historical_manifest(manifest, repository_root=tmp)

    def test_outcomes_materialized_flag_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, _ = self._fixture(Path(tmp))
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["result"]["outcomes_materialized"] = True
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(
                SportsHistoricalManifestValidationError,
                "outcomes_materialized=false",
            ):
                validate_sports_historical_manifest(manifest, repository_root=tmp)


if __name__ == "__main__":
    unittest.main()

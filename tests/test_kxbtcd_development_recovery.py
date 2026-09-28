from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.kxbtcd_baseline_design import TIME_BANDS, design_fingerprint
from src.kxbtcd_development_evaluation import (
    KxbtcdDevelopmentEvaluationError,
    PreOutcomeFreeze,
    _enrich_cross_sections_with_source_probe_metadata,
    development_request_plan,
    evaluate_development,
    recover_development_outcomes_from_failed_manifest,
)


def _freeze() -> PreOutcomeFreeze:
    clusters = []
    sections = []
    fingerprint = design_fingerprint()
    roles = ("q25", "q50", "q75")
    for i in range(12):
        partition = "development" if i < 8 else "holdout"
        cluster_id = f"cluster-{i:02d}"
        event = f"KXBTCD-EVENT-{i:02d}"
        clusters.append({
            "design_fingerprint": fingerprint,
            "source_cluster_id": cluster_id,
            "event_ticker": event,
            "primary_eligible": "true",
            "partition": partition,
        })
        for band_index, band in enumerate(TIME_BANDS):
            for role_index, role in enumerate(roles):
                sections.append({
                    "design_fingerprint": fingerprint,
                    "event_ticker": event,
                    "source_cluster_id": cluster_id,
                    "partition": partition,
                    "time_band": band,
                    "cross_section_id": f"{cluster_id}-{band}",
                    "selected_end_period_ts": str(1_700_000_000 + i * 10000 + band_index * 60),
                    "selected_normalized_time_remaining": ("0.83", "0.50", "0.16")[band_index],
                    "ticker": f"{event}-{role}",
                    "probe_role": role,
                    "functional_strike": str(50000 + role_index * 1000),
                    "q_raw": ("0.70", "0.80", "0.20")[role_index],
                    "quote_route_tier": "historical",
                })
    return PreOutcomeFreeze(
        receipt_path=Path("receipt.json"),
        receipt_sha256="a" * 64,
        receipt={"source_run_id": "source-run"},
        clusters_path=Path("clusters.csv"),
        cross_sections_path=Path("sections.csv"),
        clusters=tuple(clusters),
        cross_sections=tuple(sections),
    )


def _write_raw_record(handle, *, request_id: str, path: str, ticker: str, event: str, result: str):
    payload = {"market": {"ticker": ticker, "event_ticker": event, "status": "finalized", "result": result}}
    record = {
        "schema_version": "raw_http_exchange.v1",
        "source": "kalshi_public_rest",
        "session_id": "session-1",
        "request": {"request_id": request_id, "path": path},
        "response": {"status_code": 200, "body_text": json.dumps(payload)},
        "error": None,
    }
    handle.write(json.dumps(record) + "\n")


class KxbtcdDevelopmentRecoveryTests(unittest.TestCase):
    def test_blank_frozen_strike_metadata_is_recovered_from_source_probe(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            probe_path = root / "data/derived/source_btc_family_probe_markets.csv"
            probe_path.parent.mkdir(parents=True)
            with probe_path.open("w", encoding="utf-8", newline="") as handle:
                fields = ["family", "event_ticker", "source_cluster_id", "ticker", "probe_role", "strike_type", "floor_strike", "cap_strike", "functional_strike"]
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "family": "KXBTCD", "event_ticker": "E", "source_cluster_id": "C",
                    "ticker": "T", "probe_role": "q25", "strike_type": "greater",
                    "floor_strike": "50000", "cap_strike": "", "functional_strike": "",
                })
            source_manifest_path = root / "data/manifests/source.json"
            source_manifest_path.parent.mkdir(parents=True)
            source_manifest = {
                "run_id": "source-run", "status": "completed",
                "files": [{
                    "role": "derived_csv", "sha256": hashlib.sha256(probe_path.read_bytes()).hexdigest(),
                    "path": {"kind": "repository_relative", "value": probe_path.relative_to(root).as_posix()},
                }],
            }
            source_manifest_path.write_text(json.dumps(source_manifest), encoding="utf-8")
            receipt = {
                "source_run_id": "source-run",
                "source_manifest": {"kind": "repository_relative", "value": source_manifest_path.relative_to(root).as_posix()},
                "source_manifest_sha256": hashlib.sha256(source_manifest_path.read_bytes()).hexdigest(),
            }
            rows = [{
                "event_ticker": "E", "source_cluster_id": "C", "ticker": "T", "probe_role": "q25",
                "strike_type": "", "floor_strike": "", "cap_strike": "", "functional_strike": "",
            }]
            enriched = _enrich_cross_sections_with_source_probe_metadata(repo=root, receipt=receipt, cross_sections=rows)
            self.assertEqual("50000", enriched[0]["floor_strike"])
            self.assertEqual("50000", enriched[0]["strike_anchor"])

    def test_failed_run_is_replayed_offline_and_scores(self):
        freeze = _freeze()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "data/raw/kalshi_rest/2026/08/09/session-1.jsonl"
            raw_path.parent.mkdir(parents=True)
            plan = development_request_plan(freeze)
            with raw_path.open("w", encoding="utf-8") as handle:
                for index, item in enumerate(plan, start=1):
                    endpoint = f"/historical/markets/{item['ticker']}"
                    result = "yes" if item["probe_role"] in {"q25", "q50"} else "no"
                    _write_raw_record(handle, request_id=f"req-{index}", path=endpoint, ticker=item["ticker"], event=item["event_ticker"], result=result)
            manifest_path = root / "data/manifests/2026/08/09/collect_kxbtcd_development_outcomes_test.json"
            manifest_path.parent.mkdir(parents=True)
            manifest = {
                "run_id": "failed-run",
                "collector": {"name": "collect_kxbtcd_development_outcomes"},
                "status": "failed",
                "arguments": {
                    "preoutcome_receipt_sha256": freeze.receipt_sha256,
                    "design_fingerprint": design_fingerprint(),
                    "partition": "development",
                },
                "files": [{
                    "role": "raw_api_archive",
                    "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                    "path": {"kind": "repository_relative", "value": raw_path.relative_to(root).as_posix()},
                }],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            outcomes = recover_development_outcomes_from_failed_manifest(
                freeze=freeze, manifest_path=manifest_path, repository_root=root
            )
            self.assertEqual(24, len(outcomes))
            evaluation = evaluate_development(freeze=freeze, outcomes=outcomes)
            self.assertEqual(72, len(evaluation.predictions))
            self.assertEqual("false", evaluation.summary["holdout_outcomes_materialized"])

    def test_recovery_rejects_any_holdout_request_in_raw_archive(self):
        freeze = _freeze()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "data/raw/kalshi_rest/2026/08/09/session-1.jsonl"
            raw_path.parent.mkdir(parents=True)
            plan = development_request_plan(freeze)
            with raw_path.open("w", encoding="utf-8") as handle:
                for index, item in enumerate(plan, start=1):
                    endpoint = f"/historical/markets/{item['ticker']}"
                    result = "yes" if item["probe_role"] in {"q25", "q50"} else "no"
                    _write_raw_record(handle, request_id=f"req-{index}", path=endpoint, ticker=item["ticker"], event=item["event_ticker"], result=result)
                holdout = next(row for row in freeze.cross_sections if row["partition"] == "holdout")
                _write_raw_record(
                    handle, request_id="holdout-req", path=f"/historical/markets/{holdout['ticker']}",
                    ticker=holdout["ticker"], event=holdout["event_ticker"], result="no",
                )
            manifest_path = root / "data/manifests/2026/08/09/collect_kxbtcd_development_outcomes_test.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps({
                "run_id": "failed-run",
                "collector": {"name": "collect_kxbtcd_development_outcomes"},
                "status": "failed",
                "arguments": {
                    "preoutcome_receipt_sha256": freeze.receipt_sha256,
                    "design_fingerprint": design_fingerprint(),
                    "partition": "development",
                },
                "files": [{
                    "role": "raw_api_archive", "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                    "path": {"kind": "repository_relative", "value": raw_path.relative_to(root).as_posix()},
                }],
            }), encoding="utf-8")
            with self.assertRaisesRegex(KxbtcdDevelopmentEvaluationError, "holdout request"):
                recover_development_outcomes_from_failed_manifest(
                    freeze=freeze, manifest_path=manifest_path, repository_root=root
                )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.kxbtcd_baseline_design import EXPERIMENT_ID, TIME_BANDS, design_fingerprint
from src.kxbtcd_development_evaluation import PreOutcomeFreeze
from src.kxbtcd_holdout_evaluation import (
    DevelopmentRecoveryEvidence,
    KxbtcdHoldoutEvaluationError,
    OUTCOME_FIELDS,
    collect_holdout_outcomes,
    evaluate_holdout,
    holdout_request_plan,
    load_verified_development_recovery,
    recover_holdout_outcomes_from_failed_manifest,
)


@dataclass(frozen=True)
class _Raw:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class _Response:
    payload: dict
    raw_record: _Raw


class _Client:
    def __init__(self, labels, events):
        self.labels = labels
        self.events = events
        self.paths = []

    def get_json(self, path, *, params=None):
        self.paths.append(path)
        ticker = path.rsplit("/", 1)[-1]
        return _Response(
            payload={
                "market": {
                    "ticker": ticker,
                    "event_ticker": self.events[ticker],
                    "status": "finalized",
                    "result": self.labels[ticker],
                }
            },
            raw_record=_Raw("kalshi_public_rest", "session", f"req-{len(self.paths)}"),
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
        clusters.append(
            {
                "design_fingerprint": fingerprint,
                "source_cluster_id": cluster_id,
                "event_ticker": event,
                "primary_eligible": "true",
                "partition": partition,
            }
        )
        for band_index, band in enumerate(TIME_BANDS):
            cross_id = f"{cluster_id}-{band}"
            for role_index, role in enumerate(roles):
                # Deliberately non-monotone q25/q50 so the projection has work to do.
                q = ("0.70", "0.80", "0.20")[role_index]
                sections.append(
                    {
                        "design_fingerprint": fingerprint,
                        "event_ticker": event,
                        "source_cluster_id": cluster_id,
                        "partition": partition,
                        "time_band": band,
                        "cross_section_id": cross_id,
                        "selected_end_period_ts": str(
                            1_700_000_000 + i * 10000 + band_index * 60
                        ),
                        "selected_normalized_time_remaining": (
                            "0.83",
                            "0.50",
                            "0.16",
                        )[band_index],
                        "ticker": f"{event}-{role}",
                        "probe_role": role,
                        "functional_strike": str(50000 + role_index * 1000),
                        "strike_anchor": str(50000 + role_index * 1000),
                        "q_raw": q,
                        "quote_route_tier": "historical",
                    }
                )
    return PreOutcomeFreeze(
        receipt_path=Path("receipt.json"),
        receipt_sha256="a" * 64,
        receipt={"experiment_id": EXPERIMENT_ID},
        clusters_path=Path("clusters.csv"),
        cross_sections_path=Path("sections.csv"),
        clusters=tuple(clusters),
        cross_sections=tuple(sections),
    )


def _development_evidence() -> DevelopmentRecoveryEvidence:
    return DevelopmentRecoveryEvidence(
        receipt_path=Path("development_receipt.json"),
        receipt_sha256="b" * 64,
        receipt={"status": "offline_recovery_complete"},
    )


def _write_raw_record(
    handle,
    *,
    request_id: str,
    path: str,
    ticker: str,
    event: str,
    result: str,
):
    payload = {
        "market": {
            "ticker": ticker,
            "event_ticker": event,
            "status": "finalized",
            "result": result,
        }
    }
    record = {
        "schema_version": "raw_http_exchange.v1",
        "source": "kalshi_public_rest",
        "session_id": "session-1",
        "request": {"request_id": request_id, "path": path},
        "response": {"status_code": 200, "body_text": json.dumps(payload)},
        "error": None,
    }
    handle.write(json.dumps(record) + "\n")


class KxbtcdHoldoutEvaluationTests(unittest.TestCase):
    def test_holdout_plan_is_exactly_four_clusters_and_no_development_ticker(self):
        freeze = _freeze()
        plan = holdout_request_plan(freeze)
        self.assertEqual(12, len(plan))
        self.assertEqual(4, len({row["source_cluster_id"] for row in plan}))
        self.assertTrue(all("EVENT-0" not in row["event_ticker"] or int(row["event_ticker"].split("-")[-1]) >= 8 for row in plan))
        development = {
            row["ticker"] for row in freeze.cross_sections if row["partition"] == "development"
        }
        self.assertFalse({row["ticker"] for row in plan} & development)

    def test_collection_requests_only_twelve_holdout_markets(self):
        freeze = _freeze()
        evidence = _development_evidence()
        plan = holdout_request_plan(freeze)
        labels = {
            item["ticker"]: ("yes" if item["probe_role"] in {"q25", "q50"} else "no")
            for item in plan
        }
        events = {item["ticker"]: item["event_ticker"] for item in plan}
        client = _Client(labels, events)
        outcomes = collect_holdout_outcomes(
            client,
            freeze=freeze,
            development_recovery=evidence,
        )
        self.assertEqual(12, len(outcomes))
        self.assertEqual(12, len(client.paths))
        self.assertTrue(all(path.startswith("/historical/markets/") for path in client.paths))
        self.assertFalse(any("EVENT-00" in path for path in client.paths))
        self.assertTrue(all(tuple(row.keys()) == OUTCOME_FIELDS for row in outcomes))

    def test_evaluation_scores_36_predictions_and_four_clusters(self):
        freeze = _freeze()
        evidence = _development_evidence()
        plan = holdout_request_plan(freeze)
        labels = {
            item["ticker"]: ("yes" if item["probe_role"] in {"q25", "q50"} else "no")
            for item in plan
        }
        events = {item["ticker"]: item["event_ticker"] for item in plan}
        outcomes = collect_holdout_outcomes(
            _Client(labels, events),
            freeze=freeze,
            development_recovery=evidence,
        )
        result = evaluate_holdout(
            freeze=freeze,
            development_recovery=evidence,
            outcomes=outcomes,
        )
        self.assertEqual(36, len(result.predictions))
        self.assertEqual(4, len(result.cluster_scores))
        self.assertEqual(3, len(result.band_scores))
        self.assertEqual("true", result.summary["holdout_outcomes_materialized"])
        self.assertEqual("false", result.summary["model_or_metric_change_after_development"])
        self.assertGreater(float(result.summary["delta_log_loss"]), 0.0)

    def test_impossible_finalized_holdout_ordering_fails_closed(self):
        freeze = _freeze()
        evidence = _development_evidence()
        plan = holdout_request_plan(freeze)
        labels = {item["ticker"]: "no" for item in plan}
        events = {item["ticker"]: item["event_ticker"] for item in plan}
        first_cluster = plan[0]["source_cluster_id"]
        for item in plan:
            if item["source_cluster_id"] == first_cluster and item["probe_role"] == "q50":
                labels[item["ticker"]] = "yes"
        with self.assertRaisesRegex(KxbtcdHoldoutEvaluationError, "violate threshold ordering"):
            collect_holdout_outcomes(
                _Client(labels, events),
                freeze=freeze,
                development_recovery=evidence,
            )

    def test_non_yes_no_holdout_result_fails_closed(self):
        freeze = _freeze()
        evidence = _development_evidence()
        plan = holdout_request_plan(freeze)
        labels = {
            item["ticker"]: ("yes" if item["probe_role"] in {"q25", "q50"} else "no")
            for item in plan
        }
        events = {item["ticker"]: item["event_ticker"] for item in plan}
        labels[plan[0]["ticker"]] = "void"
        with self.assertRaisesRegex(KxbtcdHoldoutEvaluationError, "unsupported finalized result"):
            collect_holdout_outcomes(
                _Client(labels, events),
                freeze=freeze,
                development_recovery=evidence,
            )

    def test_development_recovery_receipt_is_hash_verified_and_proves_untouched_holdout(self):
        freeze = _freeze()
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            root = repo / "data/derived/kxbtcd_development_evaluation_recovery"
            root.mkdir(parents=True)
            artifact = root / "dev_outcomes.csv"
            artifact.write_text("a,b\n1,2\n", encoding="utf-8")
            receipt_path = root / "run_offline_recovery_receipt.json"
            receipt = {
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": freeze.receipt_sha256,
                "development_labels": 24,
                "development_predictions": 72,
                "artifacts": [
                    {
                        "path": str(artifact.relative_to(repo)),
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        "bytes": artifact.stat().st_size,
                    }
                ],
                "safety": {
                    "api_requests_made": 0,
                    "holdout_outcomes_materialized": False,
                    "external_predictive_feed_used": False,
                    "orders_placed": 0,
                },
                "status": "offline_recovery_complete",
            }
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            evidence = load_verified_development_recovery(freeze, repo)
            self.assertEqual(hashlib.sha256(receipt_path.read_bytes()).hexdigest(), evidence.receipt_sha256)

    def test_offline_recovery_replays_failed_holdout_without_network(self):
        freeze = _freeze()
        evidence = _development_evidence()
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            raw_path = repo / "data/raw/kalshi_rest/2026/08/09/session-1.jsonl"
            raw_path.parent.mkdir(parents=True)
            plan = holdout_request_plan(freeze)
            with raw_path.open("w", encoding="utf-8") as handle:
                for index, item in enumerate(plan, start=1):
                    endpoint = f"/historical/markets/{item['ticker']}"
                    result = "yes" if item["probe_role"] in {"q25", "q50"} else "no"
                    _write_raw_record(
                        handle,
                        request_id=f"req-{index}",
                        path=endpoint,
                        ticker=item["ticker"],
                        event=item["event_ticker"],
                        result=result,
                    )
            manifest_path = repo / "data/manifests/2026/08/09/collect_kxbtcd_holdout_outcomes_test.json"
            manifest_path.parent.mkdir(parents=True)
            manifest = {
                "run_id": "failed-holdout-run",
                "collector": {"name": "collect_kxbtcd_holdout_outcomes"},
                "status": "failed",
                "arguments": {
                    "preoutcome_receipt_sha256": freeze.receipt_sha256,
                    "development_recovery_receipt_sha256": evidence.receipt_sha256,
                    "design_fingerprint": design_fingerprint(),
                    "partition": "holdout",
                },
                "files": [
                    {
                        "role": "raw_api_archive",
                        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                        "path": {
                            "kind": "repository_relative",
                            "value": raw_path.relative_to(repo).as_posix(),
                        },
                    }
                ],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            outcomes = recover_holdout_outcomes_from_failed_manifest(
                freeze=freeze,
                development_recovery=evidence,
                manifest_path=manifest_path,
                repository_root=repo,
            )
            self.assertEqual(12, len(outcomes))
            result = evaluate_holdout(
                freeze=freeze,
                development_recovery=evidence,
                outcomes=outcomes,
            )
            self.assertEqual(36, len(result.predictions))

    def test_holdout_recovery_rejects_development_request(self):
        freeze = _freeze()
        evidence = _development_evidence()
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            raw_path = repo / "data/raw/kalshi_rest/2026/08/09/session-1.jsonl"
            raw_path.parent.mkdir(parents=True)
            plan = holdout_request_plan(freeze)
            with raw_path.open("w", encoding="utf-8") as handle:
                for index, item in enumerate(plan, start=1):
                    endpoint = f"/historical/markets/{item['ticker']}"
                    result = "yes" if item["probe_role"] in {"q25", "q50"} else "no"
                    _write_raw_record(
                        handle,
                        request_id=f"req-{index}",
                        path=endpoint,
                        ticker=item["ticker"],
                        event=item["event_ticker"],
                        result=result,
                    )
                dev = next(row for row in freeze.cross_sections if row["partition"] == "development")
                _write_raw_record(
                    handle,
                    request_id="dev-req",
                    path=f"/historical/markets/{dev['ticker']}",
                    ticker=dev["ticker"],
                    event=dev["event_ticker"],
                    result="no",
                )
            manifest_path = repo / "data/manifests/2026/08/09/collect_kxbtcd_holdout_outcomes_test.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": "failed-holdout-run",
                        "collector": {"name": "collect_kxbtcd_holdout_outcomes"},
                        "status": "failed",
                        "arguments": {
                            "preoutcome_receipt_sha256": freeze.receipt_sha256,
                            "development_recovery_receipt_sha256": evidence.receipt_sha256,
                            "design_fingerprint": design_fingerprint(),
                            "partition": "holdout",
                        },
                        "files": [
                            {
                                "role": "raw_api_archive",
                                "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                                "path": {
                                    "kind": "repository_relative",
                                    "value": raw_path.relative_to(repo).as_posix(),
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(KxbtcdHoldoutEvaluationError, "development request"):
                recover_holdout_outcomes_from_failed_manifest(
                    freeze=freeze,
                    development_recovery=evidence,
                    manifest_path=manifest_path,
                    repository_root=repo,
                )


if __name__ == "__main__":
    unittest.main()

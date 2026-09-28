from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.data_integrity import DataIntegrityError, inspect_runtime_event_jsonl
from src.kalshi_public import (
    EndpointValidationError,
    KalshiPublicAPIError,
    KalshiPublicClient,
)
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.run_validation import RunValidationError, validate_run_manifest
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


def make_response(
    *,
    status_code: int,
    body: str,
    reason: str,
    url: str = "https://example.test/markets",
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.reason = reason
    response.url = url
    response.encoding = "utf-8"
    response.headers["Content-Type"] = "application/json"
    response._content = body.encode("utf-8")
    return response


def read_jsonl(root: Path) -> list[dict]:
    paths = list(root.rglob("*.jsonl"))
    if len(paths) != 1:
        raise AssertionError(f"Expected one JSONL file, found {paths}")
    return [
        json.loads(line)
        for line in paths[0].read_text(encoding="utf-8").splitlines()
    ]


def fixed_git_info(_: Path) -> dict:
    return {
        "git_commit": "9" * 40,
        "git_worktree_dirty": False,
        "git_error": None,
    }


class RuntimeObservabilityTests(unittest.TestCase):
    def test_event_logger_sequences_redacts_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = RuntimeEventLogger(
                root,
                run_id="test_run_1",
                collector_name="test_collector",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            logger.emit(
                "collector.started",
                severity="info",
                message="Collector started",
                context={"api_token": "must-not-appear", "ticker": "TEST"},
            )
            logger.emit(
                "collector.completed",
                severity="info",
                message="Collector workload completed",
                context={"rows": 1},
            )

            records = read_jsonl(root)
            descriptor = inspect_runtime_event_jsonl(logger.output_path)

        self.assertEqual([record["sequence"] for record in records], [1, 2])
        self.assertEqual(
            records[0]["context"]["api_token"],
            "[REDACTED]",
        )
        self.assertNotIn("must-not-appear", json.dumps(records))
        self.assertEqual(descriptor["event_count"], 2)
        self.assertEqual(descriptor["run_ids"], ["test_run_1"])
        self.assertEqual(descriptor["collectors"], ["test_collector"])

    def test_event_logger_rejects_non_finite_json_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = RuntimeEventLogger(
                Path(temp_dir),
                run_id="test_run_non_finite",
                collector_name="test_collector",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )

            with self.assertRaises(RuntimeEventWriteError):
                logger.emit(
                    "collector.started",
                    severity="info",
                    message="Collector started",
                    context={"invalid_metric": float("nan")},
                )

        self.assertEqual(logger.written_paths, ())

    def test_runtime_inspector_rejects_non_standard_nan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime.jsonl"
            text = (
                '{"schema_version":"runtime_event.v1","event_id":"event-1",'
                '"sequence":1,"event_name":"collector.started",'
                '"severity":"info",'
                '"occurred_at_utc":"2026-08-03T12:00:00.000000Z",'
                '"occurred_monotonic_ns":1,"run_id":"run-1",'
                '"collector":"test_collector","message":"Collector started",'
                '"correlation":null,"context":{"invalid_metric":NaN},'
                '"error":null}'
            )
            path.write_text(text + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                DataIntegrityError,
                "invalid strict JSON",
            ):
                inspect_runtime_event_jsonl(path)

    def test_success_event_correlates_to_persisted_raw_record(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":[],"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_root = root / "raw"
            event_root = root / "events"
            logger = RuntimeEventLogger(
                event_root,
                run_id="run-1",
                collector_name="scan_btc_markets",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=raw_root,
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                payload = client._get("/markets")

            raw_record = read_jsonl(raw_root)[0]
            event = read_jsonl(event_root)[0]

        self.assertEqual(payload["markets"], [])
        self.assertEqual(event["event_name"], "api.request.succeeded")
        self.assertEqual(event["severity"], "info")
        self.assertEqual(
            event["correlation"]["raw_request_id"],
            raw_record["request"]["request_id"],
        )

    def test_retryable_http_failure_is_warning(self) -> None:
        response = make_response(
            status_code=429,
            body='{"error":{"message":"rate limit"}}',
            reason="Too Many Requests",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = RuntimeEventLogger(
                root / "events",
                run_id="run-2",
                collector_name="record_orderbook",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root / "raw",
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(KalshiPublicAPIError):
                    client._get("/markets")

            event = read_jsonl(root / "events")[0]

        self.assertEqual(event["event_name"], "api.request.failed")
        self.assertEqual(event["severity"], "warning")
        self.assertTrue(event["context"]["retryable"])
        self.assertEqual(event["context"]["status_code"], 429)

    def test_endpoint_validation_failure_is_archived_and_correlated(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":{},"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = RuntimeEventLogger(
                root / "events",
                run_id="run-3",
                collector_name="scan_btc_markets",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root / "raw",
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(EndpointValidationError):
                    client.list_open_markets(series_ticker="KXBTC15M")

            raw_record = read_jsonl(root / "raw")[0]
            events = read_jsonl(root / "events")

        self.assertIsNone(raw_record["error"])
        self.assertEqual(
            [event["event_name"] for event in events],
            ["api.request.succeeded", "endpoint.validation.failed"],
        )
        validation_event = events[-1]
        self.assertEqual(validation_event["severity"], "error")
        self.assertEqual(
            validation_event["context"]["validation_code"],
            "markets_field_not_list",
        )
        self.assertEqual(
            validation_event["correlation"]["raw_request_id"],
            raw_record["request"]["request_id"],
        )

    def test_non_finite_orderbook_level_is_terminal_and_correlated(self) -> None:
        response = make_response(
            status_code=200,
            body=(
                '{"orderbook_fp":{"yes_dollars":[["NaN","1"]],'
                '"no_dollars":[]}}'
            ),
            reason="OK",
            url="https://example.test/markets/TEST/orderbook",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = RuntimeEventLogger(
                root / "events",
                run_id="run-non-finite",
                collector_name="record_orderbook",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root / "raw",
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(EndpointValidationError):
                    client.get_orderbook_with_lineage("TEST")

            raw_record = read_jsonl(root / "raw")[0]
            events = read_jsonl(root / "events")

        validation_event = events[-1]
        self.assertEqual(
            validation_event["context"]["validation_code"],
            "orderbook_level_not_finite",
        )
        self.assertEqual(
            validation_event["correlation"]["raw_request_id"],
            raw_record["request"]["request_id"],
        )

    def test_orderbook_level_requires_documented_fixed_point_strings(self) -> None:
        response = make_response(
            status_code=200,
            body=(
                '{"orderbook_fp":{"yes_dollars":[[0.5,1]],'
                '"no_dollars":[]}}'
            ),
            reason="OK",
            url="https://example.test/markets/TEST/orderbook",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logger = RuntimeEventLogger(
                root / "events",
                run_id="run-fixed-point-shape",
                collector_name="record_orderbook",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root / "raw",
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(EndpointValidationError):
                    client.get_orderbook_with_lineage("TEST")

            validation_event = read_jsonl(root / "events")[-1]

        self.assertEqual(
            validation_event["context"]["validation_code"],
            "orderbook_level_not_fixed_point_strings",
        )

    def test_fails_closed_when_runtime_event_cannot_be_written(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":[],"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blocked_root = root / "blocked"
            blocked_root.write_text("not a directory", encoding="utf-8")
            logger = RuntimeEventLogger(
                blocked_root,
                run_id="run-4",
                collector_name="scan_btc_markets",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root / "raw",
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(RuntimeEventWriteError):
                    client._get("/markets")

            raw_records = read_jsonl(root / "raw")

        self.assertEqual(len(raw_records), 1)
        self.assertEqual(raw_records[0]["error"], None)

    def test_raw_persistence_failure_emits_critical_event(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":[],"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blocked_raw = root / "blocked_raw"
            blocked_raw.write_text("not a directory", encoding="utf-8")
            logger = RuntimeEventLogger(
                root / "events",
                run_id="run-5",
                collector_name="scan_btc_markets",
                started_at_utc="2026-08-03T12:00:00.000000Z",
            )
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=blocked_raw,
                runtime_events=logger,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(KalshiPublicAPIError):
                    client._get("/markets")

            event = read_jsonl(root / "events")[0]

        self.assertEqual(event["event_name"], "api.raw.persistence.failed")
        self.assertEqual(event["severity"], "critical")
        self.assertIsNone(event["correlation"])

    def test_manifest_v2_reconciles_request_events_to_raw_records(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":[],"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=repo / "data/raw",
            )
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={"series_ticker": "KXBTC15M"},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                source_sessions=[
                    {
                        "source": client.raw_recorder.source_name,
                        "session_id": client.raw_recorder.session_id,
                    }
                ],
                git_info_provider=fixed_git_info,
                runtime_observability=True,
            )
            logger = RuntimeEventLogger(
                repo / "logs/runtime",
                run_id=manifest.run_id,
                collector_name="scan_btc_markets",
                started_at_utc=manifest.started_at_utc,
            )
            client.attach_runtime_event_logger(logger)
            logger.emit(
                "collector.started",
                severity="info",
                message="Collector started",
            )
            with patch.object(client.session, "get", return_value=response):
                client._get("/markets")
            logger.emit(
                "collector.completed",
                severity="info",
                message="Collector workload completed",
            )
            manifest.complete(
                raw_files=client.raw_recorder.written_paths,
                runtime_event_files=logger.written_paths,
            )

            result = validate_run_manifest(
                manifest.manifest_path,
                repository_root=repo,
            )

        self.assertEqual(result["summary"]["raw_record_count"], 1)
        self.assertEqual(result["summary"]["runtime_event_count"], 3)

    def test_manifest_v2_rejects_raw_record_without_request_event(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":[],"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=repo / "data/raw",
            )
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={"series_ticker": "KXBTC15M"},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                source_sessions=[
                    {
                        "source": client.raw_recorder.source_name,
                        "session_id": client.raw_recorder.session_id,
                    }
                ],
                git_info_provider=fixed_git_info,
                runtime_observability=True,
            )
            logger = RuntimeEventLogger(
                repo / "logs/runtime",
                run_id=manifest.run_id,
                collector_name="scan_btc_markets",
                started_at_utc=manifest.started_at_utc,
            )
            logger.emit(
                "collector.started",
                severity="info",
                message="Collector started",
            )
            with patch.object(client.session, "get", return_value=response):
                client._get("/markets")
            logger.emit(
                "collector.completed",
                severity="info",
                message="Collector workload completed",
            )
            manifest.complete(
                raw_files=client.raw_recorder.written_paths,
                runtime_event_files=logger.written_paths,
            )

            with self.assertRaisesRegex(
                RunValidationError,
                "missing matching API request events",
            ):
                validate_run_manifest(
                    manifest.manifest_path,
                    repository_root=repo,
                )

    def test_manifest_v2_refuses_completion_without_completed_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={"series_ticker": "KXBTC15M"},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                git_info_provider=fixed_git_info,
                runtime_observability=True,
            )
            logger = RuntimeEventLogger(
                repo / "logs/runtime",
                run_id=manifest.run_id,
                collector_name="scan_btc_markets",
                started_at_utc=manifest.started_at_utc,
            )
            logger.emit(
                "collector.started",
                severity="info",
                message="Collector started",
            )

            with self.assertRaisesRegex(
                RunManifestError,
                "missing lifecycle events",
            ):
                manifest.complete(
                    raw_files=[],
                    runtime_event_files=logger.written_paths,
                )

            state = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(state["status"], "running")

    def test_terminal_collector_failure_is_preserved_in_manifest_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={"series_ticker": "KXBTC15M"},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                git_info_provider=fixed_git_info,
                runtime_observability=True,
            )
            logger = RuntimeEventLogger(
                repo / "logs/runtime",
                run_id=manifest.run_id,
                collector_name="scan_btc_markets",
                started_at_utc=manifest.started_at_utc,
            )
            logger.emit(
                "collector.started",
                severity="info",
                message="Collector started",
            )
            logger.emit(
                "collector.failed",
                severity="critical",
                message="Collector terminated",
                error={"type": "RuntimeError", "message": "terminal failure"},
            )
            manifest.fail(
                RuntimeError("terminal failure"),
                runtime_event_files=logger.written_paths,
            )
            state = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(state["schema_version"], "collection_run_manifest.v2")
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["failure"]["type"], "RuntimeError")
        self.assertEqual(state["summary"]["runtime_event_count"], 2)
        self.assertEqual(state["summary"]["runtime_error_event_count"], 1)
        self.assertEqual(state["files"][0]["role"], "runtime_event_log")

    def test_manifest_v2_validates_runtime_events_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={"series_ticker": "KXBTC15M"},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                git_info_provider=fixed_git_info,
                runtime_observability=True,
            )
            logger = RuntimeEventLogger(
                repo / "logs/runtime",
                run_id=manifest.run_id,
                collector_name="scan_btc_markets",
                started_at_utc=manifest.started_at_utc,
            )
            logger.emit(
                "collector.started",
                severity="info",
                message="Collector started",
            )
            logger.emit(
                "collector.completed",
                severity="info",
                message="Collector workload completed",
            )
            manifest.complete(
                raw_files=[],
                runtime_event_files=logger.written_paths,
                result={"orders_placed": 0},
            )

            result = validate_run_manifest(
                manifest.manifest_path,
                repository_root=repo,
            )
            event_text = logger.output_path.read_text(encoding="utf-8")
            logger.output_path.write_text(
                event_text.replace("Collector started", "Collector altered"),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RunValidationError, "Artifact mismatch"):
                validate_run_manifest(
                    manifest.manifest_path,
                    repository_root=repo,
                )

        self.assertEqual(result["summary"]["runtime_event_file_count"], 1)
        self.assertEqual(result["summary"]["runtime_event_count"], 2)
        self.assertEqual(result["summary"]["runtime_error_event_count"], 0)


if __name__ == "__main__":
    unittest.main()

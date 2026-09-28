from __future__ import annotations

from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.run_manifest import CollectionRunManifest
from src.run_validation import RunValidationError, validate_run_manifest


class SequenceFactory:
    def __init__(self, values):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


def valid_raw_record(*, request_id: str = "request-1") -> dict:
    body = '{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]}}'
    return {
        "schema_version": "raw_http_exchange.v1",
        "source": "kalshi_public_rest",
        "session_id": "kalshi-session-1",
        "request": {
            "request_id": request_id,
            "method": "GET",
            "base_url": "https://example.test",
            "path": "/markets/TEST/orderbook",
            "params": {},
            "started_at_utc": "2026-08-03T09:00:00.000000Z",
            "started_monotonic_ns": 100,
        },
        "timing": {
            "received_at_utc": "2026-08-03T09:00:00.100000Z",
            "received_monotonic_ns": 200,
            "elapsed_monotonic_ns": 100,
        },
        "response": {
            "status_code": 200,
            "reason": "OK",
            "url": "https://example.test/markets/TEST/orderbook",
            "headers": {"Content-Type": "application/json"},
            "body_text": body,
            "body_size_bytes": len(body.encode("utf-8")),
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "json_parse_error": None,
        },
        "source_timestamps": [],
        "error": None,
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def fixed_git_info(_: Path) -> dict:
    return {
        "git_commit": "8" * 40,
        "git_worktree_dirty": False,
        "git_error": None,
    }


ORDERBOOK_CSV_FIELDS = [
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "observed_at_utc",
    "ticker",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "no_bid",
    "no_ask",
    "no_spread",
]


def make_record_orderbook_manifest(
    repo: Path,
    csv_path: Path,
) -> CollectionRunManifest:
    clock = SequenceFactory(
        [
            datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 9, 1, tzinfo=timezone.utc),
        ]
    )
    ids = SequenceFactory(
        ["runidentifier", "tempstart", "tempfinish"]
    )
    return CollectionRunManifest(
        collector_name="record_orderbook",
        arguments={
            "ticker": "TEST",
            "seconds": 60,
            "output": csv_path,
            "api_token": "must-not-be-recorded",
        },
        manifest_root=repo / "data/manifests",
        repository_root=repo,
        source_sessions=[
            {
                "source": "kalshi_public_rest",
                "session_id": "kalshi-session-1",
            }
        ],
        utc_now=clock,
        id_factory=ids,
        git_info_provider=fixed_git_info,
    )


def lineage_row(
    manifest: CollectionRunManifest,
    *,
    request_id: str = "request-1",
    ticker: str = "TEST",
    run_id: str | None = None,
    source: str = "kalshi_public_rest",
    session_id: str = "kalshi-session-1",
) -> dict[str, str]:
    return {
        "run_id": run_id or manifest.run_id,
        "raw_source": source,
        "raw_session_id": session_id,
        "raw_request_id": request_id,
        "observed_at_utc": "2026-08-03T09:00:00+00:00",
        "ticker": ticker,
        "yes_bid": "0.5000",
        "yes_ask": "0.5000",
        "yes_spread": "0.0000",
        "no_bid": "0.5000",
        "no_ask": "0.5000",
        "no_spread": "0.0000",
    }


def write_lineage_csv(
    path: Path,
    rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ORDERBOOK_CSV_FIELDS,
        )
        writer.writeheader()
        writer.writerows(rows)


class RunManifestTests(unittest.TestCase):
    def test_completed_manifest_validates_and_records_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            raw_path = repo / "data/raw/kalshi_rest/2026/08/03/session.jsonl"
            csv_path = repo / "logs/test.csv"

            write_jsonl(raw_path, [valid_raw_record()])
            manifest = make_record_orderbook_manifest(repo, csv_path)
            write_lineage_csv(
                csv_path,
                [lineage_row(manifest)],
            )

            running_state = json.loads(manifest.manifest_path.read_text())
            self.assertEqual(running_state["status"], "running")
            self.assertEqual(running_state["files"], [])

            manifest.complete(
                raw_files=[raw_path],
                derived_csv_files=[csv_path],
                result={
                    "successful_csv_rows": 1,
                    "orders_placed": 0,
                },
            )
            completed_state = json.loads(
                manifest.manifest_path.read_text()
            )
            result = validate_run_manifest(
                manifest.manifest_path,
                repository_root=repo,
            )

        self.assertEqual(completed_state["status"], "completed")
        self.assertEqual(
            completed_state["arguments"]["api_token"],
            "[REDACTED]",
        )
        self.assertEqual(
            completed_state["summary"]["raw_record_count"],
            1,
        )
        self.assertEqual(
            completed_state["summary"]["derived_row_count"],
            1,
        )
        self.assertEqual(
            completed_state["code"]["git_worktree_dirty"],
            False,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["summary"]["raw_error_record_count"],
            0,
        )
        self.assertEqual(
            completed_state["files"][0]["path"],
            {
                "kind": "repository_relative",
                "value": (
                    "data/raw/kalshi_rest/2026/08/03/"
                    "session.jsonl"
                ),
            },
        )

    def test_validator_detects_artifact_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            raw_path = repo / "data/raw/session.jsonl"
            write_jsonl(raw_path, [valid_raw_record()])

            clock = SequenceFactory(
                [
                    datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
                    datetime(2026, 8, 3, 9, 1, tzinfo=timezone.utc),
                ]
            )
            ids = SequenceFactory(["runidentifier", "tempstart", "tempfinish"])
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={"series_ticker": "KXBTC15M"},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                utc_now=clock,
                id_factory=ids,
                git_info_provider=fixed_git_info,
            )
            manifest.complete(raw_files=[raw_path])

            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(valid_raw_record(request_id="request-2")))
                handle.write("\n")

            with self.assertRaisesRegex(RunValidationError, "Artifact mismatch"):
                validate_run_manifest(manifest.manifest_path, repository_root=repo)

    def test_running_manifest_is_rejected_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            clock = SequenceFactory(
                [datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)]
            )
            ids = SequenceFactory(["runidentifier", "tempstart"])
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                utc_now=clock,
                id_factory=ids,
                git_info_provider=fixed_git_info,
            )

            with self.assertRaisesRegex(RunValidationError, "only completed runs"):
                validate_run_manifest(manifest.manifest_path, repository_root=repo)

    def test_failed_manifest_preserves_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            clock = SequenceFactory(
                [
                    datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc),
                    datetime(2026, 8, 3, 9, 1, tzinfo=timezone.utc),
                ]
            )
            ids = SequenceFactory(["runidentifier", "tempstart", "tempfinish"])
            manifest = CollectionRunManifest(
                collector_name="scan_btc_markets",
                arguments={},
                manifest_root=repo / "data/manifests",
                repository_root=repo,
                utc_now=clock,
                id_factory=ids,
                git_info_provider=fixed_git_info,
            )
            manifest.fail(RuntimeError("collector stopped"))
            state = json.loads(manifest.manifest_path.read_text())

        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["failure"]["type"], "RuntimeError")
        self.assertEqual(state["failure"]["message"], "collector stopped")


    def test_validator_rejects_unknown_raw_request_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            raw_path = repo / "data/raw/session.jsonl"
            csv_path = repo / "logs/test.csv"

            write_jsonl(raw_path, [valid_raw_record()])
            manifest = make_record_orderbook_manifest(repo, csv_path)
            write_lineage_csv(
                csv_path,
                [
                    lineage_row(
                        manifest,
                        request_id="missing-request",
                    )
                ],
            )
            manifest.complete(
                raw_files=[raw_path],
                derived_csv_files=[csv_path],
            )

            with self.assertRaisesRegex(
                RunValidationError,
                "does not match any raw record",
            ):
                validate_run_manifest(
                    manifest.manifest_path,
                    repository_root=repo,
                )

    def test_validator_rejects_duplicate_derived_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            raw_path = repo / "data/raw/session.jsonl"
            csv_path = repo / "logs/test.csv"

            write_jsonl(raw_path, [valid_raw_record()])
            manifest = make_record_orderbook_manifest(repo, csv_path)
            row = lineage_row(manifest)
            write_lineage_csv(csv_path, [row, row])
            manifest.complete(
                raw_files=[raw_path],
                derived_csv_files=[csv_path],
            )

            with self.assertRaisesRegex(
                RunValidationError,
                "duplicate derived reference",
            ):
                validate_run_manifest(
                    manifest.manifest_path,
                    repository_root=repo,
                )

    def test_validator_rejects_missing_derived_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            raw_path = repo / "data/raw/session.jsonl"
            csv_path = repo / "logs/test.csv"

            write_jsonl(
                raw_path,
                [
                    valid_raw_record(request_id="request-1"),
                    valid_raw_record(request_id="request-2"),
                ],
            )
            manifest = make_record_orderbook_manifest(repo, csv_path)
            write_lineage_csv(
                csv_path,
                [
                    lineage_row(
                        manifest,
                        request_id="request-1",
                    )
                ],
            )
            manifest.complete(
                raw_files=[raw_path],
                derived_csv_files=[csv_path],
            )

            with self.assertRaisesRegex(
                RunValidationError,
                "missing derived CSV rows",
            ):
                validate_run_manifest(
                    manifest.manifest_path,
                    repository_root=repo,
                )

    def test_validator_rejects_ticker_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            raw_path = repo / "data/raw/session.jsonl"
            csv_path = repo / "logs/test.csv"

            write_jsonl(raw_path, [valid_raw_record()])
            manifest = make_record_orderbook_manifest(repo, csv_path)
            write_lineage_csv(
                csv_path,
                [
                    lineage_row(
                        manifest,
                        ticker="OTHER",
                    )
                ],
            )
            manifest.complete(
                raw_files=[raw_path],
                derived_csv_files=[csv_path],
            )

            with self.assertRaisesRegex(
                RunValidationError,
                "does not match raw request ticker",
            ):
                validate_run_manifest(
                    manifest.manifest_path,
                    repository_root=repo,
                )


if __name__ == "__main__":
    unittest.main()

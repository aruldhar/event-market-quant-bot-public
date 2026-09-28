import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.kalshi_public import KalshiPublicAPIError, KalshiPublicClient


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
    response.headers["Date"] = "Mon, 03 Aug 2026 08:05:00 GMT"
    response.headers["Set-Cookie"] = "session=must-not-be-logged"
    response._content = body.encode("utf-8")
    return response


def read_only_record(root: Path) -> dict[str, object]:
    paths = list(root.rglob("*.jsonl"))
    if len(paths) != 1:
        raise AssertionError(f"Expected one JSONL file, found {paths}")
    lines = paths[0].read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise AssertionError(f"Expected one record, found {len(lines)}")
    return json.loads(lines[0])


class RawJsonLoggingTests(unittest.TestCase):
    def test_logs_success_before_returning_payload(self) -> None:
        body = (
            '{"markets":[{"ticker":"TEST",'
            '"close_time":"2026-08-03T08:15:00Z"}],"cursor":""}\n'
        )
        response = make_response(
            status_code=200,
            body=body,
            reason="OK",
            url=(
                "https://example.test/markets?status=open&"
                "api_key=must-not-be-logged"
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root,
            )
            with patch.object(client.session, "get", return_value=response):
                payload = client._get(
                    "/markets",
                    params={
                        "status": "open",
                        "limit": 1000,
                        "api_key": "must-not-be-logged",
                    },
                )

            self.assertEqual(payload["markets"][0]["ticker"], "TEST")
            record = read_only_record(root)
            written_paths = client.raw_recorder.written_paths

        self.assertEqual(len(written_paths), 1)
        self.assertEqual(written_paths[0].suffix, ".jsonl")
        self.assertEqual(record["schema_version"], "raw_http_exchange.v1")
        self.assertEqual(record["source"], "kalshi_public_rest")
        self.assertEqual(record["request"]["method"], "GET")
        self.assertEqual(record["request"]["path"], "/markets")
        self.assertEqual(
            record["request"]["params"],
            {
                "status": "open",
                "limit": 1000,
                "api_key": "[REDACTED]",
            },
        )
        self.assertIsInstance(record["request"]["started_monotonic_ns"], int)
        self.assertIsInstance(record["timing"]["received_monotonic_ns"], int)
        self.assertGreaterEqual(record["timing"]["elapsed_monotonic_ns"], 0)
        self.assertEqual(record["response"]["status_code"], 200)
        self.assertNotIn("must-not-be-logged", json.dumps(record))
        self.assertNotIn("Set-Cookie", record["response"]["headers"])
        self.assertIn("Content-Type", record["response"]["headers"])
        self.assertEqual(record["response"]["body_text"], body)
        self.assertEqual(
            record["response"]["body_sha256"],
            hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(record["error"], None)
        self.assertIn(
            {
                "json_path": "$.markets[0].close_time",
                "value": "2026-08-03T08:15:00Z",
            },
            record["source_timestamps"],
        )

    def test_logs_http_error_payload_before_raising(self) -> None:
        body = '{"error":{"message":"rate limit"}}'
        response = make_response(
            status_code=429,
            body=body,
            reason="Too Many Requests",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root,
            )
            with patch.object(client.session, "get", return_value=response):
                with self.assertRaises(KalshiPublicAPIError):
                    client._get("/markets")

            record = read_only_record(root)

        self.assertEqual(record["response"]["status_code"], 429)
        self.assertEqual(record["response"]["body_text"], body)
        self.assertEqual(record["error"]["stage"], "http_status")

    def test_logs_invalid_json_before_raising(self) -> None:
        body = "not-json"
        response = make_response(status_code=200, body=body, reason="OK")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root,
            )
            with patch.object(client.session, "get", return_value=response):
                with self.assertRaisesRegex(
                    KalshiPublicAPIError,
                    "did not return valid JSON",
                ):
                    client._get("/markets")

            record = read_only_record(root)

        self.assertEqual(record["response"]["body_text"], body)
        self.assertIsNotNone(record["response"]["json_parse_error"])
        self.assertEqual(record["error"]["stage"], "json_decode")

    def test_logs_unexpected_top_level_shape_before_raising(self) -> None:
        body = '[{"ticker":"TEST"}]'
        response = make_response(status_code=200, body=body, reason="OK")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root,
            )
            with patch.object(client.session, "get", return_value=response):
                with self.assertRaisesRegex(
                    KalshiPublicAPIError,
                    "unexpected JSON shape",
                ):
                    client._get("/markets")

            record = read_only_record(root)

        self.assertEqual(record["response"]["body_text"], body)
        self.assertEqual(record["error"]["stage"], "shape_validation")

    def test_logs_transport_error_without_a_response(self) -> None:
        transport_error = requests.ConnectionError("network unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root,
            )
            with patch.object(client.session, "get", side_effect=transport_error):
                with self.assertRaisesRegex(
                    KalshiPublicAPIError,
                    "network unavailable",
                ):
                    client._get("/markets", params={"status": "open"})

            record = read_only_record(root)

        self.assertIsNone(record["response"])
        self.assertEqual(record["request"]["params"], {"status": "open"})
        self.assertEqual(record["error"]["stage"], "transport")
        self.assertEqual(record["error"]["type"], "ConnectionError")

    def test_fails_closed_when_raw_record_cannot_be_written(self) -> None:
        response = make_response(
            status_code=200,
            body='{"markets":[],"cursor":""}',
            reason="OK",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            blocked_root = Path(temp_dir) / "not_a_directory"
            blocked_root.write_text("file blocks directory creation", encoding="utf-8")
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=blocked_root,
            )

            with patch.object(client.session, "get", return_value=response):
                with self.assertRaisesRegex(
                    KalshiPublicAPIError,
                    "required raw record could not be saved",
                ):
                    client._get("/markets")


    def test_returns_lineage_matching_the_persisted_raw_record(self) -> None:
        body = (
            '{"orderbook_fp":{'
            '"yes_dollars":[["0.4200","3.00"]],'
            '"no_dollars":[["0.5600","2.00"]]'
            '}}'
        )
        response = make_response(
            status_code=200,
            body=body,
            reason="OK",
            url="https://example.test/markets/TEST/orderbook",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            client = KalshiPublicClient(
                base_url="https://example.test",
                raw_log_root=root,
            )

            with patch.object(client.session, "get", return_value=response):
                sourced_orderbook = client.get_orderbook_with_lineage("TEST")

            record = read_only_record(root)

        self.assertEqual(
            sourced_orderbook.orderbook["yes_dollars"],
            [["0.4200", "3.00"]],
        )
        self.assertEqual(
            sourced_orderbook.raw_record.source,
            record["source"],
        )
        self.assertEqual(
            sourced_orderbook.raw_record.session_id,
            record["session_id"],
        )
        self.assertEqual(
            sourced_orderbook.raw_record.request_id,
            record["request"]["request_id"],
        )
        self.assertEqual(
            record["request"]["path"],
            "/markets/TEST/orderbook",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json

import pytest
import requests

from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError
from src.runtime_events import RuntimeEventLogger


class FakeSession:
    def __init__(self, response):
        self.responses = list(response) if isinstance(response, (list, tuple)) else [response]
        self.headers = {}
        self.calls = 0

    def get(self, url, params, timeout):
        index = min(self.calls, len(self.responses) - 1)
        response = self.responses[index]
        self.calls += 1
        response.url = url
        return response


def _response(body: bytes, status: int = 200, content_type: str = "application/json"):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.reason = "OK" if status == 200 else "ERROR"
    response.headers["Content-Type"] = content_type
    return response


def _raw_records(client):
    [raw_path] = client.raw_recorder.written_paths
    return [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]


def test_valid_response_is_archived_before_return(tmp_path):
    client = PublicCensusHttpClient(
        base_url="https://example.com",
        source_name="test_public",
        raw_root=tmp_path,
    )
    client.session = FakeSession(_response(b'{"data": []}'))
    result = client.get_json("/markets")
    assert result.payload == {"data": []}
    [record] = _raw_records(client)
    assert record["response"]["body_text"] == '{"data": []}'
    assert record["request"]["request_id"] == result.raw_record.request_id


def test_invalid_json_is_still_archived_before_failure(tmp_path):
    client = PublicCensusHttpClient(
        base_url="https://example.com",
        source_name="test_public",
        raw_root=tmp_path,
    )
    client.session = FakeSession(_response(b"not-json", content_type="text/plain"))
    with pytest.raises(PublicCensusHttpError, match="valid JSON"):
        client.get_json("/markets")
    [record] = _raw_records(client)
    assert record["response"]["body_text"] == "not-json"
    assert record["error"]["stage"] == "json_decode"


def test_non_rate_limit_http_error_is_archived_and_rejected_without_retry(tmp_path):
    sleeps = []
    client = PublicCensusHttpClient(
        base_url="https://example.com",
        source_name="test_public",
        raw_root=tmp_path,
        sleep_fn=sleeps.append,
    )
    client.session = FakeSession(_response(b'{"error":"bad"}', status=500))
    with pytest.raises(PublicCensusHttpError, match="HTTP 500"):
        client.get_json("/markets")
    [record] = _raw_records(client)
    assert record["response"]["status_code"] == 500
    assert record["error"]["stage"] == "http_status"
    assert sleeps == []
    assert client.session.calls == 1


def test_rate_limit_retries_preserve_every_attempt_before_success(tmp_path):
    sleeps = []
    client = PublicCensusHttpClient(
        base_url="https://example.com",
        source_name="test_public",
        raw_root=tmp_path,
        max_rate_limit_retries=4,
        rate_limit_backoff_seconds=0.5,
        sleep_fn=sleeps.append,
    )
    client.session = FakeSession([
        _response(b'{"error":"too many requests"}', status=429),
        _response(b'{"error":"too many requests"}', status=429),
        _response(b'{"data": []}', status=200),
    ])

    result = client.get_json("/markets")

    assert result.payload == {"data": []}
    records = _raw_records(client)
    assert [record["response"]["status_code"] for record in records] == [429, 429, 200]
    assert len({record["request"]["request_id"] for record in records}) == 3
    assert sleeps == [0.5, 1.0]
    assert client.session.calls == 3


def test_rate_limit_exhaustion_fails_closed_after_archiving_all_attempts(tmp_path):
    sleeps = []
    client = PublicCensusHttpClient(
        base_url="https://example.com",
        source_name="test_public",
        raw_root=tmp_path,
        max_rate_limit_retries=2,
        rate_limit_backoff_seconds=0.25,
        sleep_fn=sleeps.append,
    )
    client.session = FakeSession([
        _response(b'{"error":"too many requests"}', status=429),
        _response(b'{"error":"too many requests"}', status=429),
        _response(b'{"error":"too many requests"}', status=429),
    ])

    with pytest.raises(PublicCensusHttpError, match="429 after 3 archived attempts"):
        client.get_json("/markets")

    records = _raw_records(client)
    assert [record["response"]["status_code"] for record in records] == [429, 429, 429]
    assert sleeps == [0.25, 0.5]
    assert client.session.calls == 3



def test_rate_limit_retry_emits_schema_valid_runtime_events(tmp_path):
    sleeps = []
    runtime = RuntimeEventLogger(
        tmp_path / "runtime",
        run_id="test_public_census_retry",
        collector_name="collect_opportunity_census",
        started_at_utc="2026-08-09T04:00:00.000000Z",
    )
    client = PublicCensusHttpClient(
        base_url="https://example.com",
        source_name="test_public",
        raw_root=tmp_path / "raw",
        max_rate_limit_retries=1,
        rate_limit_backoff_seconds=0.5,
        runtime_events=runtime,
        sleep_fn=sleeps.append,
    )
    client.session = FakeSession([
        _response(b'{"error":"too many requests"}', status=429),
        _response(b'{"data": []}', status=200),
    ])

    result = client.get_json("/events")

    assert result.payload == {"data": []}
    assert sleeps == [0.5]
    runtime_records = [
        json.loads(line)
        for line in runtime.output_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event_name"] for record in runtime_records] == [
        "api.request.failed",
        "api.request.retry.scheduled",
        "api.request.succeeded",
    ]

def test_negative_retry_configuration_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="max_rate_limit_retries"):
        PublicCensusHttpClient(
            base_url="https://example.com",
            source_name="test_public",
            raw_root=tmp_path,
            max_rate_limit_retries=-1,
        )

import json

import pytest

from src.kxbtcd_candidate_e_prospective_live_collector import (
    ProspectiveLiveCollectorError,
    RawJournal,
)
from src.kxbtcd_candidate_e_restart_reconciliation import (
    RestartReconciliationError,
    RestartSessionRawJournal,
)
from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournal,
    RuntimeRawJournalError,
)


SAFE_IDENTITY = {
    "method": "GET",
    "url": "https://example.invalid/markets",
    "params": {
        "series_ticker": "KXBTCD",
        "status": "open",
        "limit": 1000,
    },
    "status_code": 200,
    "elapsed_monotonic_ns": 1234,
}

SAFE_COINBASE_RECOVERY_IDENTITIES = (
    {
        "method": "GET",
        "url": "https://api.exchange.coinbase.com/products/BTC-USD/trades",
        "params": {"limit": 1000},
        "status_code": 200,
        "phase": "latest_visibility",
        "latest_attempt_index": 1,
        "cb_before": "newer-cursor",
        "cb_after": "older-cursor",
    },
    {
        "method": "GET",
        "url": "https://api.exchange.coinbase.com/products/BTC-USD/trades",
        "params": {"limit": 1000, "after": "older-cursor"},
        "status_code": 200,
        "phase": "older_pagination",
        "latest_attempt_index": None,
        "cb_before": None,
        "cb_after": None,
    },
)

DANGEROUS_IDENTITIES = (
    {"headers": {"KALSHI-ACCESS-KEY": "SENTINEL_KEY_ID"}},
    {"KALSHI-ACCESS-KEY": "SENTINEL_KEY_ID"},
    {"KALSHI-ACCESS-SIGNATURE": "SENTINEL_SIGNATURE"},
    {"authorization": "Bearer SENTINEL_TOKEN"},
    {"cookie": "session=SENTINEL_COOKIE"},
    {"private_key": "SENTINEL_PRIVATE_KEY"},
    {"params": {"api_key": "SENTINEL_PARAM_KEY"}},
    {"params": {"nested": {"token": "SENTINEL_NESTED_TOKEN"}}},
    {"url": "https://example.invalid/markets?token=SENTINEL_URL_TOKEN"},
    {"channel": "Bearer SENTINEL_CHANNEL_TOKEN"},
    {"channel": "SYNTHETIC PRIVATE KEY-----SENTINEL_PRIVATE_KEY"},
)

SENTINEL_BYTES = (
    b"SENTINEL_KEY_ID",
    b"SENTINEL_SIGNATURE",
    b"SENTINEL_TOKEN",
    b"SENTINEL_COOKIE",
    b"SENTINEL_PRIVATE_KEY",
    b"SENTINEL_PARAM_KEY",
    b"SENTINEL_NESTED_TOKEN",
    b"SENTINEL_URL_TOKEN",
    b"SENTINEL_CHANNEL_TOKEN",
)


def _assert_no_sentinel(path):
    data = path.read_bytes() if path.exists() else b""
    for sentinel in SENTINEL_BYTES:
        assert sentinel not in data


def test_prospective_raw_journal_accepts_current_safe_rest_identity(tmp_path):
    path = tmp_path / "prospective.jsonl"
    journal = RawJournal(path)
    journal.append(
        source="kalshi_production_rest",
        transport="https_rest",
        raw_text='{"markets":[]}',
        received_monotonic_ns=100,
        received_utc="2026-09-04T06:00:00Z",
        request_identity=SAFE_IDENTITY,
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["request_identity"] == SAFE_IDENTITY


@pytest.mark.parametrize("identity", DANGEROUS_IDENTITIES)
def test_prospective_raw_journal_rejects_sensitive_request_identity(
    tmp_path,
    identity,
):
    path = tmp_path / "prospective_blocked.jsonl"
    journal = RawJournal(path)
    with pytest.raises(ProspectiveLiveCollectorError):
        journal.append(
            source="kalshi_production_rest",
            transport="https_rest",
            raw_text='{"markets":[]}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity=identity,
        )
    _assert_no_sentinel(path)


def test_runtime_raw_journal_accepts_current_safe_rest_identity(tmp_path):
    path = tmp_path / "runtime.jsonl"
    with RuntimeRawJournal(path) as journal:
        journal.append(
            source="kalshi_production_rest",
            transport="https_rest",
            raw_text='{"markets":[]}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity=SAFE_IDENTITY,
        )
        assert journal.record_count == 1
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["request_identity"] == SAFE_IDENTITY


@pytest.mark.parametrize("identity", DANGEROUS_IDENTITIES)
def test_runtime_raw_journal_rejects_sensitive_request_identity(
    tmp_path,
    identity,
):
    path = tmp_path / "runtime_blocked.jsonl"
    with RuntimeRawJournal(path) as journal:
        with pytest.raises(RuntimeRawJournalError):
            journal.append(
                source="kalshi_production_rest",
                transport="https_rest",
                raw_text='{"markets":[]}',
                received_monotonic_ns=100,
                received_utc="2026-09-04T06:00:00Z",
                request_identity=identity,
            )
        assert journal.record_count == 0
    assert path.read_bytes() == b""
    _assert_no_sentinel(path)


def test_restart_raw_journal_accepts_current_safe_rest_identity(tmp_path):
    path = tmp_path / "restart.jsonl"
    with RestartSessionRawJournal(
        path,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as journal:
        journal.append(
            source="kalshi_production_rest",
            transport="https_rest",
            raw_text='{"markets":[]}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity=SAFE_IDENTITY,
        )
        assert journal.record_count == 1
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["request_identity"] == SAFE_IDENTITY


@pytest.mark.parametrize("identity", DANGEROUS_IDENTITIES)
def test_restart_raw_journal_rejects_sensitive_request_identity(
    tmp_path,
    identity,
):
    path = tmp_path / "restart_blocked.jsonl"
    with RestartSessionRawJournal(
        path,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as journal:
        with pytest.raises(RestartReconciliationError):
            journal.append(
                source="kalshi_production_rest",
                transport="https_rest",
                raw_text='{"markets":[]}',
                received_monotonic_ns=100,
                received_utc="2026-09-04T06:00:00Z",
                request_identity=identity,
            )
        assert journal.record_count == 0
    assert path.read_bytes() == b""
    _assert_no_sentinel(path)


def test_safe_websocket_channel_identity_is_allowed_across_journals(tmp_path):
    identity = {"channel": "orderbook_delta"}

    prospective = tmp_path / "prospective_ws.jsonl"
    RawJournal(prospective).append(
        source="kalshi_production_ws",
        transport="wss",
        raw_text='{"type":"subscribed"}',
        received_monotonic_ns=100,
        received_utc="2026-09-04T06:00:00Z",
        request_identity=identity,
    )

    runtime = tmp_path / "runtime_ws.jsonl"
    with RuntimeRawJournal(runtime) as journal:
        journal.append(
            source="kalshi_production_ws",
            transport="wss",
            raw_text='{"type":"subscribed"}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity=identity,
        )

    restart = tmp_path / "restart_ws.jsonl"
    with RestartSessionRawJournal(
        restart,
        runtime_session_id="session-1",
        raw_segment_id="segment-1",
    ) as journal:
        journal.append(
            source="kalshi_production_ws",
            transport="wss",
            raw_text='{"type":"subscribed"}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity=identity,
        )

    for path in (prospective, runtime, restart):
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["request_identity"] == identity


@pytest.mark.parametrize("identity", SAFE_COINBASE_RECOVERY_IDENTITIES)
def test_runtime_raw_journal_accepts_existing_coinbase_recovery_metadata(
    tmp_path,
    identity,
):
    path = tmp_path / "coinbase_recovery.jsonl"
    with RuntimeRawJournal(path) as journal:
        journal.append(
            source="coinbase_exchange_rest",
            transport="https_rest",
            raw_text='[]',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity=identity,
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["request_identity"] == identity


def test_runtime_raw_journal_accepts_existing_coinbase_ws_product_id(tmp_path):
    path = tmp_path / "coinbase_ws.jsonl"
    with RuntimeRawJournal(path) as journal:
        journal.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text='{"type":"heartbeat"}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T06:00:00Z",
            request_identity={"product_id": "BTC-USD"},
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["request_identity"] == {"product_id": "BTC-USD"}


@pytest.mark.parametrize(
    "identity",
    (
        {"phase": "unexpected_phase"},
        {"latest_attempt_index": 0},
        {"latest_attempt_index": -1},
        {"cb_after": ""},
        {"product_id": "ETH-USD"},
    ),
)
def test_runtime_raw_journal_rejects_invalid_new_allowlisted_metadata(
    tmp_path,
    identity,
):
    path = tmp_path / "invalid_metadata.jsonl"
    with RuntimeRawJournal(path) as journal:
        with pytest.raises(RuntimeRawJournalError):
            journal.append(
                source="coinbase_exchange_rest",
                transport="https_rest",
                raw_text='[]',
                received_monotonic_ns=100,
                received_utc="2026-09-04T06:00:00Z",
                request_identity=identity,
            )
        assert journal.record_count == 0
    assert path.read_bytes() == b""

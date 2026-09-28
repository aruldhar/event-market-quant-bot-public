from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.predexon_subcent_backfill import (
    PAGE_LIMIT,
    SCHEMA_VERSION,
    PredexonSubcentBackfillError,
    body_sha256,
    inspect_resume_file,
    validate_raw_record,
)


def snap(ticker: str, ts: int, seq: int = 1):
    return {
        "ticker": ticker,
        "timestamp": ts,
        "yes_bids": [{"price": "50", "size": "2.0"}],
        "yes_asks": [{"price": "51", "size": "3.0"}],
        "best_bid": "50",
        "best_ask": "51",
        "bid_depth": "2.0",
        "ask_depth": "3.0",
        "sequence": seq,
        "source": "websocket",
    }


def record(ticker: str, page: int, snapshots, *, has_more: bool, key):
    body = json.dumps(
        {
            "snapshots": snapshots,
            "pagination": {
                "limit": PAGE_LIMIT,
                "count": len(snapshots),
                "pagination_key": key,
                "has_more": has_more,
            },
        },
        separators=(",", ":"),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "page_number": page,
        "request_utc": "2026-09-01T00:00:00Z",
        "receive_utc": "2026-09-01T00:00:01Z",
        "start_monotonic_ns": 1,
        "end_monotonic_ns": 2,
        "http_status": 200,
        "body_sha256": body_sha256(body),
        "body": body,
    }


def test_validate_terminal_page():
    ticker = "KXBTCD-X-T1"
    r = record(ticker, 1, [snap(ticker, 1)], has_more=False, key=None)
    count, has_more, key, first, last = validate_raw_record(
        r, ticker=ticker, expected_page_number=1
    )
    assert count == 1
    assert has_more is False
    assert key is None
    assert first == last == 1


def test_has_more_requires_key():
    ticker = "KXBTCD-X-T1"
    r = record(ticker, 1, [snap(ticker, 1)], has_more=True, key=None)
    with pytest.raises(PredexonSubcentBackfillError):
        validate_raw_record(r, ticker=ticker, expected_page_number=1)


def test_body_hash_tamper_fails():
    ticker = "KXBTCD-X-T1"
    r = record(ticker, 1, [snap(ticker, 1)], has_more=False, key=None)
    r["body_sha256"] = "0" * 64
    with pytest.raises(PredexonSubcentBackfillError):
        validate_raw_record(r, ticker=ticker, expected_page_number=1)


def test_resume_two_pages_complete(tmp_path: Path):
    ticker = "KXBTCD-X-T1"
    path = tmp_path / "raw.jsonl"
    rows = [
        record(ticker, 1, [snap(ticker, 1)], has_more=True, key="opaque-1"),
        record(ticker, 2, [snap(ticker, 2)], has_more=False, key=None),
    ]
    path.write_text(
        "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in rows),
        encoding="utf-8",
    )
    state = inspect_resume_file(path, ticker=ticker)
    assert state.complete
    assert state.page_count == 2
    assert state.snapshot_count == 2
    assert state.next_pagination_key is None


def test_resume_incomplete_returns_opaque_key(tmp_path: Path):
    ticker = "KXBTCD-X-T1"
    path = tmp_path / "raw.jsonl"
    row = record(ticker, 1, [snap(ticker, 1)], has_more=True, key="opaque-1")
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    state = inspect_resume_file(path, ticker=ticker)
    assert not state.complete
    assert state.next_pagination_key == "opaque-1"


def test_cross_page_timestamp_backwards_fails(tmp_path: Path):
    ticker = "KXBTCD-X-T1"
    path = tmp_path / "raw.jsonl"
    rows = [
        record(ticker, 1, [snap(ticker, 10)], has_more=True, key="opaque-1"),
        record(ticker, 2, [snap(ticker, 9)], has_more=False, key=None),
    ]
    path.write_text(
        "".join(json.dumps(x) + "\n" for x in rows),
        encoding="utf-8",
    )
    with pytest.raises(PredexonSubcentBackfillError):
        inspect_resume_file(path, ticker=ticker)

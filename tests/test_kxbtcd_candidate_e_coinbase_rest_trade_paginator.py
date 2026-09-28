import json

from src.kxbtcd_candidate_e_coinbase_rest_trade_paginator import (
    fetch_recovery_pages,
)
from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournal,
)


def _trade(trade_id):
    return {
        "trade_id": trade_id,
        "time": "2026-09-04T03:22:00Z",
        "price": str(80000 + trade_id),
        "size": "0.01",
        "side": "sell",
    }


class FakeResponse:
    def __init__(
        self,
        rows,
        *,
        after=None,
        before=None,
        status=200,
    ):
        self.status_code = status
        self.text = json.dumps(rows)
        self.headers = {}

        if after is not None:
            self.headers["CB-AFTER"] = after

        if before is not None:
            self.headers["CB-BEFORE"] = before

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(
        self,
        url,
        *,
        params,
        timeout,
    ):
        self.calls.append({
            "url": url,
            "params": dict(params),
            "timeout": timeout,
        })

        if not self.responses:
            raise AssertionError(
                "unexpected extra HTTP request"
            )

        return self.responses.pop(0)


def test_single_latest_page_can_prove_recovery(
    tmp_path,
):
    session = FakeSession([
        FakeResponse([
            _trade(105),
            _trade(104),
            _trade(103),
            _trade(100),
        ], after="older-1"),
    ])

    with RuntimeRawJournal(
        tmp_path / "raw.jsonl"
    ) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
        )

    assert (
        result.evidence.coverage_proven
        is True
    )
    assert len(result.pages) == 1
    assert session.calls[0]["params"] == {
        "limit": 1000,
    }


def test_after_cursor_walks_to_older_page(
    tmp_path,
):
    session = FakeSession([
        FakeResponse(
            [
                _trade(110),
                _trade(109),
                _trade(108),
            ],
            after="cursor-old-1",
        ),
        FakeResponse(
            [
                _trade(107),
                _trade(105),
                _trade(100),
            ],
            after="cursor-old-2",
        ),
    ])

    with RuntimeRawJournal(
        tmp_path / "raw.jsonl"
    ) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
        )

    assert (
        result.evidence.coverage_proven
        is True
    )
    assert len(result.pages) == 2

    assert session.calls[1]["params"] == {
        "limit": 1000,
        "after": "cursor-old-1",
    }


def test_stops_fail_closed_when_no_older_cursor(
    tmp_path,
):
    session = FakeSession([
        FakeResponse([
            _trade(105),
            _trade(104),
        ]),
    ])

    with RuntimeRawJournal(
        tmp_path / "raw.jsonl"
    ) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
        )

    assert (
        result.evidence.coverage_proven
        is False
    )
    assert (
        result.evidence.target_trade_seen
        is True
    )
    assert (
        result.evidence.boundary_trade_seen
        is False
    )


def test_raw_response_is_visible_before_parsing(
    tmp_path,
):
    path = tmp_path / "raw.jsonl"

    session = FakeSession([
        FakeResponse([
            _trade(105),
            _trade(100),
        ]),
    ])

    with RuntimeRawJournal(path) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
        )

        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()

        assert len(lines) == 1

        outer = json.loads(lines[0])

        assert (
            outer["source"]
            == "coinbase_exchange_rest"
        )

        assert json.loads(
            outer["raw_text"]
        )[0]["trade_id"] == 105

    assert result.evidence.coverage_proven


def test_numeric_trade_id_holes_do_not_block_cursor_coverage(
    tmp_path,
):
    session = FakeSession([
        FakeResponse([
            _trade(105),
            _trade(103),
            _trade(100),
        ]),
    ])

    with RuntimeRawJournal(
        tmp_path / "raw.jsonl"
    ) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
        )

    assert result.evidence.coverage_proven
    assert [
        row["trade_id"]
        for row
        in result.evidence.interval_rows
    ] == [103, 105]


def test_retries_latest_page_when_rest_lags_websocket(
    tmp_path,
    monkeypatch,
):
    # First REST snapshot is behind the WebSocket target.
    # The paginator MUST request latest again, not paginate older.
    session = FakeSession([
        FakeResponse(
            [
                _trade(98),
                _trade(97),
            ],
            after="old-from-stale-page",
        ),
        FakeResponse(
            [
                _trade(105),
                _trade(104),
                _trade(103),
                _trade(100),
            ],
            after="old-from-current-page",
        ),
    ])

    sleeps = []

    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_coinbase_rest_trade_paginator.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    with RuntimeRawJournal(
        tmp_path / "raw.jsonl"
    ) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
            max_latest_attempts=3,
            latest_retry_sleep_seconds=0.5,
        )

    assert result.evidence.coverage_proven
    assert (
        result.latest_target_watermark_reached
        is True
    )
    assert result.latest_attempt_count == 2

    # Critical invariant: both first requests are unpaginated latest.
    assert session.calls[0]["params"] == {
        "limit": 1000,
    }
    assert session.calls[1]["params"] == {
        "limit": 1000,
    }

    assert sleeps == [0.5]

    assert result.pages[0].phase == (
        "latest_visibility"
    )
    assert result.pages[1].phase == (
        "latest_visibility"
    )


def test_latest_visibility_timeout_fails_closed_without_paging_older(
    tmp_path,
    monkeypatch,
):
    session = FakeSession([
        FakeResponse(
            [_trade(98), _trade(97)],
            after="older-1",
        ),
        FakeResponse(
            [_trade(99), _trade(98)],
            after="older-2",
        ),
    ])

    monkeypatch.setattr(
        "src.kxbtcd_candidate_e_coinbase_rest_trade_paginator.time.sleep",
        lambda seconds: None,
    )

    with RuntimeRawJournal(
        tmp_path / "raw.jsonl"
    ) as journal:
        result = fetch_recovery_pages(
            session=session,
            journal=journal,
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
            max_latest_attempts=2,
            latest_retry_sleep_seconds=0,
        )

    assert (
        result.evidence.coverage_proven
        is False
    )
    assert (
        result.latest_target_watermark_reached
        is False
    )
    assert result.latest_attempt_count == 2

    # We must never follow the stale pages' CB-AFTER cursors.
    assert session.calls == [
        {
            "url":
                "https://api.exchange.coinbase.com/"
                "products/BTC-USD/trades",
            "params": {"limit": 1000},
            "timeout": 10.0,
        },
        {
            "url":
                "https://api.exchange.coinbase.com/"
                "products/BTC-USD/trades",
            "params": {"limit": 1000},
            "timeout": 10.0,
        },
    ]

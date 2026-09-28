import json

import src.kxbtcd_candidate_e_runtime_raw_journal as journal_module

from src.kxbtcd_candidate_e_coinbase_ws_transport import (
    COINBASE_PRODUCT,
    COINBASE_WS_URL,
    minute_start_for_source_time,
    subscription_command,
)
from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournal,
)


def test_coinbase_subscription_is_public_market_data_only():
    command = subscription_command()

    assert COINBASE_WS_URL == (
        "wss://ws-feed.exchange.coinbase.com"
    )
    assert command == {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["matches", "heartbeat"],
    }

    assert "key" not in command
    assert "signature" not in command
    assert "passphrase" not in command


def test_source_minute_alignment_uses_coinbase_timestamp():
    assert minute_start_for_source_time(
        "2026-09-04T02:17:59.999999Z"
    ) == 1788488220

    assert minute_start_for_source_time(
        "2026-09-04T02:18:00Z"
    ) == 1788488280


def test_runtime_raw_journal_flushes_before_transform(
    tmp_path,
):
    path = tmp_path / "raw.jsonl"

    with RuntimeRawJournal(path) as journal:
        journal.append(
            source="coinbase_exchange_ws",
            transport="wss",
            raw_text='{"type":"heartbeat"}',
            received_monotonic_ns=100,
            received_utc="2026-09-04T02:00:00Z",
            request_identity={
                "product_id": COINBASE_PRODUCT,
            },
        )

        # The file must already be visible before close(), proving the
        # Python userspace buffer was flushed before transformation.
        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()

        assert len(lines) == 1
        row = json.loads(lines[0])

        assert (
            row["source"]
            == "coinbase_exchange_ws"
        )
        assert (
            row["raw_text"]
            == '{"type":"heartbeat"}'
        )


def test_runtime_raw_journal_fsync_cadence(
    tmp_path,
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        journal_module.os,
        "fsync",
        lambda fd: calls.append(fd),
    )

    journal = RuntimeRawJournal(
        tmp_path / "raw.jsonl",
        fsync_interval_ns=1_000,
    )

    journal.append(
        source="coinbase_exchange_ws",
        transport="wss",
        raw_text="a",
        received_monotonic_ns=100,
        received_utc="x",
    )

    # First append establishes a durability point.
    assert len(calls) == 1

    journal.append(
        source="coinbase_exchange_ws",
        transport="wss",
        raw_text="b",
        received_monotonic_ns=500,
        received_utc="x",
    )

    # Less than one interval: no additional fsync.
    assert len(calls) == 1

    journal.append(
        source="coinbase_exchange_ws",
        transport="wss",
        raw_text="c",
        received_monotonic_ns=1_100,
        received_utc="x",
    )

    assert len(calls) == 2

    journal.close()

    # Close forces final durability.
    assert len(calls) == 3

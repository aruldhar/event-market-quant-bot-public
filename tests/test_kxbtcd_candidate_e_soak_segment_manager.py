import json
import threading
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournal,
)
from src.kxbtcd_candidate_e_soak_archive import (
    close_raw_segment,
)
from src.kxbtcd_candidate_e_soak_segment_manager import (
    HourlySourceSegmentManager,
    SoakSegmentManagerError,
    SourceBoundJournalAdapter,
)


SOURCE = "kalshi_production_ws"


def append_record(
    manager,
    *,
    utc,
    mono,
    raw="{}",
):
    manager.append(
        transport="wss",
        raw_text=raw,
        received_monotonic_ns=mono,
        received_utc=utc,
        request_identity={
            "channel": "orderbook_delta"
        },
    )


def _capture_error(errors, action):
    try:
        action()
    except Exception as exc:
        errors.append(exc)


def _capture_result(results, errors, action):
    try:
        results.append(action())
    except Exception as exc:
        errors.append(exc)


def make_raw(
    path,
    *,
    source=SOURCE,
    times=("2026-09-04T14:10:00Z",),
):
    with RuntimeRawJournal(path) as journal:
        for i, utc in enumerate(times, 1):
            journal.append(
                source=source,
                transport="wss",
                raw_text=json.dumps(
                    {"sequence": i}
                ),
                received_monotonic_ns=i,
                received_utc=utc,
                request_identity={
                    "channel": "orderbook_delta"
                },
            )


def test_rotates_at_utc_hour_and_archives_prior_segment(
    tmp_path,
):
    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="session-a",
    )

    append_record(
        manager,
        utc="2026-09-04T14:59:59.900Z",
        mono=1,
    )

    first_raw = manager.active_raw_path
    assert first_raw is not None
    assert "20260904T140000Z" in first_raw.name

    append_record(
        manager,
        utc="2026-09-04T15:00:00.100Z",
        mono=2,
    )

    assert not first_raw.exists()
    assert (
        first_raw.with_name(
            first_raw.name + ".zst"
        )
    ).exists()
    assert (
        first_raw.with_name(
            first_raw.name + ".descriptor.json"
        )
    ).exists()

    second_raw = manager.active_raw_path
    assert second_raw is not None
    assert "20260904T150000Z" in second_raw.name

    manager.close()

    assert not second_raw.exists()
    assert len(
        manager.closed_descriptor_paths
    ) == 2


def test_hour_rotation_serializes_concurrent_idle_fsync(
    tmp_path,
    monkeypatch,
):
    """An idle-fsync pass must never observe the old journal after close."""
    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="rotation-lock",
    )
    append_record(
        manager,
        utc="2026-09-04T14:59:59.900Z",
        mono=1,
    )
    active = manager._active
    assert active is not None

    original_close = active.journal.close
    journal_closed = threading.Event()
    allow_rotation = threading.Event()

    def pause_after_close():
        original_close()
        journal_closed.set()
        assert allow_rotation.wait(timeout=1)

    monkeypatch.setattr(active.journal, "close", pause_after_close)
    rotation_errors = []
    fsync_errors = []
    fsync_result = []

    rotation = threading.Thread(
        target=lambda: _capture_error(
            rotation_errors,
            lambda: append_record(
                manager,
                utc="2026-09-04T15:00:00.100Z",
                mono=2,
            ),
        ),
    )
    rotation.start()
    assert journal_closed.wait(timeout=1)

    fsync = threading.Thread(
        target=lambda: _capture_result(
            fsync_result,
            fsync_errors,
            lambda: manager.fsync_if_due(2),
        ),
    )
    fsync.start()
    assert fsync.is_alive()

    allow_rotation.set()
    rotation.join(timeout=1)
    fsync.join(timeout=1)

    assert not rotation.is_alive()
    assert not fsync.is_alive()
    assert rotation_errors == []
    assert fsync_errors == []
    assert fsync_result == [False]
    manager.close()


def test_first_and_last_partial_segment_is_valid(
    tmp_path,
):
    manager = HourlySourceSegmentManager(
        tmp_path,
        source="coinbase_exchange_ws",
        segment_instance_id="session-b",
    )

    append = manager.append

    append(
        transport="wss",
        raw_text="{}",
        received_monotonic_ns=10,
        received_utc="2026-09-04T14:37:00Z",
        request_identity={
            "product_id": "BTC-USD"
        },
    )

    raw = manager.active_raw_path
    manager.close()

    descriptor = json.loads(
        raw.with_name(
            raw.name + ".descriptor.json"
        ).read_text(encoding="utf-8")
    )

    assert (
        descriptor["segment_start_utc"]
        == "2026-09-04T14:00:00Z"
    )
    assert (
        descriptor["segment_end_utc"]
        == "2026-09-04T15:00:00Z"
    )
    assert descriptor["record_count"] == 1


def test_idle_active_segment_is_fsynced_at_one_second_deadline(tmp_path):
    manager = HourlySourceSegmentManager(tmp_path, source=SOURCE,
        segment_instance_id="idle-fsync", fsync_interval_ns=1_000_000_000)
    append_record(manager, utc="2026-09-04T14:37:00Z", mono=100)
    active = manager._active
    assert active is not None
    # A concurrent source worker may capture time immediately before this
    # journal's append/fsync. Defer safely; do not misclassify it as a clock
    # regression or perform an early fsync.
    assert manager.fsync_if_due(99) is False
    assert manager.fsync_if_due(999_999_999) is False
    assert manager.fsync_if_due(1_000_000_100) is True
    assert active.journal._last_fsync_ns == 1_000_000_100
    assert manager.fsync_if_due(1_000_000_101) is False
    manager.close()


def test_same_hour_different_runtime_sessions_do_not_collide(
    tmp_path,
):
    first = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="process-1",
    )
    append_record(
        first,
        utc="2026-09-04T14:10:00Z",
        mono=1,
    )
    first.close()

    second = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="process-2",
    )
    append_record(
        second,
        utc="2026-09-04T14:20:00Z",
        mono=2,
    )
    second.close()

    descriptors = list(
        (tmp_path / SOURCE).glob(
            "*.descriptor.json"
        )
    )

    assert len(descriptors) == 2


def test_utc_hour_regression_fails_closed(tmp_path):
    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="session-a",
    )

    append_record(
        manager,
        utc="2026-09-04T15:01:00Z",
        mono=10,
    )

    with pytest.raises(
        SoakSegmentManagerError,
        match="UTC segment hour regressed",
    ):
        append_record(
            manager,
            utc="2026-09-04T14:59:00Z",
            mono=11,
        )

    manager.close()


def test_cross_segment_monotonic_regression_fails_closed(
    tmp_path,
):
    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="session-a",
    )

    append_record(
        manager,
        utc="2026-09-04T14:59:00Z",
        mono=10,
    )

    with pytest.raises(
        SoakSegmentManagerError,
        match="monotonic receive time regressed",
    ):
        append_record(
            manager,
            utc="2026-09-04T15:00:00Z",
            mono=9,
        )

    manager.close()


def test_recovery_discards_orphan_temp_and_recompresses_raw(
    tmp_path,
):
    source_dir = tmp_path / SOURCE
    source_dir.mkdir(parents=True)

    raw = (
        source_dir
        / "20260904T140000Z__old-process.jsonl"
    )
    make_raw(raw)

    temp = raw.with_name(
        raw.name + ".zst.tmp"
    )
    temp.write_bytes(b"orphan")

    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="new-process",
    )

    summary = manager.recover_existing_segments()

    assert summary.archived_raw_segments == 1
    assert len(manager.closed_descriptor_paths) == 1
    assert manager.closed_descriptor_paths[0].exists()
    assert (
        summary.discarded_temporary_compressed
        == 1
    )
    assert not raw.exists()
    assert not temp.exists()
    assert (
        raw.with_name(
            raw.name + ".descriptor.json"
        )
    ).exists()


def test_recovery_discards_unverified_final_compressed_when_raw_intact(
    tmp_path,
):
    source_dir = tmp_path / SOURCE
    source_dir.mkdir(parents=True)

    raw = (
        source_dir
        / "20260904T140000Z__old-process.jsonl"
    )
    make_raw(raw)

    compressed = raw.with_name(
        raw.name + ".zst"
    )
    compressed.write_bytes(b"not-authoritative")

    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="new-process",
    )

    summary = manager.recover_existing_segments()

    assert (
        summary.discarded_unverified_compressed
        == 1
    )
    assert summary.archived_raw_segments == 1
    assert not raw.exists()


def test_recovery_reverifies_descriptor_before_deleting_redundant_raw(
    tmp_path,
):
    source_dir = tmp_path / SOURCE
    source_dir.mkdir(parents=True)

    raw = (
        source_dir
        / "20260904T140000Z__old-process.jsonl"
    )
    make_raw(raw)

    original = raw.read_bytes()

    close_raw_segment(
        raw_path=raw,
        source=SOURCE,
        segment_start_utc="2026-09-04T14:00:00Z",
        segment_end_utc="2026-09-04T15:00:00Z",
        record_count=1,
    )

    # Simulate crash/restart state where a redundant raw copy
    # still exists beside an already-verified closed segment.
    raw.write_bytes(original)

    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="new-process",
    )

    summary = manager.recover_existing_segments()

    assert summary.verified_closed_segments == 1
    assert len(manager.closed_descriptor_paths) == 1
    assert summary.deleted_redundant_raw == 1
    assert not raw.exists()


def test_missing_raw_without_verified_descriptor_is_hard_failure(
    tmp_path,
):
    source_dir = tmp_path / SOURCE
    source_dir.mkdir(parents=True)

    raw = (
        source_dir
        / "20260904T140000Z__old-process.jsonl"
    )

    raw.with_name(
        raw.name + ".zst"
    ).write_bytes(b"orphan")

    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="new-process",
    )

    with pytest.raises(
        SoakSegmentManagerError,
        match="uncompressed segment missing without",
    ):
        manager.recover_existing_segments()


def test_descriptor_hash_mismatch_is_hard_failure(
    tmp_path,
):
    source_dir = tmp_path / SOURCE
    source_dir.mkdir(parents=True)

    raw = (
        source_dir
        / "20260904T140000Z__old-process.jsonl"
    )
    make_raw(raw)

    close_raw_segment(
        raw_path=raw,
        source=SOURCE,
        segment_start_utc="2026-09-04T14:00:00Z",
        segment_end_utc="2026-09-04T15:00:00Z",
        record_count=1,
    )

    compressed = raw.with_name(
        raw.name + ".zst"
    )
    data = bytearray(compressed.read_bytes())
    data[-1] ^= 1
    compressed.write_bytes(data)

    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="new-process",
    )

    with pytest.raises(
        SoakSegmentManagerError,
        match="descriptor/hash validation failed",
    ):
        manager.recover_existing_segments()


def test_incomplete_raw_record_is_not_silently_repaired(
    tmp_path,
):
    source_dir = tmp_path / SOURCE
    source_dir.mkdir(parents=True)

    raw = (
        source_dir
        / "20260904T140000Z__old-process.jsonl"
    )
    raw.write_bytes(b'{"incomplete":')

    manager = HourlySourceSegmentManager(
        tmp_path,
        source=SOURCE,
        segment_instance_id="new-process",
    )

    with pytest.raises(
        SoakSegmentManagerError,
        match="incomplete trailing record",
    ):
        manager.recover_existing_segments()



def test_source_bound_adapter_accepts_matching_source(
    tmp_path,
):
    manager = HourlySourceSegmentManager(
        tmp_path,
        source="coinbase_exchange_rest",
        segment_instance_id="adapter-a",
    )

    adapter = SourceBoundJournalAdapter(
        manager
    )

    adapter.append(
        source="coinbase_exchange_rest",
        transport="https_rest",
        raw_text='[{"trade_id":12}]',
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:10:00Z",
        request_identity={
            "method": "GET",
            "url": (
                "https://api.exchange.coinbase.com/"
                "products/BTC-USD/trades"
            ),
        },
    )

    raw = manager.active_raw_path
    assert raw is not None
    assert raw.exists()

    manager.close()

    descriptor = json.loads(
        raw.with_name(
            raw.name + ".descriptor.json"
        ).read_text(encoding="utf-8")
    )

    assert descriptor["source"] == (
        "coinbase_exchange_rest"
    )
    assert descriptor["record_count"] == 1


def test_source_bound_adapter_rejects_cross_source_write(
    tmp_path,
):
    manager = HourlySourceSegmentManager(
        tmp_path,
        source="coinbase_exchange_rest",
        segment_instance_id="adapter-b",
    )

    adapter = SourceBoundJournalAdapter(
        manager
    )

    with pytest.raises(
        SoakSegmentManagerError,
        match="source does not match",
    ):
        adapter.append(
            source="kalshi_production_rest",
            transport="https_rest",
            raw_text="{}",
            received_monotonic_ns=1,
            received_utc="2026-09-04T15:10:00Z",
            request_identity={
                "method": "GET",
            },
        )

    assert manager.active_raw_path is None

    manager.close()


def test_coinbase_recovery_paginator_can_use_hourly_adapter(
    tmp_path,
    monkeypatch,
):
    import src.kxbtcd_candidate_e_coinbase_rest_trade_paginator as paginator

    class FakeResponse:
        status_code = 200

        headers = {}

        text = json.dumps(
            [
                {"trade_id": 12},
                {"trade_id": 10},
            ]
        )

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def get(
            self,
            url,
            *,
            params,
            timeout,
        ):
            self.calls += 1
            return FakeResponse()

    monkeypatch.setattr(
        paginator,
        "_utc_now_text",
        lambda: "2026-09-04T15:20:00Z",
    )

    manager = HourlySourceSegmentManager(
        tmp_path,
        source="coinbase_exchange_rest",
        segment_instance_id="adapter-c",
    )

    adapter = SourceBoundJournalAdapter(
        manager
    )

    session = FakeSession()

    result = paginator.fetch_recovery_pages(
        session=session,
        journal=adapter,
        start_exclusive_trade_id=10,
        target_inclusive_trade_id=12,
        max_pages=2,
        max_latest_attempts=1,
        latest_retry_sleep_seconds=0,
    )

    assert session.calls == 1
    assert result.evidence.coverage_proven
    assert (
        result.evidence.start_exclusive_trade_id
        == 10
    )
    assert (
        result.evidence.target_inclusive_trade_id
        == 12
    )

    raw = manager.active_raw_path
    assert raw is not None

    # One raw journal record represents the exact HTTP response,
    # independently of how many trade rows that response contained.
    manager.close()

    descriptor = json.loads(
        raw.with_name(
            raw.name + ".descriptor.json"
        ).read_text(encoding="utf-8")
    )

    assert descriptor["record_count"] == 1
    assert descriptor["source"] == (
        "coinbase_exchange_rest"
    )

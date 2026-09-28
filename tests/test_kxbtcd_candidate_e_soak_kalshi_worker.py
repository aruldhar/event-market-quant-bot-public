from datetime import datetime
import json

from src.kxbtcd_candidate_e_soak_kalshi_worker import (
    KalshiReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    SoakSourceRuntimeCore,
)


def epoch_ms(text):
    return int(
        datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).timestamp()
        * 1000
    )


NOW_MS = epoch_ms(
    "2026-09-04T15:30:00Z"
)


def market(
    *,
    event,
    ticker,
    close_time,
):
    return {
        "ticker": ticker,
        "event_ticker": event,
        "status": "active",
        "close_time": close_time,
    }


def discovery_payload():
    return {
        "markets": [
            market(
                event="KXBTCD-26SEP0416",
                ticker=(
                    "KXBTCD-26SEP0416-T110000.00"
                ),
                close_time=(
                    "2026-09-04T16:00:00Z"
                ),
            ),
            market(
                event="KXBTCD-26SEP0416",
                ticker=(
                    "KXBTCD-26SEP0416-T111000.00"
                ),
                close_time=(
                    "2026-09-04T16:00:00Z"
                ),
            ),
            market(
                event="KXBTCD-26SEP0417",
                ticker=(
                    "KXBTCD-26SEP0417-T110000.00"
                ),
                close_time=(
                    "2026-09-04T17:00:00Z"
                ),
            ),
        ]
    }


def make_worker(tmp_path):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
    )

    core.discover_current_event_from_raw(
        raw_text=json.dumps(
            discovery_payload()
        ),
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=NOW_MS,
        request_identity={
            "method": "GET",
            "params": {
                "series_ticker": "KXBTCD",
                "status": "open",
            },
        },
    )

    worker = KalshiReadOnlyWorkerSession(
        core
    )

    binding = worker.start_generation(
        opened_monotonic_ns=100
    )

    return core, worker, binding


def subscribed():
    return json.dumps(
        {
            "type": "subscribed",
            "msg": {
                "channel": "orderbook_delta",
                "sid": 1,
            },
        }
    )


def snapshot(
    ticker,
    seq,
):
    return json.dumps(
        {
            "type": "orderbook_snapshot",
            "seq": seq,
            "msg": {
                "market_ticker": ticker,
            },
        }
    )


def test_fresh_generation_subscribes_exact_current_event_ladder(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    assert set(
        binding.cache.subscribed_tickers
    ) == {
        "KXBTCD-26SEP0416-T110000.00",
        "KXBTCD-26SEP0416-T111000.00",
    }

    action = worker.evaluate(
        now_timestamp_ms=NOW_MS,
        now_monotonic_ns=101,
    )

    assert action.kind == "BLOCKED"
    assert action.event_ticker == (
        "KXBTCD-26SEP0416"
    )

    core.close()


def test_full_ladder_snapshots_plus_current_pong_reach_ready(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    first, second = (
        binding.cache.subscribed_tickers
    )

    worker.ingest_ws_frame(
        raw_text=subscribed(),
        received_monotonic_ns=110,
        received_utc="2026-09-04T15:30:01Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.ingest_ws_frame(
        raw_text=snapshot(
            first,
            1,
        ),
        received_monotonic_ns=120,
        received_utc="2026-09-04T15:30:02Z",
        now_timestamp_ms=NOW_MS,
    )

    before = worker.ingest_ws_frame(
        raw_text=snapshot(
            second,
            2,
        ),
        received_monotonic_ns=130,
        received_utc="2026-09-04T15:30:03Z",
        now_timestamp_ms=NOW_MS,
    )

    # Books are complete but transport liveness still lacks a current Pong.
    assert before.kind == "BLOCKED"

    ready = worker.record_pong(
        pong_monotonic_ns=140,
        now_timestamp_ms=NOW_MS,
    )

    assert ready.kind == "READY"
    assert ready.reason == "PASS"

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 0
    )

    core.close()


def test_sequence_gap_invalidates_entire_ladder_and_requires_reconnect(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    first, second = (
        binding.cache.subscribed_tickers
    )

    worker.ingest_ws_frame(
        raw_text=subscribed(),
        received_monotonic_ns=110,
        received_utc="2026-09-04T15:30:01Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.ingest_ws_frame(
        raw_text=snapshot(first, 1),
        received_monotonic_ns=120,
        received_utc="2026-09-04T15:30:02Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.ingest_ws_frame(
        raw_text=snapshot(second, 2),
        received_monotonic_ns=130,
        received_utc="2026-09-04T15:30:03Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.record_pong(
        pong_monotonic_ns=140,
        now_timestamp_ms=NOW_MS,
    )

    action = worker.ingest_ws_frame(
        raw_text=json.dumps(
            {
                "type": "orderbook_delta",
                "seq": 4,
                "msg": {
                    "market_ticker": first,
                    "side": "yes",
                    "price_dollars": "0.50",
                    "delta_fp": "1",
                },
            }
        ),
        received_monotonic_ns=150,
        received_utc="2026-09-04T15:30:04Z",
        now_timestamp_ms=NOW_MS,
    )

    assert action.kind == (
        "RECONNECT_REQUIRED"
    )
    assert action.reason == (
        "KALSHI_SEQUENCE_GAP"
    )
    assert action.sequence_gap_count == 1

    assert binding.cache.resync_required
    assert not binding.cache.all_ready()

    assert all(
        not book.valid
        for book in binding.cache.books.values()
    )

    core.close()


def test_initial_resync_state_does_not_trigger_reconnect(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    assert binding.cache.resync_required
    assert (
        binding.cache.sequence_gap_count
        == 0
    )

    action = worker.evaluate(
        now_timestamp_ms=NOW_MS,
        now_monotonic_ns=101,
    )

    assert action.kind == "BLOCKED"

    core.close()


def test_stale_pong_requires_fresh_connection_generation(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    first, second = (
        binding.cache.subscribed_tickers
    )

    worker.ingest_ws_frame(
        raw_text=subscribed(),
        received_monotonic_ns=110,
        received_utc="2026-09-04T15:30:01Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.ingest_ws_frame(
        raw_text=snapshot(first, 1),
        received_monotonic_ns=120,
        received_utc="2026-09-04T15:30:02Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.ingest_ws_frame(
        raw_text=snapshot(second, 2),
        received_monotonic_ns=130,
        received_utc="2026-09-04T15:30:03Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.record_pong(
        pong_monotonic_ns=140,
        now_timestamp_ms=NOW_MS,
    )

    # Frozen maximum Pong proof age = 20 seconds.
    stale = worker.evaluate(
        now_timestamp_ms=NOW_MS,
        now_monotonic_ns=(
            140
            + 20_000_000_001
        ),
    )

    assert stale.kind == (
        "RECONNECT_REQUIRED"
    )
    assert stale.reason == (
        "KALSHI_PONG_STALE"
    )

    core.close()


def test_event_expiry_requires_rollover_not_generic_reconnect(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    expired = worker.evaluate(
        now_timestamp_ms=epoch_ms(
            "2026-09-04T16:00:00Z"
        ),
        now_monotonic_ns=200,
    )

    assert expired.kind == (
        "ROLLOVER_REQUIRED"
    )
    assert expired.reason == (
        "SELECTED_EVENT_CLOSED"
    )

    core.close()


def test_failure_disconnect_arms_frozen_backoff(
    tmp_path,
):
    core, worker, binding = make_worker(
        tmp_path
    )

    decision = worker.disconnect(
        closed_monotonic_ns=200,
        count_as_failure=True,
    )

    assert decision.delay_seconds == 1

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 1
    )

    assert not (
        core.connections
        .current_kalshi
        .connected
    )

    core.close()


def test_fresh_reconnect_uses_new_empty_cache_generation(
    tmp_path,
):
    core, worker, first_binding = make_worker(
        tmp_path
    )

    first_generation = (
        first_binding.generation
    )

    first_ticker = (
        first_binding
        .cache
        .subscribed_tickers[0]
    )

    worker.ingest_ws_frame(
        raw_text=subscribed(),
        received_monotonic_ns=110,
        received_utc="2026-09-04T15:30:01Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.ingest_ws_frame(
        raw_text=snapshot(
            first_ticker,
            1,
        ),
        received_monotonic_ns=120,
        received_utc="2026-09-04T15:30:02Z",
        now_timestamp_ms=NOW_MS,
    )

    worker.disconnect(
        closed_monotonic_ns=200,
        count_as_failure=True,
    )

    second_binding = (
        worker.start_generation(
            opened_monotonic_ns=300
        )
    )

    assert (
        second_binding.generation
        == first_generation + 1
    )

    assert second_binding.cache.books == {}
    assert second_binding.cache.resync_required
    assert (
        second_binding.cache.sequence_gap_count
        == 0
    )

    core.close()

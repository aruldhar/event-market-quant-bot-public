from datetime import datetime, timezone
import json

import pytest

from src.kxbtcd_candidate_e_soak_runtime_core import (
    COINBASE_WS_SOURCE,
    KALSHI_REST_SOURCE,
    KALSHI_WS_SOURCE,
    SoakRuntimeCoreError,
    SoakSourceRuntimeCore,
)


def epoch_ms(text):
    dt = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    return int(dt.timestamp() * 1000)


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


def new_core(tmp_path):
    return SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
    )


def test_ws_latency_uses_real_post_persistence_timestamps(tmp_path):
    samples = []
    ticks = iter((11, 13, 17, 19))
    observer = type(
        "Observer",
        (),
        {
            "record_latency": lambda self, name, *, started_ns, ended_ns:
            samples.append((name, started_ns, ended_ns)),
            "record_source_event": lambda self, **kwargs: None,
        },
    )()
    core = SoakSourceRuntimeCore(
        runtime_session_id="timed-runtime",
        archive_root=tmp_path,
        observability=observer,
        monotonic_ns=lambda: next(ticks),
    )
    core.open_coinbase_generation(opened_monotonic_ns=1)

    core.ingest_coinbase_ws_frame(
        raw_text=json.dumps({
            "type": "heartbeat",
            "product_id": "BTC-USD",
            "last_trade_id": 1,
            "sequence": 1,
            "time": "2026-09-04T15:10:00Z",
        }),
        received_monotonic_ns=7,
        received_utc="2026-09-04T15:10:00Z",
    )

    assert samples == [
        ("receive_to_raw_persist_duration", 7, 11),
        ("raw_persist_to_parse_apply_duration", 11, 13),
    ]
    core.close()


def test_invalid_coinbase_json_is_persisted_before_parse_failure(
    tmp_path,
):
    core = new_core(tmp_path)

    core.open_coinbase_generation(
        opened_monotonic_ns=1
    )

    with pytest.raises(
        SoakRuntimeCoreError,
        match="invalid JSON",
    ):
        core.ingest_coinbase_ws_frame(
            raw_text="{",
            received_monotonic_ns=2,
            received_utc="2026-09-04T15:10:00Z",
        )

    raw = core.manager(
        COINBASE_WS_SOURCE
    ).active_raw_path

    assert raw is not None
    assert raw.exists()

    wrapper = json.loads(
        raw.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )

    assert wrapper["raw_text"] == "{"

    core.close()


def test_coinbase_transform_occurs_only_after_raw_write(
    tmp_path,
):
    core = new_core(tmp_path)

    binding = core.open_coinbase_generation(
        opened_monotonic_ns=1
    )

    original = binding.builder.apply_ws

    raw_text = json.dumps(
        {
            "type": "last_match",
            "product_id": "BTC-USD",
            "trade_id": 100,
            "sequence": 200,
            "time": "2026-09-04T15:10:00Z",
            "price": "110000.00",
            "size": "0.01",
            "side": "buy",
        }
    )

    def checked_apply(
        payload,
        *,
        received_monotonic_ns,
    ):
        path = core.manager(
            COINBASE_WS_SOURCE
        ).active_raw_path

        assert path is not None
        text = path.read_text(
            encoding="utf-8"
        )

        wrapper = json.loads(
            text.splitlines()[0]
        )

        assert wrapper["raw_text"] == raw_text

        return original(
            payload,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
        )

    binding.builder.apply_ws = checked_apply

    result = core.ingest_coinbase_ws_frame(
        raw_text=raw_text,
        received_monotonic_ns=2,
        received_utc="2026-09-04T15:10:00Z",
    )

    assert result["type"] == "last_match"
    assert binding.builder.seeded

    core.close()


def test_discovery_selects_earliest_future_event_and_full_ladder(
    tmp_path,
):
    core = new_core(tmp_path)

    raw = json.dumps(
        discovery_payload()
    )

    result = core.discover_current_event_from_raw(
        raw_text=raw,
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=epoch_ms(
            "2026-09-04T15:30:00Z"
        ),
        request_identity={
            "method": "GET",
            "params": {
                "series_ticker": "KXBTCD",
            },
        },
    )

    assert (
        result.current_event.event_ticker
        == "KXBTCD-26SEP0416"
    )

    binding = core.open_kalshi_generation(
        opened_monotonic_ns=2
    )

    assert set(
        binding.cache.subscribed_tickers
    ) == {
        "KXBTCD-26SEP0416-T110000.00",
        "KXBTCD-26SEP0416-T111000.00",
    }

    core.close()


def test_event_rollover_moves_to_next_strategy_independent_event(
    tmp_path,
):
    core = new_core(tmp_path)

    raw = json.dumps(
        discovery_payload()
    )

    first = core.discover_current_event_from_raw(
        raw_text=raw,
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=epoch_ms(
            "2026-09-04T15:30:00Z"
        ),
    )

    assert (
        first.current_event.event_ticker
        == "KXBTCD-26SEP0416"
    )

    second = core.discover_current_event_from_raw(
        raw_text=raw,
        received_monotonic_ns=2,
        received_utc="2026-09-04T16:00:01Z",
        now_timestamp_ms=epoch_ms(
            "2026-09-04T16:00:01Z"
        ),
    )

    assert second.rollover_required
    assert (
        second.reason
        == "SELECTED_EVENT_CLOSED"
    )
    assert (
        second.current_event.event_ticker
        == "KXBTCD-26SEP0417"
    )

    core.close()


def test_invalid_kalshi_ws_json_is_persisted_before_parse_failure(
    tmp_path,
):
    core = new_core(tmp_path)

    core.discover_current_event_from_raw(
        raw_text=json.dumps(
            discovery_payload()
        ),
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=epoch_ms(
            "2026-09-04T15:30:00Z"
        ),
    )

    core.open_kalshi_generation(
        opened_monotonic_ns=2
    )

    with pytest.raises(
        SoakRuntimeCoreError,
        match="invalid JSON",
    ):
        core.ingest_kalshi_ws_frame(
            raw_text="{",
            received_monotonic_ns=3,
            received_utc="2026-09-04T15:30:01Z",
        )

    raw = core.manager(
        KALSHI_WS_SOURCE
    ).active_raw_path

    assert raw is not None
    wrapper = json.loads(
        raw.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )
    assert wrapper["raw_text"] == "{"

    core.close()


def test_kalshi_sequence_gap_invalidates_full_ladder(
    tmp_path,
):
    core = new_core(tmp_path)

    core.discover_current_event_from_raw(
        raw_text=json.dumps(
            {
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
                ]
            }
        ),
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=epoch_ms(
            "2026-09-04T15:30:00Z"
        ),
    )

    binding = core.open_kalshi_generation(
        opened_monotonic_ns=2
    )

    core.ingest_kalshi_ws_frame(
        raw_text=json.dumps(
            {
                "type": "subscribed",
                "msg": {
                    "channel": "orderbook_delta",
                    "sid": 1,
                },
            }
        ),
        received_monotonic_ns=3,
        received_utc="2026-09-04T15:30:01Z",
    )

    snapshot = core.ingest_kalshi_ws_frame(
        raw_text=json.dumps(
            {
                "type": "orderbook_snapshot",
                "seq": 1,
                "msg": {
                    "market_ticker": (
                        "KXBTCD-26SEP0416-T110000.00"
                    ),
                },
            }
        ),
        received_monotonic_ns=4,
        received_utc="2026-09-04T15:30:02Z",
    )

    assert snapshot["ready"]
    assert binding.cache.all_ready()

    gap = core.ingest_kalshi_ws_frame(
        raw_text=json.dumps(
            {
                "type": "orderbook_delta",
                "seq": 3,
                "msg": {
                    "market_ticker": (
                        "KXBTCD-26SEP0416-T110000.00"
                    ),
                    "side": "yes",
                    "price_dollars": "0.50",
                    "delta_fp": "1",
                },
            }
        ),
        received_monotonic_ns=5,
        received_utc="2026-09-04T15:30:03Z",
    )

    assert gap["gap"]
    assert not binding.cache.all_ready()
    assert binding.cache.resync_required

    core.close()


def test_core_reconnect_policy_resets_only_after_ready(
    tmp_path,
):
    core = new_core(tmp_path)

    first = core.record_source_failure(
        "coinbase",
        observed_monotonic_ns=(
            1_000_000_000
        ),
    )

    second = core.record_source_failure(
        "coinbase",
        observed_monotonic_ns=(
            2_000_000_000
        ),
    )

    assert first.delay_seconds == 1
    assert second.delay_seconds == 2

    core.mark_source_ready(
        "coinbase"
    )

    again = core.record_source_failure(
        "coinbase",
        observed_monotonic_ns=(
            10_000_000_000
        ),
    )

    assert again.delay_seconds == 1

    core.close()


def test_kalshi_rest_discovery_is_source_specific(
    tmp_path,
):
    core = new_core(tmp_path)

    core.discover_current_event_from_raw(
        raw_text=json.dumps(
            discovery_payload()
        ),
        received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=epoch_ms(
            "2026-09-04T15:30:00Z"
        ),
    )

    path = core.manager(
        KALSHI_REST_SOURCE
    ).active_raw_path

    assert path is not None
    assert path.parent.name == (
        "kalshi_production_rest"
    )

    core.close()



def test_exact_rest_candle_can_seed_current_generation_readiness(
    tmp_path,
):
    core = new_core(tmp_path)

    binding = core.open_coinbase_generation(
        opened_monotonic_ns=1_000_000_000
    )

    # New connection starts AFTER the required completed minute.
    core.ingest_coinbase_ws_frame(
        raw_text=json.dumps(
            {
                "type": "last_match",
                "product_id": "BTC-USD",
                "trade_id": 100,
                "sequence": 200,
                "time": "2026-09-04T15:10:05Z",
                "price": "110200",
                "size": "0.01",
                "side": "buy",
            }
        ),
        received_monotonic_ns=(
            2_000_000_000
        ),
        received_utc="2026-09-04T15:10:05Z",
    )

    core.ingest_coinbase_ws_frame(
        raw_text=json.dumps(
            {
                "type": "heartbeat",
                "product_id": "BTC-USD",
                "last_trade_id": 100,
                "sequence": 201,
                "time": "2026-09-04T15:10:06Z",
            }
        ),
        received_monotonic_ns=(
            3_000_000_000
        ),
        received_utc="2026-09-04T15:10:06Z",
    )

    decision_s = int(
        datetime.fromisoformat(
            "2026-09-04T15:10:30+00:00"
        ).timestamp()
    )

    before = core.evaluate_coinbase(
        decision_epoch_s=decision_s,
        now_monotonic_ns=(
            3_500_000_000
        ),
    )

    assert before.status.value == "BLOCKED"
    assert (
        before.builder_status
        == "NO_TRADES_IN_MINUTE"
    )

    target_start = (
        (decision_s // 60) * 60
    ) - 60

    core.ingest_coinbase_rest_seed_candle(
        raw_text=json.dumps(
            [
                [
                    target_start,
                    109900,
                    110150,
                    110000,
                    110123.45,
                    12.5,
                ]
            ]
        ),
        received_monotonic_ns=(
            3_600_000_000
        ),
        received_utc="2026-09-04T15:10:07Z",
        decision_epoch_s=decision_s,
        request_identity={
            "method": "GET",
            "params": {
                "granularity": 60,
            },
        },
    )

    after = core.evaluate_coinbase(
        decision_epoch_s=decision_s,
        now_monotonic_ns=(
            3_700_000_000
        ),
    )

    assert after.status.value == "PASS"
    assert (
        after.builder_status
        == "REST_CANDLE_SEED"
    )
    assert after.close_trade_id is None
    assert (
        binding.generation
        == after.connection_generation
    )

    core.close()


def test_rest_seed_raw_is_persisted_before_invalid_json_failure(
    tmp_path,
):
    core = new_core(tmp_path)

    core.open_coinbase_generation(
        opened_monotonic_ns=1
    )

    with pytest.raises(
        SoakRuntimeCoreError,
        match="invalid JSON",
    ):
        core.ingest_coinbase_rest_seed_candle(
            raw_text="{",
            received_monotonic_ns=2,
            received_utc="2026-09-04T15:10:00Z",
            decision_epoch_s=1_725_550_000,
        )

    raw = core.manager(
        "coinbase_exchange_rest"
    ).active_raw_path

    assert raw is not None
    wrapper = json.loads(
        raw.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )

    assert wrapper["raw_text"] == "{"

    core.close()


def test_v2_rest_candle_is_independent_of_coinbase_websocket_generation(
    tmp_path,
):
    core = new_core(tmp_path)
    decision_s = int(datetime.fromisoformat("2026-09-04T15:10:30+00:00").timestamp())
    target_start = (decision_s // 60) * 60 - 60

    # No Coinbase WebSocket generation is opened for frozen V2's candle input.
    core.ingest_v2_coinbase_rest_candle(
        raw_text=json.dumps([[target_start, 1, 2, 1, 1.5, 3]]),
        received_monotonic_ns=5,
        received_utc="2026-09-04T15:10:07Z",
        target_minute_start_s=target_start,
        request_identity={"method": "GET", "params": {"granularity": 60}},
    )

    evidence = core.evaluate_v2_coinbase_rest_candle(
        decision_epoch_s=decision_s,
        now_monotonic_ns=5,
    )
    assert evidence.status.value == "PASS"
    assert core.connections.current_coinbase is None

    raw = core.manager("coinbase_exchange_rest").active_raw_path
    assert raw is not None
    assert json.loads(raw.read_text(encoding="utf-8").splitlines()[0])["raw_text"]
    core.close()


def test_v2_rest_candle_is_raw_persisted_before_invalid_payload_failure(
    tmp_path,
):
    core = new_core(tmp_path)
    with pytest.raises(SoakRuntimeCoreError, match="V2 Coinbase REST payload"):
        core.ingest_v2_coinbase_rest_candle(
            raw_text="{",
            received_monotonic_ns=5,
            received_utc="2026-09-04T15:10:07Z",
            target_minute_start_s=1_725_501_000,
        )
    raw = core.manager("coinbase_exchange_rest").active_raw_path
    assert raw is not None
    assert json.loads(raw.read_text(encoding="utf-8").splitlines()[0])["raw_text"] == "{"
    core.close()

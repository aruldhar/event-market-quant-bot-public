from datetime import datetime
import json
import threading

import pytest

from src.kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_coinbase_ws_generation_transport import (
    COINBASE_WS_URL,
    CoinbaseCandleSeedRetryPolicy,
    CoinbaseWsGenerationTransportError,
    run_one_coinbase_generation,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    COINBASE_WS_SOURCE,
    SoakSourceRuntimeCore,
)
from src.kxbtcd_candidate_e_soak_metric_producers import RuntimeMetricProducers


DECISION_S = int(
    datetime.fromisoformat(
        "2026-09-04T15:10:30+00:00"
    ).timestamp()
)


class FakeResponse:
    status_code = 200

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeHttpSession:
    def __init__(self, candle_text):
        self.candle_text = candle_text
        self.calls = []

    def get(
        self,
        url,
        *,
        params,
        timeout,
    ):
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "timeout": timeout,
            }
        )

        return FakeResponse(
            self.candle_text
        )


class FakeWebSocket:
    def __init__(
        self,
        *,
        frames,
        stop_event,
    ):
        self.frames = list(frames)
        self.stop_event = stop_event
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    def send(self, text):
        self.sent.append(
            json.loads(text)
        )

    def recv(self, *, timeout):
        if not self.frames:
            raise TimeoutError

        value = self.frames.pop(0)

        if not self.frames:
            self.stop_event.set()

        return value


class FakeConnectFactory:
    def __init__(
        self,
        websocket,
    ):
        self.websocket = websocket
        self.calls = []

    def __call__(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            {
                "url": url,
                **kwargs,
            }
        )

        return self.websocket


def make_core_worker(tmp_path, metric_producers=None):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
        metric_producers=metric_producers,
    )

    worker = CoinbaseReadOnlyWorkerSession(
        core
    )

    return core, worker


def test_unpublished_candle_retry_is_rate_limited_and_bounded():
    policy = CoinbaseCandleSeedRetryPolicy()
    action = type("Action", (), {"kind": "REST_CANDLE_SEED_REQUIRED", "target_minute_start_s": 60,
        "target_minute_end_s": 120})()
    assert policy.allow(action, now_monotonic_ns=0)
    assert not policy.allow(action, now_monotonic_ns=500_000_000)
    for now in range(1, 5):
        assert policy.allow(action, now_monotonic_ns=now * 1_000_000_000)
    assert not policy.allow(action, now_monotonic_ns=5_000_000_000)
    next_minute = type("Action", (), {"kind": "REST_CANDLE_SEED_REQUIRED", "target_minute_start_s": 120,
        "target_minute_end_s": 180})()
    assert policy.allow(next_minute, now_monotonic_ns=5_000_000_000)


def test_generation_subscribes_matches_and_heartbeat_and_reaches_ready(
    tmp_path,
):
    metrics = RuntimeMetricProducers(archive_root=tmp_path, clock_evidence_path=tmp_path / "clock")
    core, worker = make_core_worker(tmp_path, metrics)

    stop = threading.Event()

    frames = [
        json.dumps(
            {
                "type": "subscriptions",
                "channels": [],
            }
        ),
        json.dumps(
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
        json.dumps(
            {
                "type": "heartbeat",
                "product_id": "BTC-USD",
                "last_trade_id": 100,
                "sequence": 201,
                "time": "2026-09-04T15:10:06Z",
            }
        ),
    ]

    ws = FakeWebSocket(
        frames=frames,
        stop_event=stop,
    )

    connect = FakeConnectFactory(
        ws
    )

    target_start = (
        (DECISION_S // 60) * 60
    ) - 60

    http = FakeHttpSession(
        json.dumps(
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
        )
    )

    times = iter(
        [
            1_000_000_000,
            2_000_000_000,
            3_000_000_000,
            4_000_000_000,
            5_000_000_000,
            6_000_000_000,
            7_000_000_000,
        ]
    )

    result = run_one_coinbase_generation(
        worker=worker,
        stop_event=stop,
        decision_epoch_s=(
            lambda: DECISION_S
        ),
        http_session=http,
        connect_fn=connect,
        monotonic_ns=lambda: next(
            times
        ),
        utc_now_text=lambda: (
            "2026-09-04T15:10:07Z"
        ),
    )

    assert result.received_frame_count == 3
    assert result.final_action_kind == "READY"
    assert result.intentional_stop
    assert result.reconnect_decision is None
    assert metrics.counters["coinbase_message_count"] == 3
    assert metrics.counters["coinbase_heartbeat_count"] == 1
    assert metrics.generations["coinbase"] == 1

    assert len(connect.calls) == 1
    call = connect.calls[0]

    assert call["url"] == COINBASE_WS_URL
    assert call["ping_interval"] is None
    assert call["ping_timeout"] is None

    assert len(ws.sent) == 1

    command = ws.sent[0]

    assert command["type"] == "subscribe"

    channels = set(
        command["channels"]
    )

    assert channels == {
        "matches",
        "heartbeat",
    }

    assert len(http.calls) == 1

    assert not (
        core.connections
        .current_coinbase
        .connected
    )

    core.close()


def test_ws_frame_is_raw_persisted(
    tmp_path,
):
    core, worker = make_core_worker(
        tmp_path
    )

    stop = threading.Event()

    frame = json.dumps(
        {
            "type": "subscriptions",
            "channels": [],
        }
    )

    ws = FakeWebSocket(
        frames=[frame],
        stop_event=stop,
    )

    connect = FakeConnectFactory(
        ws
    )

    times = iter(
        [
            1_000,
            2_000,
            3_000,
        ]
    )

    run_one_coinbase_generation(
        worker=worker,
        stop_event=stop,
        decision_epoch_s=(
            lambda: DECISION_S
        ),
        connect_fn=connect,
        monotonic_ns=lambda: next(
            times
        ),
        utc_now_text=lambda: (
            "2026-09-04T15:10:00Z"
        ),
    )

    # A connection-generation close must NOT close the UTC-hour
    # archive segment.  The raw payload should already be durable in
    # the active JSONL segment.
    raw = core.manager(
        COINBASE_WS_SOURCE
    ).active_raw_path

    assert raw is not None
    assert raw.exists()

    record = json.loads(
        raw.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )

    assert record["raw_text"] == frame

    # Runtime/archive shutdown closes the partial UTC-hour segment and
    # creates its verified compressed artifact + descriptor.
    core.close()

    descriptor = raw.with_name(
        raw.name + ".descriptor.json"
    )

    assert descriptor.exists()

    value = json.loads(
        descriptor.read_text(
            encoding="utf-8"
        )
    )

    assert value["record_count"] == 1


def test_binary_frame_fails_and_schedules_reconnect_backoff(
    tmp_path,
):
    core, worker = make_core_worker(
        tmp_path
    )

    events = []
    core.observability = type("Observer", (), {
        "record_source_event": lambda self, **kwargs: events.append(kwargs),
    })()
    stop = threading.Event()

    ws = FakeWebSocket(
        frames=[b"binary"],
        stop_event=stop,
    )

    connect = FakeConnectFactory(
        ws
    )

    times = iter(
        [
            1_000_000_000,
            2_000_000_000,
            3_000_000_000,
        ]
    )

    with pytest.raises(
        CoinbaseWsGenerationTransportError,
        match="binary",
    ):
        run_one_coinbase_generation(
            worker=worker,
            stop_event=stop,
            decision_epoch_s=(
                lambda: DECISION_S
            ),
            connect_fn=connect,
            monotonic_ns=lambda: next(
                times
            ),
            utc_now_text=lambda: (
                "2026-09-04T15:10:00Z"
            ),
        )

    assert (
        core.coinbase_backoff
        .consecutive_failures
        == 1
    )

    assert (
        core.coinbase_backoff
        .retry_not_before_monotonic_ns
        == 3_000_000_000
    )

    assert not (
        core.connections
        .current_coinbase
        .connected
    )
    errors = [event for event in events if event["event"] == "transport_error"]
    assert errors == [{
        "source": "coinbase", "event": "transport_error", "generation": 1,
        "monotonic_ns": 3_000_000_000, "failure_class": "CoinbaseWsGenerationTransportError",
        "close_code": None,
    }]

    core.close()


def test_websocket_error_frame_is_raw_persisted_before_failure(
    tmp_path,
):
    core, worker = make_core_worker(
        tmp_path
    )

    stop = threading.Event()

    frame = json.dumps(
        {
            "type": "error",
            "message": "test failure",
        }
    )

    ws = FakeWebSocket(
        frames=[frame],
        stop_event=stop,
    )

    connect = FakeConnectFactory(
        ws
    )

    times = iter(
        [
            1_000_000_000,
            2_000_000_000,
            3_000_000_000,
        ]
    )

    with pytest.raises(Exception):
        run_one_coinbase_generation(
            worker=worker,
            stop_event=stop,
            decision_epoch_s=(
                lambda: DECISION_S
            ),
            connect_fn=connect,
            monotonic_ns=lambda: next(
                times
            ),
            utc_now_text=lambda: (
                "2026-09-04T15:10:00Z"
            ),
        )

    raw = (
        core.manager(
            COINBASE_WS_SOURCE
        ).active_raw_path
    )

    assert raw is not None
    assert raw.exists()

    record = json.loads(
        raw.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )

    assert record["raw_text"] == frame

    core.close()

from datetime import datetime
import json
import threading
from unittest.mock import patch

import pytest

from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournalError,
)
from src.kxbtcd_candidate_e_soak_kalshi_worker import (
    KalshiReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_kalshi_ws_generation_transport import (
    KALSHI_WS_URL,
    run_one_kalshi_generation,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    KALSHI_WS_SOURCE,
    SoakSourceRuntimeCore,
)
from src.kxbtcd_candidate_e_soak_metric_producers import RuntimeMetricProducers


def epoch_ms(text):
    return int(
        datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
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
        ],
        "cursor": "",
    }


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


class StepClock:
    def __init__(
        self,
        *,
        start=0,
        step=1_000_000_000,
    ):
        self.value = start
        self.step = step

    def __call__(self):
        self.value += self.step
        return self.value


class FakePong:
    def __init__(
        self,
        value,
        waits,
    ):
        self.value = value
        self.waits = waits

    def wait(
        self,
        *,
        timeout,
    ):
        self.waits.append(
            timeout
        )
        return self.value

    def is_set(self):
        return self.value


class FakeWebSocket:
    def __init__(
        self,
        *,
        frames,
        pong_results,
        stop_event,
        stop_after_last=True,
    ):
        self.frames = list(
            frames
        )
        self.pong_results = list(
            pong_results
        )
        self.stop_event = (
            stop_event
        )
        self.stop_after_last = (
            stop_after_last
        )
        self.sent = []
        self.ping_payloads = []
        self.pong_wait_timeouts = []
        # The library updates this after a completed background keepalive.
        self.latency = 0.001

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

    def ping(self, payload=None):
        self.ping_payloads.append(
            payload
        )

        if not self.pong_results:
            raise AssertionError(
                "unexpected manual Ping"
            )

        return FakePong(
            self.pong_results.pop(0),
            self.pong_wait_timeouts,
        )

    def recv(
        self,
        *,
        timeout,
    ):
        if not self.frames:
            raise TimeoutError

        value = self.frames.pop(0)

        if (
            not self.frames
            and self.stop_after_last
        ):
            self.stop_event.set()

        return value


class ReceiveDrivenPongWebSocket(FakeWebSocket):
    """Expose a Pong only after the transport keeps receiving frames."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pong_ready = threading.Event()

    def ping(self, payload=None):
        self.ping_payloads.append(payload)
        websocket = self

        class ReceiveDrivenPong:
            def is_set(self):
                return websocket.pong_ready.is_set()

            def wait(self, *, timeout):
                websocket.pong_wait_timeouts.append(timeout)
                return websocket.pong_ready.is_set()

        return ReceiveDrivenPong()

    def recv(self, *, timeout):
        value = super().recv(timeout=timeout)
        self.pong_ready.set()
        return value


class FakeConnectFactory:
    def __init__(self, websocket):
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


def make_worker(tmp_path, metric_producers=None):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
        metric_producers=metric_producers,
    )

    core.discover_current_event_from_raw(
        raw_text=json.dumps(
            discovery_payload()
        ),
        received_monotonic_ns=1,
        received_utc=(
            "2026-09-04T15:30:00Z"
        ),
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

    return core, worker


def fake_headers(repo_root):
    return {
        "X-Test-Auth": "redacted",
    }


def test_generation_subscribes_full_ladder_and_reaches_ready(
    tmp_path,
):
    metrics = RuntimeMetricProducers(archive_root=tmp_path, clock_evidence_path=tmp_path / "clock")
    core, worker = make_worker(tmp_path, metrics)

    stop = threading.Event()

    tickers = tuple(
        market.market_ticker
        for market in core.current_event.markets
    )

    ws = FakeWebSocket(
        frames=[
            subscribed(),
            snapshot(
                tickers[0],
                1,
            ),
            snapshot(
                tickers[1],
                2,
            ),
        ],
        pong_results=[True],
        stop_event=stop,
    )

    connect = FakeConnectFactory(
        ws
    )

    clock = StepClock(
        step=4_000_000_000
    )

    result = run_one_kalshi_generation(
        worker=worker,
        stop_event=stop,
        connect_fn=connect,
        auth_headers_factory=(
            fake_headers
        ),
        monotonic_ns=clock,
        now_timestamp_ms=lambda: (
            NOW_MS
        ),
        utc_now_text=lambda: (
            "2026-09-04T15:30:05Z"
        ),
    )

    assert result.received_frame_count == 3
    assert result.manual_ping_attempts == 1
    assert result.manual_pong_successes == 1
    assert result.manual_pong_timeouts == 0
    assert result.final_action_kind == "READY"
    assert result.intentional_stop
    assert result.reconnect_decision is None
    assert metrics.counters["kalshi_snapshot_count"] == 2
    assert metrics.counters["kalshi_ping_attempts"] == 1
    assert metrics.counters["kalshi_pong_successes"] == 1
    assert metrics.generations["kalshi"] == 1

    assert len(connect.calls) == 1

    call = connect.calls[0]

    assert call["url"] == (
        KALSHI_WS_URL
    )

    assert call["ping_interval"] is None
    assert call["ping_timeout"] is None

    assert call["additional_headers"] == {
        "X-Test-Auth": "redacted",
    }

    assert len(ws.sent) == 1

    command = ws.sent[0]

    assert command["cmd"] == (
        "subscribe"
    )

    assert command["params"]["channels"] == [
        "orderbook_delta"
    ]

    assert set(
        command["params"][
            "market_tickers"
        ]
    ) == set(tickers)

    assert ws.ping_payloads == [None]

    assert not (
        core.connections
        .current_kalshi
        .connected
    )

    core.close()


def test_sequence_gap_closes_generation_and_arms_one_second_backoff(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    tickers = tuple(
        market.market_ticker
        for market in core.current_event.markets
    )

    ws = FakeWebSocket(
        frames=[
            subscribed(),
            snapshot(
                tickers[0],
                1,
            ),
            snapshot(
                tickers[1],
                2,
            ),
            json.dumps(
                {
                    "type": "orderbook_delta",
                    "seq": 4,
                    "msg": {
                        "market_ticker": (
                            tickers[0]
                        ),
                        "side": "yes",
                        "price_dollars": (
                            "0.50"
                        ),
                        "delta_fp": "1",
                    },
                }
            ),
        ],
        pong_results=[True],
        stop_event=stop,
        stop_after_last=False,
    )

    result = run_one_kalshi_generation(
        worker=worker,
        stop_event=stop,
        connect_fn=(
            FakeConnectFactory(
                ws
            )
        ),
        auth_headers_factory=(
            fake_headers
        ),
        monotonic_ns=(
            StepClock()
        ),
        now_timestamp_ms=lambda: (
            NOW_MS
        ),
        utc_now_text=lambda: (
            "2026-09-04T15:30:05Z"
        ),
    )

    assert result.final_action_kind == (
        "RECONNECT_REQUIRED"
    )

    assert result.final_action_reason == (
        "KALSHI_SEQUENCE_GAP"
    )

    assert (
        result
        .reconnect_decision
        .delay_seconds
        == 1
    )

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


def test_pending_pong_does_not_block_busy_application_frame_receive(
    tmp_path,
):
    core, worker = make_worker(tmp_path)
    stop = threading.Event()
    tickers = tuple(
        market.market_ticker
        for market in core.current_event.markets
    )
    ws = ReceiveDrivenPongWebSocket(
        frames=[
            subscribed(),
            snapshot(tickers[0], 1),
            snapshot(tickers[1], 2),
        ],
        pong_results=[],
        stop_event=stop,
    )

    result = run_one_kalshi_generation(
        worker=worker,
        stop_event=stop,
        connect_fn=FakeConnectFactory(ws),
        auth_headers_factory=fake_headers,
        monotonic_ns=StepClock(step=4_000_000_000),
        now_timestamp_ms=lambda: NOW_MS,
        utc_now_text=lambda: "2026-09-04T15:30:05Z",
    )

    assert result.received_frame_count == 3
    assert result.manual_ping_attempts == 1
    assert result.manual_pong_successes == 1
    assert result.manual_pong_timeouts == 0
    assert ws.pong_wait_timeouts == []
    core.close()


def test_missed_pong_never_refreshes_liveness_and_eventually_reconnects(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    # Six-second jumps: first application Ping succeeds; its successor
    # times out and routes the connection through the bounded backoff.
    clock = StepClock(
        step=6_000_000_000
    )

    ws = FakeWebSocket(
        frames=[],
        pong_results=[
            True,
            False,
        ],
        stop_event=stop,
        stop_after_last=False,
    )

    result = run_one_kalshi_generation(
        worker=worker,
        stop_event=stop,
        connect_fn=(
            FakeConnectFactory(
                ws
            )
        ),
        auth_headers_factory=(
            fake_headers
        ),
        monotonic_ns=clock,
        now_timestamp_ms=lambda: (
            NOW_MS
        ),
        utc_now_text=lambda: (
            "2026-09-04T15:30:05Z"
        ),
    )

    assert result.final_action_kind == (
        "RECONNECT_REQUIRED"
    )

    assert result.final_action_reason == "KALSHI_PONG_UNPROVEN"

    assert result.manual_ping_attempts == 2
    assert result.manual_pong_successes == 1
    assert result.manual_pong_timeouts == 1

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 1
    )

    core.close()


def test_unproven_initial_pong_timeout_reconnects_immediately(tmp_path):
    core, worker = make_worker(tmp_path)
    stop = threading.Event()
    ws = FakeWebSocket(
        frames=[],
        pong_results=[False],
        stop_event=stop,
        stop_after_last=False,
    )
    ws.latency = None

    result = run_one_kalshi_generation(
        worker=worker,
        stop_event=stop,
        connect_fn=FakeConnectFactory(ws),
        auth_headers_factory=fake_headers,
        monotonic_ns=StepClock(),
        now_timestamp_ms=lambda: NOW_MS,
        utc_now_text=lambda: "2026-09-04T15:30:05Z",
    )

    assert result.final_action_kind == "RECONNECT_REQUIRED"
    assert result.final_action_reason == "KALSHI_PONG_UNPROVEN"
    assert result.manual_ping_attempts == 1
    assert result.manual_pong_successes == 0
    assert result.manual_pong_timeouts == 1
    assert core.kalshi_backoff.consecutive_failures == 1
    core.close()


def test_event_expiry_is_rollover_without_network_failure_backoff(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    ws = FakeWebSocket(
        frames=[],
        pong_results=[],
        stop_event=stop,
        stop_after_last=False,
    )

    result = run_one_kalshi_generation(
        worker=worker,
        stop_event=stop,
        connect_fn=(
            FakeConnectFactory(
                ws
            )
        ),
        auth_headers_factory=(
            fake_headers
        ),
        monotonic_ns=(
            StepClock()
        ),
        now_timestamp_ms=lambda: (
            epoch_ms(
                "2026-09-04T16:00:00Z"
            )
        ),
        utc_now_text=lambda: (
            "2026-09-04T16:00:00Z"
        ),
    )

    assert result.final_action_kind == (
        "ROLLOVER_REQUIRED"
    )

    assert result.final_action_reason == (
        "SELECTED_EVENT_CLOSED"
    )

    assert result.reconnect_decision is None

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 0
    )

    core.close()


def test_local_raw_failure_hard_fails_without_arming_network_backoff(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    ws = FakeWebSocket(
        frames=[
            subscribed(),
        ],
        pong_results=[
            True,
        ],
        stop_event=stop,
        stop_after_last=False,
    )

    manager = core.manager(
        KALSHI_WS_SOURCE
    )

    def fail_append(**kwargs):
        raise RuntimeRawJournalError(
            "synthetic Kalshi disk failure"
        )

    with patch.object(
        manager,
        "append",
        side_effect=fail_append,
    ):
        with pytest.raises(
            RuntimeRawJournalError,
            match="Kalshi disk failure",
        ):
            run_one_kalshi_generation(
                worker=worker,
                stop_event=stop,
                connect_fn=(
                    FakeConnectFactory(
                        ws
                    )
                ),
                auth_headers_factory=(
                    fake_headers
                ),
                monotonic_ns=(
                    StepClock()
                ),
                now_timestamp_ms=(
                    lambda: NOW_MS
                ),
                utc_now_text=lambda: (
                    "2026-09-04T15:30:05Z"
                ),
            )

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 0
    )

    assert not (
        core.connections
        .current_kalshi
        .connected
    )

    core.close()


def test_ws_error_or_binary_failure_never_exposes_auth_headers_to_raw_archive(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )
    events = []
    core.observability = type(
        "Observer",
        (),
        {
            "record_source_event": (
                lambda self, **kwargs: events.append(kwargs)
            ),
            "record_latency": (
                lambda self, *args, **kwargs: None
            ),
        },
    )()

    stop = threading.Event()

    ws = FakeWebSocket(
        frames=[
            b"binary",
        ],
        pong_results=[
            True,
        ],
        stop_event=stop,
        stop_after_last=False,
    )

    with pytest.raises(
        Exception,
        match="binary",
    ):
        run_one_kalshi_generation(
            worker=worker,
            stop_event=stop,
            connect_fn=(
                FakeConnectFactory(
                    ws
                )
            ),
            auth_headers_factory=(
                fake_headers
            ),
            monotonic_ns=(
                StepClock()
            ),
            now_timestamp_ms=lambda: (
                NOW_MS
            ),
            utc_now_text=lambda: (
                "2026-09-04T15:30:05Z"
            ),
        )

    raw = core.manager(
        KALSHI_WS_SOURCE
    ).active_raw_path

    if raw is not None and raw.exists():
        content = raw.read_text(
            encoding="utf-8"
        )

        assert "X-Test-Auth" not in content
        assert "redacted" not in content

    # Binary transport failure is a source failure, not local storage failure.
    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 1
    )
    transport_errors = [
        event for event in events
        if event["event"] == "transport_error"
    ]
    assert len(transport_errors) == 1
    assert transport_errors[0]["source"] == "kalshi"
    assert transport_errors[0]["generation"] == 1
    assert transport_errors[0]["event_ticker"] == "KXBTCD-26SEP0416"
    assert (
        transport_errors[0]["failure_class"]
        == "KalshiWsGenerationTransportError"
    )
    assert isinstance(transport_errors[0]["monotonic_ns"], int)

    core.close()

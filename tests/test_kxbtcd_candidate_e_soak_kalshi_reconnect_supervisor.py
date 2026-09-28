from datetime import datetime
import json
from types import SimpleNamespace
import threading

import pytest

from src.kxbtcd_candidate_e_prospective_live_collector import (
    ProspectiveLiveCollectorError,
)
from src.kxbtcd_candidate_e_soak_failure_policy import (
    is_local_fatal_exception,
)
from src.kxbtcd_candidate_e_soak_kalshi_reconnect_supervisor import (
    run_kalshi_reconnect_supervisor,
)
from src.kxbtcd_candidate_e_soak_kalshi_worker import (
    KalshiReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
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

ROLLOVER_MS = epoch_ms(
    "2026-09-04T16:00:00Z"
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


def first_payload():
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
        ],
        "cursor": "",
    }


def rollover_payload():
    return {
        "markets": [
            market(
                event="KXBTCD-26SEP0417",
                ticker=(
                    "KXBTCD-26SEP0417-T110000.00"
                ),
                close_time=(
                    "2026-09-04T17:00:00Z"
                ),
            ),
        ],
        "cursor": "",
    }


def new_core(tmp_path, metric_producers=None):
    return SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
        metric_producers=metric_producers,
    )


def install_first_event(core):
    core.discover_current_event_from_raw(
        raw_text=json.dumps(
            first_payload()
        ),
        received_monotonic_ns=1,
        received_utc=(
            "2026-09-04T15:30:00Z"
        ),
        now_timestamp_ms=NOW_MS,
        request_identity={
            "method": "GET",
        },
    )


def clean_stop_result():
    return SimpleNamespace(
        intentional_stop=True,
        final_action_kind="READY",
        final_action_reason="PASS",
        reconnect_decision=None,
    )


def rollover_result():
    return SimpleNamespace(
        intentional_stop=False,
        final_action_kind=(
            "ROLLOVER_REQUIRED"
        ),
        final_action_reason=(
            "SELECTED_EVENT_CLOSED"
        ),
        reconnect_decision=None,
    )


def reconnect_result(decision):
    return SimpleNamespace(
        intentional_stop=False,
        final_action_kind=(
            "RECONNECT_REQUIRED"
        ),
        final_action_reason=(
            "KALSHI_SEQUENCE_GAP"
        ),
        reconnect_decision=decision,
    )


def test_initial_rest_failure_retries_then_discovers_and_starts_ws(
    tmp_path,
):
    metrics = RuntimeMetricProducers(archive_root=tmp_path, clock_evidence_path=tmp_path / "clock")
    core = new_core(tmp_path, metrics)

    worker = KalshiReadOnlyWorkerSession(
        core
    )

    stop = threading.Event()

    clock = {
        "ns": 0,
    }

    def mono():
        return clock["ns"]

    def sleep(seconds):
        clock["ns"] += int(
            seconds
            * 1_000_000_000
        )

    discovery_calls = {
        "count": 0,
    }

    def rediscover():
        discovery_calls["count"] += 1

        if discovery_calls["count"] == 1:
            raise ConnectionError(
                "synthetic Kalshi REST outage"
            )

        core.discover_current_event_from_raw(
            raw_text=json.dumps(
                first_payload()
            ),
            received_monotonic_ns=(
                mono()
            ),
            received_utc=(
                "2026-09-04T15:30:00Z"
            ),
            now_timestamp_ms=NOW_MS,
            request_identity={
                "method": "GET",
            },
        )

    generation_calls = {
        "count": 0,
    }

    def generation():
        generation_calls["count"] += 1
        stop.set()
        return clean_stop_result()

    summary = run_kalshi_reconnect_supervisor(
        worker=worker,
        stop_event=stop,
        run_generation=generation,
        rediscover_current_event=(
            rediscover
        ),
        monotonic_ns=mono,
        sleep_seconds=sleep,
    )

    assert discovery_calls["count"] == 2
    assert generation_calls["count"] == 1

    assert summary.rediscovery_attempts == 2
    assert summary.rediscovery_failures == 1
    assert summary.recoverable_failures == 1
    assert summary.generations_started == 1
    assert summary.stopped_cleanly
    assert metrics.counters["kalshi_reconnect_attempts"] == 1

    # REST success alone is not source readiness, so the prior failure
    # history is deliberately not reset here.
    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 1
    )

    core.close()


def test_rollover_clears_wait_but_preserves_failure_count(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    install_first_event(
        core
    )

    worker = KalshiReadOnlyWorkerSession(
        core
    )

    # Pretend two source failures happened before rollover.
    core.record_source_failure(
        "kalshi",
        observed_monotonic_ns=100,
    )

    core.record_source_failure(
        "kalshi",
        observed_monotonic_ns=200,
    )

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 2
    )

    stop = threading.Event()

    clock = {
        "ns": 0,
    }

    def mono():
        return clock["ns"]

    def sleep(seconds):
        clock["ns"] += int(
            seconds
            * 1_000_000_000
        )

    rediscovery_calls = {
        "count": 0,
    }

    def rediscover():
        rediscovery_calls["count"] += 1

        # intentional_rollover() must clear only the wait.
        assert (
            core.kalshi_backoff
            .retry_not_before_monotonic_ns
            == 0
        )

        assert (
            core.kalshi_backoff
            .consecutive_failures
            == 2
        )

        core.discover_current_event_from_raw(
            raw_text=json.dumps(
                rollover_payload()
            ),
            received_monotonic_ns=(
                mono()
            ),
            received_utc=(
                "2026-09-04T16:00:00Z"
            ),
            now_timestamp_ms=(
                ROLLOVER_MS
            ),
            request_identity={
                "method": "GET",
            },
        )

    generation_calls = {
        "count": 0,
    }

    def generation():
        generation_calls["count"] += 1

        if generation_calls["count"] == 1:
            return rollover_result()

        if generation_calls["count"] == 2:
            raise ConnectionError(
                "synthetic post-rollover WS outage"
            )

        stop.set()
        return clean_stop_result()

    summary = run_kalshi_reconnect_supervisor(
        worker=worker,
        stop_event=stop,
        run_generation=generation,
        rediscover_current_event=(
            rediscover
        ),
        monotonic_ns=mono,
        sleep_seconds=sleep,
    )

    assert summary.rollovers == 1
    assert summary.rediscovery_attempts == 1
    assert rediscovery_calls["count"] == 1

    assert core.current_event.event_ticker == (
        "KXBTCD-26SEP0417"
    )

    # Failure history 2 was preserved across rollover.
    # The following WS outage therefore becomes failure #3, whose frozen
    # reconnect delay is 4 seconds.
    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 3
    )

    assert (
        core.kalshi_backoff
        .retry_not_before_monotonic_ns
        > 0
    )

    assert summary.recoverable_failures == 1
    assert summary.generations_started == 3

    core.close()


def test_returned_reconnect_decision_is_not_double_counted(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    install_first_event(
        core
    )

    worker = KalshiReadOnlyWorkerSession(
        core
    )

    stop = threading.Event()

    clock = {
        "ns": 0,
    }

    def mono():
        return clock["ns"]

    def sleep(seconds):
        clock["ns"] += int(
            seconds
            * 1_000_000_000
        )

    calls = {
        "count": 0,
    }

    def generation():
        calls["count"] += 1

        if calls["count"] == 1:
            decision = (
                core.record_source_failure(
                    "kalshi",
                    observed_monotonic_ns=(
                        mono()
                    ),
                )
            )

            return reconnect_result(
                decision
            )

        stop.set()
        return clean_stop_result()

    summary = run_kalshi_reconnect_supervisor(
        worker=worker,
        stop_event=stop,
        run_generation=generation,
        rediscover_current_event=lambda: None,
        monotonic_ns=mono,
        sleep_seconds=sleep,
    )

    assert summary.recoverable_failures == 1

    # Exactly one failure, not one from generation + another from supervisor.
    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 1
    )

    core.close()


def test_local_credential_configuration_failure_hard_fails_without_retry(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    install_first_event(
        core
    )

    worker = KalshiReadOnlyWorkerSession(
        core
    )

    stop = threading.Event()

    calls = {
        "count": 0,
    }

    def generation():
        calls["count"] += 1

        raise ProspectiveLiveCollectorError(
            "synthetic credential boundary failure"
        )

    with pytest.raises(
        ProspectiveLiveCollectorError,
        match="credential boundary failure",
    ):
        run_kalshi_reconnect_supervisor(
            worker=worker,
            stop_event=stop,
            run_generation=generation,
            rediscover_current_event=lambda: None,
            monotonic_ns=lambda: 100,
            sleep_seconds=lambda _: None,
        )

    assert calls["count"] == 1

    assert (
        core.kalshi_backoff
        .consecutive_failures
        == 0
    )

    core.close()


def test_existing_collector_validation_error_is_shared_local_fatal():
    assert is_local_fatal_exception(
        ProspectiveLiveCollectorError(
            "x"
        )
    )

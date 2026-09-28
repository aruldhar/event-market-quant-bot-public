import threading

import pytest

from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournalError,
)
from src.kxbtcd_candidate_e_soak_coinbase_reconnect_supervisor import (
    is_local_fatal_exception,
    run_coinbase_reconnect_supervisor,
)
from src.kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    SoakSourceRuntimeCore,
)
from src.kxbtcd_candidate_e_soak_metric_producers import RuntimeMetricProducers


def make_worker(tmp_path, metric_producers=None):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
        metric_producers=metric_producers,
    )

    worker = CoinbaseReadOnlyWorkerSession(
        core
    )

    return core, worker


def test_recoverable_failures_use_frozen_backoff_and_fresh_generations(
    tmp_path,
):
    metrics = RuntimeMetricProducers(archive_root=tmp_path, clock_evidence_path=tmp_path / "clock")
    core, worker = make_worker(tmp_path, metrics)

    stop = threading.Event()

    clock = {
        "ns": 1_000_000_000,
    }

    observed_generations = []
    calls = {
        "count": 0,
    }

    def mono():
        return clock["ns"]

    def sleep(seconds):
        clock["ns"] += int(
            seconds * 1_000_000_000
        )

    def generation():
        binding = worker.start_generation(
            opened_monotonic_ns=mono()
        )

        observed_generations.append(
            binding.generation
        )

        calls["count"] += 1

        if calls["count"] <= 2:
            raise ConnectionError(
                "synthetic source outage"
            )

        stop.set()

    summary = run_coinbase_reconnect_supervisor(
        worker=worker,
        stop_event=stop,
        run_generation=generation,
        monotonic_ns=mono,
        sleep_seconds=sleep,
    )

    assert observed_generations == [
        1,
        2,
        3,
    ]

    assert summary.generations_started == 3
    assert summary.recoverable_failures == 2
    assert summary.hard_failures == 0
    assert summary.stopped_cleanly
    assert metrics.counters["coinbase_reconnect_attempts"] == 2
    assert metrics.generations["coinbase"] == 3

    # Failure 1 -> 1s, failure 2 -> 2s.
    # Readiness never passed, so backoff was not reset by mere reconnect.
    assert (
        core.coinbase_backoff
        .consecutive_failures
        == 2
    )

    core.close()


def test_local_raw_failure_hard_fails_without_retry(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    calls = {
        "count": 0,
    }

    def generation():
        worker.start_generation(
            opened_monotonic_ns=100
        )

        calls["count"] += 1

        raise RuntimeRawJournalError(
            "synthetic disk failure"
        )

    with pytest.raises(
        RuntimeRawJournalError,
        match="disk failure",
    ):
        run_coinbase_reconnect_supervisor(
            worker=worker,
            stop_event=stop,
            run_generation=generation,
            monotonic_ns=lambda: 200,
            sleep_seconds=lambda _: None,
        )

    assert calls["count"] == 1

    # Hard local storage failure must not arm network reconnect backoff.
    assert (
        core.coinbase_backoff
        .consecutive_failures
        == 0
    )

    assert not (
        core.connections
        .current_coinbase
        .connected
    )

    core.close()


def test_already_closed_generation_does_not_double_count_failure(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    calls = {
        "count": 0,
    }

    clock = {
        "ns": 1_000_000_000,
    }

    def mono():
        return clock["ns"]

    def sleep(seconds):
        clock["ns"] += int(
            seconds * 1_000_000_000
        )

    def generation():
        worker.start_generation(
            opened_monotonic_ns=mono()
        )

        calls["count"] += 1

        if calls["count"] == 1:
            worker.disconnect(
                closed_monotonic_ns=mono(),
                count_as_failure=True,
            )

            raise ConnectionError(
                "transport already classified failure"
            )

        stop.set()

    summary = run_coinbase_reconnect_supervisor(
        worker=worker,
        stop_event=stop,
        run_generation=generation,
        monotonic_ns=mono,
        sleep_seconds=sleep,
    )

    assert summary.recoverable_failures == 1

    # Exactly one recorded failure, not one in generation + another in
    # supervisor.
    assert (
        core.coinbase_backoff
        .consecutive_failures
        == 1
    )

    core.close()


def test_global_stop_is_clean_and_does_not_arm_backoff(
    tmp_path,
):
    core, worker = make_worker(
        tmp_path
    )

    stop = threading.Event()

    def generation():
        worker.start_generation(
            opened_monotonic_ns=100
        )

        stop.set()

    summary = run_coinbase_reconnect_supervisor(
        worker=worker,
        stop_event=stop,
        run_generation=generation,
        monotonic_ns=lambda: 200,
        sleep_seconds=lambda _: None,
    )

    assert summary.generations_started == 1
    assert summary.recoverable_failures == 0
    assert summary.hard_failures == 0
    assert summary.stopped_cleanly

    assert (
        core.coinbase_backoff
        .consecutive_failures
        == 0
    )

    assert not (
        core.connections
        .current_coinbase
        .connected
    )

    core.close()


def test_exception_classifier_marks_raw_failure_local_fatal():
    assert is_local_fatal_exception(
        RuntimeRawJournalError("x")
    )

    assert not is_local_fatal_exception(
        ConnectionError("x")
    )

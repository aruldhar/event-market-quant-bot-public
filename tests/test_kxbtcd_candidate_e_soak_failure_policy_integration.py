import threading
from unittest.mock import patch

import pytest

from src.kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournalError,
)
from src.kxbtcd_candidate_e_soak_coinbase_reconnect_supervisor import (
    run_coinbase_reconnect_supervisor,
)
from src.kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_coinbase_ws_generation_transport import (
    run_one_coinbase_generation,
)
from src.kxbtcd_candidate_e_soak_failure_policy import (
    is_local_fatal_exception,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    COINBASE_WS_SOURCE,
    SoakSourceRuntimeCore,
)


class FakeWebSocket:
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
        return None

    def recv(
        self,
        *,
        timeout,
    ):
        return '{"type":"subscriptions","channels":[]}'


def fake_connect(
    url,
    **kwargs,
):
    return FakeWebSocket()


def test_local_raw_failure_through_real_generation_does_not_arm_backoff(
    tmp_path,
):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
    )

    worker = CoinbaseReadOnlyWorkerSession(
        core
    )

    stop = threading.Event()

    clock = {
        "ns": 0,
    }

    def mono():
        clock["ns"] += 1_000_000_000
        return clock["ns"]

    manager = core.manager(
        COINBASE_WS_SOURCE
    )

    def fail_append(**kwargs):
        raise RuntimeRawJournalError(
            "synthetic local disk failure"
        )

    generation_calls = {
        "count": 0,
    }

    def generation():
        generation_calls["count"] += 1

        return run_one_coinbase_generation(
            worker=worker,
            stop_event=stop,
            decision_epoch_s=lambda: 1_788_534_000,
            connect_fn=fake_connect,
            monotonic_ns=mono,
            utc_now_text=lambda: (
                "2026-09-04T15:30:00Z"
            ),
        )

    with patch.object(
        manager,
        "append",
        side_effect=fail_append,
    ):
        with pytest.raises(
            RuntimeRawJournalError,
            match="local disk failure",
        ):
            run_coinbase_reconnect_supervisor(
                worker=worker,
                stop_event=stop,
                run_generation=generation,
                monotonic_ns=mono,
                sleep_seconds=lambda _: None,
            )

    assert generation_calls["count"] == 1

    # Critical invariant:
    # local evidence failure did NOT become a network reconnect failure.
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


def test_network_failure_remains_non_local_fatal():
    assert not is_local_fatal_exception(
        ConnectionError(
            "synthetic network outage"
        )
    )


def test_raw_failure_is_local_fatal():
    assert is_local_fatal_exception(
        RuntimeRawJournalError(
            "synthetic disk failure"
        )
    )

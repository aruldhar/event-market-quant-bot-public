import threading

import pytest

from src.kxbtcd_candidate_e_v2_coinbase_input_supervisor import (
    V2CoinbaseInputSupervisorError,
    run_v2_coinbase_input_supervisor,
)


def test_websocket_archive_can_continue_through_a_transport_drop_while_rest_runs():
    seen = []
    def ws(stop):
        # This represents the already-contained reconnect supervisor handling
        # a recoverable socket close, then continuing to archive.
        seen.append("ws_recovered")
        stop.wait()
    def rest(stop):
        seen.append("rest_running")
        stop.wait()
    ticks = []
    def sleep(_):
        ticks.append(1)
        if len(ticks) == 2:
            stop.set()
    stop = threading.Event()
    run_v2_coinbase_input_supervisor(stop_event=stop, run_rest_candle_supervisor=rest,
        run_ws_archive_supervisor=ws, sleep_seconds=sleep, join_timeout_seconds=1)
    assert set(seen) == {"ws_recovered", "rest_running"}


def test_archive_integrity_exception_remains_fail_closed():
    stop = threading.Event()
    def fail(_):
        raise RuntimeError("archive invariant")
    with pytest.raises(V2CoinbaseInputSupervisorError, match="WS archive supervisor exception"):
        run_v2_coinbase_input_supervisor(stop_event=stop, run_rest_candle_supervisor=lambda event: event.wait(),
            run_ws_archive_supervisor=fail, join_timeout_seconds=1)

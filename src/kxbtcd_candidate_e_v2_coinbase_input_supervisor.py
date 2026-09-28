"""Run V2's critical REST input beside a non-critical Coinbase WS archive."""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable


class V2CoinbaseInputSupervisorError(RuntimeError):
    pass


@dataclass
class _WorkerState:
    returned: bool = False
    exception: BaseException | None = None


def run_v2_coinbase_input_supervisor(*, stop_event: threading.Event,
                                     run_rest_candle_supervisor: Callable[[threading.Event], object],
                                     run_ws_archive_supervisor: Callable[[threading.Event], object],
                                     sleep_seconds: Callable[[float], None] = time.sleep,
                                     join_timeout_seconds: float = 12.0) -> None:
    """Keep WS archival failures separate from frozen V2's REST input.

    The archive supervisor itself handles recoverable WebSocket transport
    failures.  If it escapes with an exception, that is an internal archive or
    lifecycle failure and remains fail-closed rather than being mislabeled as
    a harmless connection drop.
    """
    if join_timeout_seconds <= 0:
        raise V2CoinbaseInputSupervisorError("join_timeout_seconds must be positive")
    ws_state = _WorkerState()

    def run_ws() -> None:
        try:
            run_ws_archive_supervisor(stop_event)
        except BaseException as exc:
            ws_state.exception = exc
        finally:
            ws_state.returned = True

    ws_thread = threading.Thread(target=run_ws, name="candidate-e-v2-coinbase-archive", daemon=False)
    ws_thread.start()
    rest_state = _WorkerState()

    def run_rest() -> None:
        try:
            run_rest_candle_supervisor(stop_event)
        except BaseException as exc:
            rest_state.exception = exc
        finally:
            rest_state.returned = True

    rest_thread = threading.Thread(target=run_rest, name="candidate-e-v2-coinbase-rest", daemon=False)
    rest_thread.start()
    try:
        while not stop_event.is_set():
            if rest_state.exception is not None:
                raise V2CoinbaseInputSupervisorError(
                    "V2 REST candle supervisor exception: " + type(rest_state.exception).__name__
                ) from rest_state.exception
            if rest_state.returned:
                raise V2CoinbaseInputSupervisorError("V2 REST candle supervisor exited unexpectedly")
            if ws_state.exception is not None:
                raise V2CoinbaseInputSupervisorError(
                    "Coinbase WS archive supervisor exception: " + type(ws_state.exception).__name__
                ) from ws_state.exception
            if ws_state.returned:
                raise V2CoinbaseInputSupervisorError("Coinbase WS archive supervisor exited unexpectedly")
            sleep_seconds(0.1)
    finally:
        stop_event.set()
        ws_thread.join(timeout=join_timeout_seconds)
        rest_thread.join(timeout=join_timeout_seconds)
        if ws_thread.is_alive() or rest_thread.is_alive():
            raise V2CoinbaseInputSupervisorError("Coinbase input supervisor stop timeout")

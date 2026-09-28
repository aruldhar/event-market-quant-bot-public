"""Bind read-only worker sessions to their reconnect supervisors.

Generation and rediscovery callables are injected.  This makes the production
assembly testable with fakes and prevents this wiring layer from opening a
network connection by itself.
"""
from __future__ import annotations

from .kxbtcd_candidate_e_soak_coinbase_reconnect_supervisor import run_coinbase_reconnect_supervisor
from .kxbtcd_candidate_e_soak_coinbase_worker import CoinbaseReadOnlyWorkerSession
from .kxbtcd_candidate_e_soak_kalshi_reconnect_supervisor import run_kalshi_reconnect_supervisor
from .kxbtcd_candidate_e_soak_kalshi_worker import KalshiReadOnlyWorkerSession


def assemble_read_only_supervisors(*, core, run_coinbase_generation,
                                   run_kalshi_generation, rediscover_current_event):
    """Return supervisor callables that share one core-owned archive/state."""
    coinbase_worker = CoinbaseReadOnlyWorkerSession(core)
    kalshi_worker = KalshiReadOnlyWorkerSession(core)

    def coinbase(stop_event):
        return run_coinbase_reconnect_supervisor(
            worker=coinbase_worker, stop_event=stop_event,
            run_generation=lambda: run_coinbase_generation(coinbase_worker, stop_event))

    def kalshi(stop_event):
        return run_kalshi_reconnect_supervisor(
            worker=kalshi_worker, stop_event=stop_event,
            run_generation=lambda: run_kalshi_generation(kalshi_worker, stop_event),
            rediscover_current_event=lambda: rediscover_current_event(core))

    return coinbase, kalshi

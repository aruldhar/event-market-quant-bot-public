"""Concrete read-only transport callbacks for supervisor assembly.

Construction is network-free.  The injected callables open source transports
only when a supervisor invokes them after the explicit live command gate.
"""
from __future__ import annotations

from pathlib import Path
import time

from .kxbtcd_candidate_e_soak_coinbase_ws_generation_transport import run_one_coinbase_generation
from .kxbtcd_candidate_e_soak_kalshi_rest_transport import fetch_current_kxbtcd_event
from .kxbtcd_candidate_e_soak_kalshi_rest_transport import fetch_kalshi_final_market_settlement
from .kxbtcd_candidate_e_soak_kalshi_ws_generation_transport import run_one_kalshi_generation


def assemble_read_only_transport_callbacks(*, http_session, settlement_http_session=None, repo_root=".",
                                           monotonic_ns=time.monotonic_ns,
                                           epoch_seconds=time.time,
                                           enable_coinbase_ws_rest_repairs=True):
    """Return Coinbase generation, Kalshi generation, and rediscovery callbacks."""
    root = Path(repo_root)
    settlement_session = http_session if settlement_http_session is None else settlement_http_session
    settlement_next_due_ns = 0
    settlement_cursor = 0

    def observe_optional_settlements(worker):
        """Probe one queued prior-event market at most every ten seconds.

        This executes on the existing Kalshi thread, is bounded to a two-second
        public GET, and intentionally swallows every error: dashboard evidence
        cannot stop or degrade the read-only collector's safety lifecycle.
        """
        nonlocal settlement_next_due_ns, settlement_cursor
        core = worker.core
        if core.live_shadow_settlement_publisher is None:
            return
        now = int(monotonic_ns())
        if now < settlement_next_due_ns:
            return
        tickers = core.pending_live_shadow_settlement_tickers()
        if not tickers:
            return
        ticker = tickers[settlement_cursor % len(tickers)]
        settlement_cursor += 1
        settlement_next_due_ns = now + 10_000_000_000
        try:
            fetch_kalshi_final_market_settlement(
                session=settlement_session, core=core, market_ticker=ticker,
                monotonic_ns=monotonic_ns,
            )
        except Exception:
            return

    def coinbase_generation(worker, stop_event):
        return run_one_coinbase_generation(
            worker=worker, stop_event=stop_event,
            http_session=(http_session if enable_coinbase_ws_rest_repairs else None),
            decision_epoch_s=lambda: int(epoch_seconds()), monotonic_ns=monotonic_ns)

    def kalshi_generation(worker, stop_event):
        return run_one_kalshi_generation(
            worker=worker, stop_event=stop_event, repo_root=root, monotonic_ns=monotonic_ns,
            observe_optional_instrumentation=lambda: observe_optional_settlements(worker))

    def rediscover_current_event(core):
        return fetch_current_kxbtcd_event(
            session=http_session, core=core, now_timestamp_ms=int(epoch_seconds() * 1000),
            monotonic_ns=monotonic_ns)

    return coinbase_generation, kalshi_generation, rediscover_current_event

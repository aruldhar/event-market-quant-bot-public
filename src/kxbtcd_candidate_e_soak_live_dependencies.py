"""Concrete read-only supervisor dependencies for the executable soak."""
from __future__ import annotations

from .kxbtcd_candidate_e_soak_source_supervisor_assembly import assemble_read_only_supervisors
from .kxbtcd_candidate_e_soak_transport_assembly import assemble_read_only_transport_callbacks
from .kxbtcd_candidate_e_v2_coinbase_input_supervisor import run_v2_coinbase_input_supervisor
from .kxbtcd_candidate_e_v2_rest_candle_transport import run_v2_rest_candle_polling_supervisor


def build_read_only_supervisors(*, core, http_session, repo_root="."):
    """Compose V2's independent REST input and non-critical WS archive."""
    # The final-settlement observer executes from the Kalshi worker. Keep its
    # session separate from Coinbase's REST polling thread.
    import requests
    coinbase_generation, kalshi_generation, rediscover = assemble_read_only_transport_callbacks(
        http_session=http_session, settlement_http_session=requests.Session(), repo_root=repo_root,
        enable_coinbase_ws_rest_repairs=False)
    coinbase_archive, kalshi = assemble_read_only_supervisors(
        core=core, run_coinbase_generation=coinbase_generation,
        run_kalshi_generation=kalshi_generation, rediscover_current_event=rediscover)

    def coinbase(stop_event):
        return run_v2_coinbase_input_supervisor(
            stop_event=stop_event,
            run_ws_archive_supervisor=coinbase_archive,
            run_rest_candle_supervisor=lambda child_stop: run_v2_rest_candle_polling_supervisor(
                stop_event=child_stop, session=http_session, core=core),
        )

    return coinbase, kalshi

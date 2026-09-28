"""Bounded public-data closeout for unresolved live-shadow positions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import json

from .kxbtcd_candidate_e_live_shadow_settlement_feed import (
    LiveShadowSettlementPublisher,
)
from .kxbtcd_candidate_e_live_shadow_simulation_store import (
    LiveShadowSimulationStore,
)
from .kxbtcd_candidate_e_soak_kalshi_rest_transport import (
    fetch_kalshi_final_market_settlement,
)
from .kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore
from .kxbtcd_candidate_e_soak_archive import write_json_atomic


CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME = "settlement_closeout.json"
CLOSEOUT_RECEIPT_SCHEMA_VERSION = "kxbtcd_candidate_e_live_shadow_closeout.v1"


class LiveShadowSettlementCloseoutError(ValueError):
    pass


@dataclass(frozen=True)
class LiveShadowSettlementCloseoutReceipt:
    run_id: str
    status: str
    unresolved_market_tickers: tuple[str, ...]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveShadowSettlementCloseoutError(f"{field} is required")
    return value


def write_live_shadow_settlement_closeout_receipt(
    *, output_path: str | Path, receipt: LiveShadowSettlementCloseoutReceipt,
) -> None:
    path = Path(output_path)
    if path.name != CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME:
        raise LiveShadowSettlementCloseoutError("closeout receipt filename is invalid")
    if receipt.status not in {"SETTLED", "DEADLINE_EXPIRED", "NO_OPEN_POSITIONS", "COLLECTOR_NOT_TERMINAL"}:
        raise LiveShadowSettlementCloseoutError("closeout receipt status is invalid")
    tickers = tuple(sorted(set(receipt.unresolved_market_tickers)))
    if tickers != receipt.unresolved_market_tickers or any(not ticker for ticker in tickers):
        raise LiveShadowSettlementCloseoutError("closeout receipt tickers are invalid")
    write_json_atomic(path, {
        "schema_version": CLOSEOUT_RECEIPT_SCHEMA_VERSION,
        "run_id": _text(receipt.run_id, "run_id"),
        "status": receipt.status,
        "unresolved_market_tickers": list(tickers),
    })


def _validated_receipt(
    *, run_id: str, status: object, unresolved_market_tickers: object,
) -> LiveShadowSettlementCloseoutReceipt:
    if status not in {"SETTLED", "DEADLINE_EXPIRED", "NO_OPEN_POSITIONS", "COLLECTOR_NOT_TERMINAL"}:
        raise LiveShadowSettlementCloseoutError("closeout receipt status is invalid")
    if not isinstance(unresolved_market_tickers, list) or any(
        not isinstance(ticker, str) or not ticker for ticker in unresolved_market_tickers
    ):
        raise LiveShadowSettlementCloseoutError("closeout receipt tickers are invalid")
    tickers = tuple(unresolved_market_tickers)
    if tickers != tuple(sorted(set(tickers))):
        raise LiveShadowSettlementCloseoutError("closeout receipt tickers are invalid")
    return LiveShadowSettlementCloseoutReceipt(run_id, status, tickers)


def read_live_shadow_settlement_closeout_receipt(
    *, path: str | Path, run_id: str,
) -> LiveShadowSettlementCloseoutReceipt:
    source = Path(path)
    if source.name != CANONICAL_SETTLEMENT_CLOSEOUT_RECEIPT_FILENAME:
        raise LiveShadowSettlementCloseoutError("closeout receipt filename is invalid")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LiveShadowSettlementCloseoutError("closeout receipt is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != CLOSEOUT_RECEIPT_SCHEMA_VERSION:
        raise LiveShadowSettlementCloseoutError("closeout receipt schema is invalid")
    if payload.get("run_id") != run_id:
        raise LiveShadowSettlementCloseoutError("closeout receipt run id is invalid")
    return _validated_receipt(
        run_id=run_id, status=payload.get("status"),
        unresolved_market_tickers=payload.get("unresolved_market_tickers"),
    )


def unresolved_shadow_market_tickers(*, store_path: str | Path, run_id: str) -> tuple[str, ...]:
    """Return every market ticker with a shadow position still awaiting an
    official result -- across the legacy edge scenarios *and* every strategy
    lane in the strategy-lane matrix. A lane-only open position (for example, a
    stricter profit-target lane still holding after its baseline counterpart
    already exited) must not be invisible to closeout just because no legacy
    scenario also happens to be open on the same ticker.
    """
    store = LiveShadowSimulationStore(store_path, read_only=True)
    try:
        states = (
            *store.states(run_id).values(),
            *store.strategy_states(run_id).values(),
        )
        tickers = {
            state.simulation_state.market_ticker
            for state in states
            if state.simulation_state.remaining_quantity > 0
        }
        tickers.update(
            pending.market_ticker
            for state in states
            for pending in state.simulation_state.pending_settlements
        )
        return tuple(sorted(tickers))
    finally:
        store.close()


def run_live_shadow_settlement_closeout(
    *, run_id: str, store_path: str | Path, archive_root: str | Path,
    settlements_output: str | Path, receipt_output: str | Path, session,
    wait_seconds: float = 3600, poll_seconds: float = 10,
    monotonic_ns=time.monotonic_ns, sleep_seconds=time.sleep,
) -> LiveShadowSettlementCloseoutReceipt:
    if wait_seconds <= 0 or poll_seconds <= 0:
        raise LiveShadowSettlementCloseoutError("closeout timing must be positive")
    tickers = unresolved_shadow_market_tickers(store_path=store_path, run_id=run_id)
    if not tickers:
        receipt = LiveShadowSettlementCloseoutReceipt(run_id, "NO_OPEN_POSITIONS", ())
        write_live_shadow_settlement_closeout_receipt(output_path=receipt_output, receipt=receipt)
        return receipt
    publisher = LiveShadowSettlementPublisher(run_id=run_id, output_path=settlements_output)
    core = SoakSourceRuntimeCore(
        runtime_session_id=run_id + "-settlement-closeout", archive_root=archive_root,
        live_shadow_settlement_publisher=publisher, monotonic_ns=monotonic_ns,
    )
    core.queue_live_shadow_settlement_tickers(tickers)
    deadline_ns = int(monotonic_ns()) + int(wait_seconds * 1_000_000_000)
    try:
        while core.pending_live_shadow_settlement_tickers() and int(monotonic_ns()) < deadline_ns:
            for ticker in core.pending_live_shadow_settlement_tickers():
                try:
                    fetch_kalshi_final_market_settlement(
                        session=session, core=core, market_ticker=ticker,
                        monotonic_ns=monotonic_ns,
                    )
                except Exception:
                    pass
            if core.pending_live_shadow_settlement_tickers() and int(monotonic_ns()) < deadline_ns:
                sleep_seconds(poll_seconds)
        unresolved = core.pending_live_shadow_settlement_tickers()
    finally:
        core.close()
    receipt = LiveShadowSettlementCloseoutReceipt(
        run_id, "SETTLED" if not unresolved else "DEADLINE_EXPIRED", unresolved,
    )
    write_live_shadow_settlement_closeout_receipt(output_path=receipt_output, receipt=receipt)
    return receipt


def wait_for_terminal_soak_manifest(
    *, manifest_path: str | Path, run_id: str, wait_seconds: float,
    poll_seconds: float, monotonic_ns=time.monotonic_ns, sleep_seconds=time.sleep,
) -> bool:
    if wait_seconds <= 0 or poll_seconds <= 0:
        raise LiveShadowSettlementCloseoutError("manifest wait timing must be positive")
    deadline_ns = int(monotonic_ns()) + int(wait_seconds * 1_000_000_000)
    path = Path(manifest_path)
    while int(monotonic_ns()) < deadline_ns:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("run_id") == run_id:
            if payload.get("lifecycle_state") == "TERMINAL":
                return payload.get("measurement_complete") is True
        sleep_seconds(poll_seconds)
    return False

"""Checkpoint 21N-Z-B: read-only prospective Candidate-E live collector core.

This module contains deterministic book reconstruction, KXBTCD event selection,
Candidate-E live signal evaluation, Coinbase completed-minute validation, and
raw-first journal helpers. It contains no trading endpoint, order submission,
cancellation, portfolio mutation, or P&L accounting.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_raw_journal_security import (
    RawJournalSecurityError,
    sanitize_request_identity,
)

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel,
    BookState,
    PLANNED_QUANTITY,
    SIDE_ORDER,
    ZERO,
    account_synthetic_fill,
    best_yes_quote,
    candidate_e_probability,
    side_fair_probability,
    side_purchase_asks,
)
from .kxbtcd_candidate_e_july10_outcome_blind_binding import (
    parse_kxbtcd_threshold_ticker,
)
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    LadderMarket,
    MIN_DEPTH,
    spot_window,
)
from .kxbtcd_candidate_e_prospective_week_predeclaration import (
    validate_predeclaration,
)

KALSHI_REST_BASE = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_WS_URL = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
KALSHI_WS_PATH = "/trade-api/ws/v2"
COINBASE_EXCHANGE_BASE = "https://api.exchange.coinbase.com"
COINBASE_PRODUCT = "BTC-USD"
PRIMARY_THRESHOLD = Decimal("0.02")
DIAGNOSTIC_THRESHOLDS = tuple(Decimal(x) for x in ("0", "0.01", "0.03", "0.05"))
ENTRY_TTC_MIN = Decimal("2")
ENTRY_TTC_MAX = Decimal("55")
READ_ONLY_KALSHI_REST_PATH = "/markets"
READ_ONLY_WS_CHANNEL = "orderbook_delta"
ALLOWED_WS_COMMANDS = frozenset({"subscribe", "update_subscription"})
ALLOWED_UPDATE_ACTIONS = frozenset({"get_snapshot"})
EXPECTED_ZA_CHECKPOINT = "4b3d2b30790844537d229d51ad70d5a03d1d8b46"
EXPECTED_ZA_RECEIPT = "5a0889b507d6938ff058e2da164562ae7a6ccd97"

class ProspectiveLiveCollectorError(RuntimeError):
    pass


class CoinbaseCompletedCandleUnavailable(ProspectiveLiveCollectorError):
    """The just-closed Coinbase minute is not published yet."""

def fail(message: str) -> None:
    raise ProspectiveLiveCollectorError(message)

def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def parse_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        fail("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)

def epoch_ms(dt: datetime) -> int:
    return int(round(dt.timestamp() * 1000))

def git_commit_is_ancestor(
    repo_root: str | Path,
    ancestor_commit: str,
    descendant: str = "HEAD",
) -> bool:
    """Return whether a required closed checkpoint is in current Git ancestry.

    Return code 0 means ancestor, 1 means not ancestor. Any other Git failure
    is treated as an infrastructure error and fails closed.
    """
    ancestor = str(ancestor_commit).strip()
    descendant = str(descendant).strip()
    if not ancestor or not descendant:
        fail("git ancestry identifiers must be non-empty")
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=str(Path(repo_root).resolve()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ProspectiveLiveCollectorError(
            "unable to execute Git ancestry check"
        ) from exc

    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    fail(f"git ancestry check failed with return code {result.returncode}")
    raise AssertionError


def validate_frozen_contract(repo_root: str | Path = ".") -> Mapping[str, Any]:
    p = validate_predeclaration(repo_root)
    if p["prospective_primary_policy"]["primary_net_edge_threshold_dollars"] != "0.02":
        fail("prospective primary threshold changed")
    if p["prospective_primary_policy"]["max_reentries_per_event"] != 1:
        fail("prospective re-entry contract changed")
    if p["safety"]["real_money_orders_authorized"] is not False:
        fail("Z-B requires real-money execution to remain unauthorized")
    if p["safety"]["demo_orders_authorized"] is not False:
        fail("Z-B requires demo execution to remain unauthorized")
    return p

class RawJournal:
    """Append raw transport evidence before any transformation.

    Each line wraps the exact response/frame text plus receive timing. Secrets and
    request headers are never accepted by this class.
    """
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(
        self,
        *,
        source: str,
        transport: str,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[str, Any] | None = None,
    ) -> None:
        if source not in {"kalshi_production_rest", "kalshi_production_ws", "coinbase_exchange_rest"}:
            fail("unregistered raw journal source")
        try:
            safe_request_identity = sanitize_request_identity(request_identity)
        except RawJournalSecurityError as exc:
            raise ProspectiveLiveCollectorError(str(exc)) from exc
        record = {
            "schema_version": "prospective_raw_record.v1",
            "source": source,
            "transport": transport,
            "received_utc": received_utc,
            "received_monotonic_ns": int(received_monotonic_ns),
            "request_identity": safe_request_identity,
            "raw_text": str(raw_text),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())

@dataclass(frozen=True)
class EventLadder:
    event_ticker: str
    close_time_utc: str
    close_timestamp_ms: int
    markets: tuple[LadderMarket, ...]

@dataclass(frozen=True)
class CoinbaseMinuteClose:
    minute_start_s: int
    minute_end_s: int
    close_price: Decimal
    available_monotonic_ns: int
    raw_received_utc: str

@dataclass(frozen=True)
class LiveSignal:
    event_ticker: str
    market_ticker: str
    side: str
    decision_timestamp_ms: int
    decision_ttc_ms: int
    btc_spot: Decimal
    strike: Decimal
    q_market: Decimal
    candidate_probability: Decimal
    side_fair_probability: Decimal
    decision_yes_bid: Decimal
    decision_yes_ask: Decimal
    decision_limit_price: Decimal
    decision_level_quantity: Decimal
    entry_fee: Decimal
    net_edge: Decimal

def _decimal(value: Any, name: str) -> Decimal:
    try:
        x = Decimal(str(value))
    except Exception as exc:
        raise ProspectiveLiveCollectorError(f"{name} must be decimal-compatible") from exc
    if not x.is_finite():
        fail(f"{name} must be finite")
    return x

def _price(value: Any, name: str) -> Decimal:
    x = _decimal(value, name)
    if x < ZERO or x > Decimal("1"):
        fail(f"{name} outside [0,1]")
    return x

def _qty(value: Any, name: str) -> Decimal:
    x = _decimal(value, name)
    if x < ZERO:
        fail(f"{name} must be nonnegative")
    return x

def _levels(value: Any, name: str) -> dict[Decimal, Decimal]:
    if not isinstance(value, list):
        fail(f"{name} must be a list")
    out: dict[Decimal, Decimal] = {}
    for index, row in enumerate(value):
        if not isinstance(row, list) or len(row) != 2:
            fail(f"{name}[{index}] must be [price, quantity]")
        p = _price(row[0], f"{name}[{index}].price")
        q = _qty(row[1], f"{name}[{index}].quantity")
        if p in out:
            fail(f"duplicate price in {name}")
        if q > ZERO:
            out[p] = q
    return out

@dataclass
class LiveBook:
    ticker: str
    yes_bids: dict[Decimal, Decimal]
    no_bids: dict[Decimal, Decimal]
    generation: int
    valid: bool
    last_source_ts_ms: int | None = None

    def top_signature(self) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
        yb = max(self.yes_bids) if self.yes_bids else None
        nb = max(self.no_bids) if self.no_bids else None
        ya = None if nb is None else Decimal("1") - nb
        return (
            yb,
            None if yb is None else self.yes_bids[yb],
            ya,
            None if nb is None else self.no_bids[nb],
        )

    def to_book_state(self, timestamp_ms: int) -> BookState:
        if not self.valid:
            fail(f"book {self.ticker} is invalid")
        yes_bids = tuple(
            BookLevel(price=p, quantity=q)
            for p, q in sorted(self.yes_bids.items(), reverse=True)
            if q > ZERO
        )
        yes_asks = tuple(
            BookLevel(price=Decimal("1") - p, quantity=q)
            for p, q in sorted(self.no_bids.items(), reverse=True)
            if q > ZERO
        )
        yes_asks = tuple(sorted(yes_asks, key=lambda level: level.price))
        return BookState(
            timestamp_ms=int(timestamp_ms),
            yes_bids=yes_bids,
            yes_asks=yes_asks,
        )

class KalshiBookCache:
    """Reconstruct one authenticated orderbook_delta subscription fail-closed."""

    def __init__(self, subscribed_tickers: Sequence[str]):
        tickers = tuple(dict.fromkeys(str(x) for x in subscribed_tickers))
        if not tickers:
            fail("at least one subscribed ticker required")
        self.subscribed_tickers = tickers
        self.books: dict[str, LiveBook] = {}
        self.last_seq: int | None = None
        self.generation = 0
        self.resync_required = True
        self.subscription_sid: int | None = None
        self.sequence_gap_count = 0

    def _invalidate_all(self) -> None:
        self.generation += 1
        self.resync_required = True
        for book in self.books.values():
            book.valid = False

    def all_ready(self) -> bool:
        return (
            not self.resync_required
            and set(self.books) == set(self.subscribed_tickers)
            and all(
                book.valid and book.generation == self.generation
                for book in self.books.values()
            )
        )

    def _observe_seq(self, seq: int) -> bool:
        gap = self.last_seq is not None and seq != self.last_seq + 1
        if gap:
            self.sequence_gap_count += 1
            self._invalidate_all()
        self.last_seq = seq
        return gap

    def apply_message(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        msg_type = str(payload.get("type", ""))
        if msg_type == "subscribed":
            msg = payload.get("msg")
            if not isinstance(msg, Mapping) or msg.get("channel") != READ_ONLY_WS_CHANNEL:
                fail("unexpected subscribed response")
            sid = msg.get("sid")
            if not isinstance(sid, int):
                fail("subscription sid missing")
            self.subscription_sid = sid
            return {"type": msg_type, "top_changed": False, "gap": False, "ready": self.all_ready()}

        if msg_type not in {"orderbook_snapshot", "orderbook_delta"}:
            return {"type": msg_type, "top_changed": False, "gap": False, "ready": self.all_ready()}

        seq = payload.get("seq")
        if not isinstance(seq, int):
            fail(f"{msg_type} missing integer seq")
        gap = self._observe_seq(seq)
        msg = payload.get("msg")
        if not isinstance(msg, Mapping):
            fail(f"{msg_type}.msg must be object")
        ticker = str(msg.get("market_ticker", ""))
        if ticker not in self.subscribed_tickers:
            fail(f"message ticker outside subscription: {ticker}")

        prior_signature = self.books[ticker].top_signature() if ticker in self.books else None

        if msg_type == "orderbook_snapshot":
            # Kalshi's live snapshot schema allows an empty book side to be
            # omitted entirely. Normalize omission only to an empty side;
            # explicitly present null/wrong-type values still fail in _levels().
            yes_raw = msg["yes_dollars_fp"] if "yes_dollars_fp" in msg else []
            no_raw = msg["no_dollars_fp"] if "no_dollars_fp" in msg else []
            yes = _levels(yes_raw, "yes_dollars_fp")
            no = _levels(no_raw, "no_dollars_fp")
            self.books[ticker] = LiveBook(
                ticker=ticker,
                yes_bids=yes,
                no_bids=no,
                generation=self.generation,
                valid=True,
                last_source_ts_ms=None,
            )
            if (
                set(self.books) == set(self.subscribed_tickers)
                and all(
                    book.valid and book.generation == self.generation
                    for book in self.books.values()
                )
            ):
                self.resync_required = False
        else:
            book = self.books.get(ticker)
            if book is None or not book.valid or book.generation != self.generation:
                return {"type": msg_type, "ticker": ticker, "top_changed": False, "gap": gap, "ready": False}
            side = str(msg.get("side", "")).lower()
            if side not in {"yes", "no"}:
                fail("delta side must be yes/no")
            p = _price(msg.get("price_dollars"), "delta.price_dollars")
            delta = _decimal(msg.get("delta_fp"), "delta.delta_fp")
            levels = book.yes_bids if side == "yes" else book.no_bids
            new_qty = levels.get(p, ZERO) + delta
            if new_qty < ZERO:
                fail("delta would make level quantity negative")
            if new_qty == ZERO:
                levels.pop(p, None)
            else:
                levels[p] = new_qty
            ts_ms = msg.get("ts_ms")
            if ts_ms is not None:
                if not isinstance(ts_ms, int):
                    fail("delta ts_ms must be integer when present")
                book.last_source_ts_ms = ts_ms

        new_signature = self.books[ticker].top_signature()
        return {
            "type": msg_type,
            "ticker": ticker,
            "top_changed": prior_signature != new_signature,
            "gap": gap,
            "ready": self.all_ready(),
        }

def build_ladders_from_markets(payload: Mapping[str, Any]) -> tuple[EventLadder, ...]:
    markets = payload.get("markets")
    if not isinstance(markets, list):
        fail("markets response missing markets list")
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in markets:
        if not isinstance(row, Mapping):
            fail("market row must be object")
        ticker = str(row.get("ticker", ""))
        event = str(row.get("event_ticker", ""))
        if not ticker.startswith("KXBTCD-") or not event.startswith("KXBTCD-"):
            continue
        if str(row.get("status", "")).lower() != "active":
            continue
        parsed_event, parsed_strike = parse_kxbtcd_threshold_ticker(ticker)
        if parsed_event != event:
            fail(f"ticker/event mismatch for {ticker}")
        floor = row.get("floor_strike")
        if floor is not None and _decimal(floor, "floor_strike") != Decimal(str(parsed_strike)):
            fail(f"ticker/floor_strike mismatch for {ticker}")
        grouped.setdefault(event, []).append(row)

    ladders: list[EventLadder] = []
    for event, rows in grouped.items():
        close_values = {str(row.get("close_time", "")) for row in rows}
        if len(close_values) != 1 or "" in close_values:
            fail(f"event {event} has inconsistent close_time")
        close_text = next(iter(close_values))
        close_ms = epoch_ms(parse_utc(close_text))
        parsed = []
        for row in rows:
            ticker = str(row["ticker"])
            _, strike = parse_kxbtcd_threshold_ticker(ticker)
            parsed.append((Decimal(str(strike)), ticker))
        parsed.sort()
        if len({s for s, _ in parsed}) != len(parsed):
            fail(f"duplicate strikes in {event}")
        ladder_rows = tuple(
            LadderMarket(
                event_ticker=event,
                market_ticker=ticker,
                strike=strike,
                strike_rank_zero_based=rank,
                event_market_count=len(parsed),
                historical_structural_role=None,
            )
            for rank, (strike, ticker) in enumerate(parsed)
        )
        ladders.append(
            EventLadder(
                event_ticker=event,
                close_time_utc=close_text,
                close_timestamp_ms=close_ms,
                markets=ladder_rows,
            )
        )
    return tuple(sorted(ladders, key=lambda x: (x.close_timestamp_ms, x.event_ticker)))

def choose_smoke_ladder(ladders: Sequence[EventLadder], now_ms: int) -> EventLadder:
    future = [x for x in ladders if x.close_timestamp_ms > int(now_ms)]
    if not future:
        fail("no future/open KXBTCD event available")
    in_window = [
        x for x in future
        if ENTRY_TTC_MIN <= Decimal(x.close_timestamp_ms - now_ms) / Decimal(60000) <= ENTRY_TTC_MAX
    ]
    if in_window:
        return min(
            in_window,
            key=lambda x: (
                abs(Decimal(x.close_timestamp_ms - now_ms) / Decimal(60000) - Decimal("30")),
                x.close_timestamp_ms,
                x.event_ticker,
            ),
        )
    return min(future, key=lambda x: (x.close_timestamp_ms, x.event_ticker))

def completed_minute_target(decision_epoch_s: int) -> tuple[int, int]:
    boundary = (int(decision_epoch_s) // 60) * 60
    return boundary - 60, boundary

def parse_coinbase_completed_candle(
    payload: Any,
    *,
    target_start_s: int,
    available_monotonic_ns: int,
    raw_received_utc: str,
) -> CoinbaseMinuteClose:
    if not isinstance(payload, list):
        fail("Coinbase candle response must be a list")
    matches = []
    for row in payload:
        if not isinstance(row, list) or len(row) < 6:
            fail("Coinbase candle row must contain six fields")
        if int(row[0]) == int(target_start_s):
            matches.append(row)
    if len(matches) != 1:
        raise CoinbaseCompletedCandleUnavailable(
            "exact completed Coinbase minute candle unavailable"
        )
    row = matches[0]
    close = _decimal(row[4], "Coinbase candle close")
    if close <= ZERO:
        fail("Coinbase close must be positive")
    return CoinbaseMinuteClose(
        minute_start_s=int(target_start_s),
        minute_end_s=int(target_start_s) + 60,
        close_price=close,
        available_monotonic_ns=int(available_monotonic_ns),
        raw_received_utc=str(raw_received_utc),
    )

def _evaluate_market(
    *,
    event: EventLadder,
    market: LadderMarket,
    book: BookState,
    btc_spot: Decimal,
    decision_timestamp_ms: int,
) -> tuple[LiveSignal, ...]:
    bid, ask = best_yes_quote(book)
    q_market = (bid.price + ask.price) / Decimal("2")
    probability = candidate_e_probability(
        q_market=q_market,
        btc_spot=btc_spot,
        strike=market.strike,
    )
    ttc_ms = event.close_timestamp_ms - int(decision_timestamp_ms)
    signals = []
    for side in ("YES", "NO"):
        asks = side_purchase_asks(book, side)
        if not asks:
            continue
        best = asks[0]
        fee = account_synthetic_fill(
            action="BUY",
            price=best.price,
            quantity=PLANNED_QUANTITY,
            accumulator_before=ZERO,
        ).net_fee
        fair = side_fair_probability(side, probability)
        signals.append(
            LiveSignal(
                event_ticker=event.event_ticker,
                market_ticker=market.market_ticker,
                side=side,
                decision_timestamp_ms=int(decision_timestamp_ms),
                decision_ttc_ms=ttc_ms,
                btc_spot=btc_spot,
                strike=market.strike,
                q_market=q_market,
                candidate_probability=probability,
                side_fair_probability=fair,
                decision_yes_bid=bid.price,
                decision_yes_ask=ask.price,
                decision_limit_price=best.price,
                decision_level_quantity=best.quantity,
                entry_fee=fee,
                net_edge=fair - best.price - fee,
            )
        )
    return tuple(signals)

def select_live_signals(
    *,
    event: EventLadder,
    cache: KalshiBookCache,
    btc_state: CoinbaseMinuteClose,
    decision_timestamp_ms: int,
) -> dict[str, Any]:
    ttc_min = Decimal(event.close_timestamp_ms - int(decision_timestamp_ms)) / Decimal(60000)
    if not (ENTRY_TTC_MIN <= ttc_min <= ENTRY_TTC_MAX):
        return {
            "status": "OUTSIDE_ENTRY_WINDOW",
            "event_ticker": event.event_ticker,
            "decision_timestamp_ms": int(decision_timestamp_ms),
            "decision_ttc_ms": event.close_timestamp_ms - int(decision_timestamp_ms),
            "primary_signal": None,
            "diagnostic_signals": {},
        }
    if not cache.all_ready():
        return {
            "status": "KALSHI_BOOKS_NOT_EXACT",
            "event_ticker": event.event_ticker,
            "decision_timestamp_ms": int(decision_timestamp_ms),
            "decision_ttc_ms": event.close_timestamp_ms - int(decision_timestamp_ms),
            "primary_signal": None,
            "diagnostic_signals": {},
        }

    window = spot_window(
        event_ticker=event.event_ticker,
        btc_spot=btc_state.close_price,
        event_ladder=event.markets,
    )
    all_signals: list[LiveSignal] = []
    for market in window:
        live = cache.books.get(market.market_ticker)
        if live is None or not live.valid:
            return {
                "status": "CURRENT_ATM_WINDOW_BOOK_UNAVAILABLE",
                "event_ticker": event.event_ticker,
                "decision_timestamp_ms": int(decision_timestamp_ms),
                "decision_ttc_ms": event.close_timestamp_ms - int(decision_timestamp_ms),
                "primary_signal": None,
                "diagnostic_signals": {},
            }
        state = live.to_book_state(int(decision_timestamp_ms))
        try:
            all_signals.extend(
                _evaluate_market(
                    event=event,
                    market=market,
                    book=state,
                    btc_spot=btc_state.close_price,
                    decision_timestamp_ms=int(decision_timestamp_ms),
                )
            )
        except Exception as exc:
            # Invalid/crossed/two-sided book blocks the entire event selection.
            return {
                "status": "INVALID_CURRENT_ATM_WINDOW_BOOK",
                "event_ticker": event.event_ticker,
                "decision_timestamp_ms": int(decision_timestamp_ms),
                "decision_ttc_ms": event.close_timestamp_ms - int(decision_timestamp_ms),
                "primary_signal": None,
                "diagnostic_signals": {},
                "detail": type(exc).__name__,
            }

    eligible = [s for s in all_signals if s.decision_level_quantity >= MIN_DEPTH]
    eligible.sort(key=lambda s: (-s.net_edge, s.market_ticker, SIDE_ORDER[s.side]))

    def pick(threshold: Decimal) -> LiveSignal | None:
        return next((s for s in eligible if s.net_edge >= threshold), None)

    primary = pick(PRIMARY_THRESHOLD)
    diagnostics = {str(x): pick(x) for x in DIAGNOSTIC_THRESHOLDS}
    return {
        "status": "EVALUABLE",
        "event_ticker": event.event_ticker,
        "decision_timestamp_ms": int(decision_timestamp_ms),
        "decision_ttc_ms": event.close_timestamp_ms - int(decision_timestamp_ms),
        "btc_minute_start_s": btc_state.minute_start_s,
        "btc_minute_end_s": btc_state.minute_end_s,
        "btc_close": btc_state.close_price,
        "atm_window_tickers": [m.market_ticker for m in window],
        "primary_signal": primary,
        "diagnostic_signals": diagnostics,
    }

def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if hasattr(value, "__dataclass_fields__"):
        return {k: jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(x) for x in value]
    return value

def make_subscribe_command(tickers: Sequence[str]) -> dict[str, Any]:
    tickers = [str(x) for x in tickers]
    if not tickers:
        fail("subscribe requires tickers")
    return {
        "id": 1,
        "cmd": "subscribe",
        "params": {
            "channels": [READ_ONLY_WS_CHANNEL],
            "market_tickers": tickers,
        },
    }

def make_snapshot_command(sid: int, tickers: Sequence[str], command_id: int) -> dict[str, Any]:
    if not isinstance(sid, int):
        fail("snapshot command requires integer sid")
    tickers = [str(x) for x in tickers]
    if not tickers:
        fail("snapshot command requires tickers")
    command = {
        "id": int(command_id),
        "cmd": "update_subscription",
        "params": {
            "sid": sid,
            "market_tickers": tickers,
            "action": "get_snapshot",
        },
    }
    assert_read_only_ws_command(command)
    return command

def assert_read_only_ws_command(command: Mapping[str, Any]) -> None:
    cmd = command.get("cmd")
    if cmd not in ALLOWED_WS_COMMANDS:
        fail("WebSocket command outside read-only allowlist")
    params = command.get("params")
    if not isinstance(params, Mapping):
        fail("WebSocket command params required")
    channels = params.get("channels")
    if channels is not None and channels != [READ_ONLY_WS_CHANNEL]:
        fail("only orderbook_delta channel is authorized")
    action = params.get("action")
    if action is not None and action not in ALLOWED_UPDATE_ACTIONS:
        fail("update_subscription action outside get_snapshot allowlist")

def read_env_file(repo_root: str | Path = ".") -> None:
    path = Path(repo_root) / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def kalshi_production_credentials(repo_root: str | Path = ".") -> tuple[str, Path]:
    read_env_file(repo_root)
    environment = os.environ.get("KALSHI_ENVIRONMENT", "").strip().lower()
    if environment not in {"production", "prod"}:
        fail("KALSHI_ENVIRONMENT must explicitly be production/prod for Z-B read-only production WebSocket")
    key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
    key_path_text = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()
    if not key_id or not key_path_text:
        fail("Kalshi key ID/private-key path are not configured in environment/.env")
    key_path = Path(key_path_text).expanduser()
    if not key_path.is_absolute():
        key_path = (Path(repo_root) / key_path).resolve()
    if not key_path.is_file():
        fail("configured Kalshi private-key file does not exist")
    return key_id, key_path

def create_kalshi_ws_headers(key_id: str, private_key_path: Path) -> dict[str, str]:
    try:
        import base64
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise ProspectiveLiveCollectorError(
            "cryptography dependency missing; install requirements.txt"
        ) from exc
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}GET{KALSHI_WS_PATH}".encode("utf-8")
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(),
        password=None,
    )
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }

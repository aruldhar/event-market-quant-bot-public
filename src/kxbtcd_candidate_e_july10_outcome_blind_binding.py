"""Checkpoint 21N-S-A: outcome-blind July 10 real-data binding layer.

This module binds the already-owned July 10, 2026 KXBTCD evidence to the
frozen Candidate-E executable convergence/liquidation simulator.  It is
intentionally settlement-blind: there is no outcome reader and no realized
P&L calculation in this module.

The materializer is designed to run only after this implementation has been
frozen/committed.  Its output is methodology/debug evidence from four
independent events; it is not a strategy-validation result.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    ANCHOR_ORDER,
    LATENCY_MS,
    STRUCTURAL_ROLES,
    THRESHOLDS,
    ExecutableConvergenceSimulatorError,
    SignalCandidate,
    VerifiedTickerTimeline,
    best_yes_quote,
    build_signal_candidates,
    build_verified_ticker_timeline,
    select_event_signal,
    select_structural_markets,
    simulate_scenario,
    validate_frozen_parents,
)
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_freeze import (
    validate_freeze as validate_simulator_implementation_freeze,
)
from .predexon_full_ladder_replay import load_backfill_snapshots


SCHEMA_VERSION = "kxbtcd_candidate_e_july10_outcome_blind_binding.v1"
CHECKPOINT_ID = "21N-S"
STRATEGY_ID = "kxbtcd_candidate_e_executable_convergence_liquidation_v1"
IMPLEMENTATION_FINGERPRINT_21N_R = (
    "6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf"
)

BTC_RELATIVE_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_btc_materialization.json"
)
PAID_TICKS_RELATIVE_PATH = Path(
    "data/raw/predexon_ticks/2026/07/10/"
    "kalshi_orderbook_deltas_2026-07-10_part00017_raw.zstd.parquet"
)
REPLAY_SUMMARY_RELATIVE_PATH = Path(
    "data/analysis/predexon_full_ladder_replay/summary.json"
)
REPLAY_TICKER_ROOT_RELATIVE_PATH = Path(
    "data/analysis/predexon_full_ladder_replay/tickers"
)
BACKFILL_ROOT_RELATIVE_PATH = Path(
    "data/raw/predexon_orderbook_subcent_backfill/2026/07/10"
)
R_FREEZE_RELATIVE_PATH = Path(
    "configs/"
    "kxbtcd_candidate_e_executable_convergence_liquidation_v1_"
    "simulator_implementation_freeze.json"
)
DEFAULT_OUTPUT_RELATIVE_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_executable_convergence_liquidation_v1_"
    "outcome_blind_paths.json"
)

EXPECTED_BTC_SHA256 = "022f6c6ce1b697bc67f7137f73e3f18cc0fe0198b347e5154a3063107299fb12"
EXPECTED_PAID_TICKS_SHA256 = "43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509"
EXPECTED_REPLAY_SUMMARY_SHA256 = "b37ba7132baf086887e4b33e7c11e9de59decc5f0b387d7e6e5352a2570ebb48"
EXPECTED_R_IMPLEMENTATION_FINGERPRINT = IMPLEMENTATION_FINGERPRINT_21N_R

EXPECTED_EVENT_MARKET_COUNTS = {
    "KXBTCD-26JUL1013": 78,
    "KXBTCD-26JUL1014": 188,
    "KXBTCD-26JUL1015": 188,
    "KXBTCD-26JUL1016": 169,
}
EXPECTED_EVENT_COUNT = 4
EXPECTED_TICKER_COUNT = 623
EXPECTED_BTC_ANCHOR_COUNT = 24
EXPECTED_STRUCTURAL_TICKER_COUNT = 20
EXPECTED_ROLE_ANCHOR_STATE_COUNT = 120
EXPECTED_PAID_DELTA_COUNT = 5_644_964
EXPECTED_SNAPSHOT_COUNT = 269_441
EXPECTED_PAIR_COUNT = 268_818
EXPECTED_EXACT_PAIR_COUNT = 266_034
EXPECTED_UNRECONCILED_PAIR_COUNT = 2_784

PAID_COLUMNS = (
    "ticker",
    "timestamp",
    "price_dollars",
    "delta_fp",
    "side",
    "sequence",
)

# Exact dangerous output labels.  Settlement-fallback *quantity* is permitted:
# it is an open-position quantity, not a settlement outcome/value.
FORBIDDEN_OUTPUT_KEYS = {
    "outcome",
    "outcomes",
    "label",
    "winner",
    "settlement_value",
    "settlement_outcome",
    "yes_settlement_value",
    "no_settlement_value",
    "pnl",
    "realized_pnl",
    "profit",
    "loss",
}


class OutcomeBlindBindingError(RuntimeError):
    """Raised when a frozen source/input invariant fails closed."""


def _fail(message: str) -> None:
    raise OutcomeBlindBindingError(message)


def _d(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OutcomeBlindBindingError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _fail(f"{name} must be finite")
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def iso_utc_to_epoch_ms(text: str) -> int:
    raw = str(text).strip()
    if not raw:
        _fail("UTC timestamp must be non-empty")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutcomeBlindBindingError(f"invalid ISO timestamp: {raw}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        _fail(f"timestamp must be explicit UTC: {raw}")
    dt = dt.astimezone(timezone.utc)
    if dt.microsecond % 1000:
        _fail(f"timestamp is not millisecond aligned: {raw}")
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = dt - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def parse_kxbtcd_threshold_ticker(ticker: str) -> tuple[str, Decimal]:
    raw = str(ticker).strip()
    if "-T" not in raw:
        _fail(f"ticker missing -T threshold separator: {raw}")
    event_ticker, strike_text = raw.rsplit("-T", 1)
    if not event_ticker.startswith("KXBTCD-") or not strike_text:
        _fail(f"unexpected KXBTCD threshold ticker: {raw}")
    strike = _d(strike_text, "strike")
    if strike <= 0:
        _fail(f"strike must be positive: {raw}")
    return event_ticker, strike


def _require_hash(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        _fail(f"{label} missing: {path}")
    observed = sha256_file(path)
    if observed.lower() != expected.lower():
        _fail(f"{label} SHA256 mismatch: expected {expected}, observed {observed}")
    return observed


def _require_false(payload: Mapping[str, Any], key: str, label: str) -> None:
    if payload.get(key) is not False:
        _fail(f"{label}.{key} must be false")


def _require_zero(payload: Mapping[str, Any], key: str, label: str) -> None:
    if payload.get(key) != 0:
        _fail(f"{label}.{key} must be 0")


def validate_21n_r_freeze(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)
    path = repo / R_FREEZE_RELATIVE_PATH
    if not path.is_file():
        _fail(f"21N-R implementation freeze missing: {path}")
    try:
        payload = validate_simulator_implementation_freeze(repo)
    except Exception as exc:
        raise OutcomeBlindBindingError(f"21N-R implementation freeze validation failed: {exc}") from exc
    if payload.get("implementation_fingerprint") != EXPECTED_R_IMPLEMENTATION_FINGERPRINT:
        _fail("21N-R implementation fingerprint mismatch")
    evidence = payload.get("evidence_and_safety")
    if not isinstance(evidence, Mapping):
        _fail("21N-R evidence_and_safety missing")
    if evidence.get("july10_outcomes_accessed_by_implementation") is not False:
        _fail("21N-R outcome firewall is not closed")
    if evidence.get("strategy_pnl_calculated_by_implementation") is not False:
        _fail("21N-R P&L firewall is not closed")
    return payload


def load_and_validate_btc_materialization(repo_root: str | Path = ".") -> tuple[Mapping[str, Any], ...]:
    repo = Path(repo_root)
    path = repo / BTC_RELATIVE_PATH
    _require_hash(path, EXPECTED_BTC_SHA256, "July10 BTC materialization")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        _fail("BTC materialization must be an object")
    if payload.get("event_count") != EXPECTED_EVENT_COUNT:
        _fail("BTC materialization event_count mismatch")
    if payload.get("decision_anchor_count") != EXPECTED_BTC_ANCHOR_COUNT:
        _fail("BTC materialization decision_anchor_count mismatch")
    if payload.get("source_eligible_anchor_count") != EXPECTED_BTC_ANCHOR_COUNT:
        _fail("all 24 BTC decision anchors must remain source eligible")
    if payload.get("source_ineligible_anchor_count") != 0:
        _fail("BTC materialization unexpectedly contains ineligible anchors")
    _require_false(payload, "candidate_e_refit", "BTC materialization")
    _require_false(payload, "outcomes_accessed", "BTC materialization")
    _require_false(payload, "strategy_pnl_calculated", "BTC materialization")
    _require_zero(payload, "orders_placed", "BTC materialization")

    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_BTC_ANCHOR_COUNT:
        _fail("BTC materialization rows must contain exactly 24 anchors")

    expected_row_keys = {
        "coinbase_current_price",
        "coinbase_lookback_price",
        "current_disagreement_bps",
        "current_minute_end_utc",
        "current_minute_start_utc",
        "decision_time_utc",
        "event_close_time_utc",
        "event_ticker",
        "kraken_current_price",
        "kraken_current_publication_ts",
        "kraken_lookback_price",
        "kraken_lookback_publication_ts",
        "lookback_disagreement_bps",
        "lookback_minute_end_utc",
        "lookback_minute_start_utc",
        "source_eligible",
        "ttc_target_minutes",
    }
    normalized: list[Mapping[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    anchors_by_event: dict[str, set[int]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(f"BTC row {i} must be an object")
        if set(row) != expected_row_keys:
            _fail(f"BTC row {i} schema mismatch")
        event = str(row["event_ticker"])
        ttc = int(row["ttc_target_minutes"])
        if event not in EXPECTED_EVENT_MARKET_COUNTS:
            _fail(f"unexpected BTC event: {event}")
        if ttc not in ANCHOR_ORDER:
            _fail(f"unexpected BTC TTC anchor: {ttc}")
        key = (event, ttc)
        if key in seen:
            _fail(f"duplicate BTC anchor: {key}")
        seen.add(key)
        anchors_by_event.setdefault(event, set()).add(ttc)
        if row["source_eligible"] is not True:
            _fail(f"BTC source ineligible at {event}/{ttc}")

        decision_ms = iso_utc_to_epoch_ms(str(row["decision_time_utc"]))
        close_ms = iso_utc_to_epoch_ms(str(row["event_close_time_utc"]))
        if close_ms - decision_ms != ttc * 60_000:
            _fail(f"decision/close TTC mismatch at {event}/{ttc}")
        if _d(row["coinbase_current_price"], "coinbase_current_price") <= 0:
            _fail("Coinbase current price must be positive")
        normalized.append(row)

    if set(anchors_by_event) != set(EXPECTED_EVENT_MARKET_COUNTS):
        _fail("BTC event set mismatch")
    for event, anchors in anchors_by_event.items():
        if anchors != set(ANCHOR_ORDER):
            _fail(f"BTC anchor set mismatch for {event}")
    return tuple(normalized)


def load_and_validate_replay_summary(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)
    path = repo / REPLAY_SUMMARY_RELATIVE_PATH
    _require_hash(path, EXPECTED_REPLAY_SUMMARY_SHA256, "full-ladder replay summary")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        _fail("replay summary must be an object")
    exact_expectations = {
        "independent_event_count": EXPECTED_EVENT_COUNT,
        "ticker_count": EXPECTED_TICKER_COUNT,
        "paid_delta_count_processed": EXPECTED_PAID_DELTA_COUNT,
        "snapshot_count": EXPECTED_SNAPSHOT_COUNT,
        "pair_count": EXPECTED_PAIR_COUNT,
        "exact_pair_count": EXPECTED_EXACT_PAIR_COUNT,
        "unreconciled_pair_count": EXPECTED_UNRECONCILED_PAIR_COUNT,
    }
    for key, expected in exact_expectations.items():
        if payload.get(key) != expected:
            _fail(f"replay summary {key} mismatch")
    _require_false(payload, "candidate_e_scored", "replay summary")
    _require_false(payload, "outcomes_accessed", "replay summary")
    _require_false(payload, "strategy_pnl_calculated", "replay summary")
    _require_zero(payload, "network_requests", "replay summary")
    _require_zero(payload, "orders_placed", "replay summary")
    _require_zero(payload, "predexon_paid_purchases", "replay summary")

    by_event = payload.get("by_event")
    if not isinstance(by_event, Mapping) or set(by_event) != set(EXPECTED_EVENT_MARKET_COUNTS):
        _fail("replay summary event set mismatch")
    for event, expected_count in EXPECTED_EVENT_MARKET_COUNTS.items():
        event_payload = by_event[event]
        if not isinstance(event_payload, Mapping) or event_payload.get("ticker_count") != expected_count:
            _fail(f"replay ticker_count mismatch for {event}")
    summaries = payload.get("ticker_summaries")
    if not isinstance(summaries, list) or len(summaries) != EXPECTED_TICKER_COUNT:
        _fail("replay ticker_summaries count mismatch")
    return payload


def collect_paid_tickers(parquet_path: Path) -> tuple[str, ...]:
    if not parquet_path.is_file():
        _fail(f"paid tick parquet missing: {parquet_path}")
    parquet = pq.ParquetFile(parquet_path)
    if parquet.metadata.num_rows != EXPECTED_PAID_DELTA_COUNT:
        _fail("paid tick parquet row count mismatch")
    names = set(parquet.schema.names)
    if not set(PAID_COLUMNS).issubset(names):
        _fail("paid tick parquet schema missing required columns")
    unique: set[str] = set()
    for batch in parquet.iter_batches(batch_size=262_144, columns=["ticker"]):
        for value in pc.unique(batch.column(0)).to_pylist():
            unique.add(str(value))
    if len(unique) != EXPECTED_TICKER_COUNT:
        _fail(f"paid ticker count mismatch: {len(unique)}")
    return tuple(sorted(unique))


def derive_structural_universe(paid_tickers: Sequence[str]) -> tuple[Mapping[str, Any], ...]:
    by_event: dict[str, list[tuple[str, Decimal]]] = {}
    for ticker in paid_tickers:
        event, strike = parse_kxbtcd_threshold_ticker(ticker)
        by_event.setdefault(event, []).append((ticker, strike))
    if set(by_event) != set(EXPECTED_EVENT_MARKET_COUNTS):
        _fail("paid ticker event set mismatch")

    output: list[Mapping[str, Any]] = []
    for event in sorted(by_event):
        markets = by_event[event]
        if len(markets) != EXPECTED_EVENT_MARKET_COUNTS[event]:
            _fail(f"full-ladder market count mismatch for {event}")
        selected = select_structural_markets(markets)
        if tuple(m.structural_role for m in selected) != STRUCTURAL_ROLES:
            _fail(f"structural role order mismatch for {event}")
        for market in selected:
            output.append(
                {
                    "event_ticker": event,
                    "market_ticker": market.market_ticker,
                    "strike": market.strike,
                    "structural_role": market.structural_role,
                    "structural_quantile": market.structural_quantile,
                    "strike_rank_zero_based": market.strike_rank_zero_based,
                    "event_market_count": market.event_market_count,
                }
            )
    if len(output) != EXPECTED_STRUCTURAL_TICKER_COUNT:
        _fail("structural ticker count must equal 20")
    if len({row["market_ticker"] for row in output}) != EXPECTED_STRUCTURAL_TICKER_COUNT:
        _fail("structural ticker selection contains duplicates")
    return tuple(output)


def validate_file_set_alignment(
    *,
    repo_root: str | Path,
    paid_tickers: Sequence[str],
) -> None:
    repo = Path(repo_root)
    replay_root = repo / REPLAY_TICKER_ROOT_RELATIVE_PATH
    backfill_root = repo / BACKFILL_ROOT_RELATIVE_PATH
    if not replay_root.is_dir():
        _fail(f"replay ticker directory missing: {replay_root}")
    if not backfill_root.is_dir():
        _fail(f"backfill directory missing: {backfill_root}")
    replay = {p.stem for p in replay_root.glob("*.json")}
    backfill = {
        p.name.removesuffix("_raw_pages.jsonl")
        for p in backfill_root.glob("*_raw_pages.jsonl")
    }
    paid = set(paid_tickers)
    if len(replay) != EXPECTED_TICKER_COUNT or len(backfill) != EXPECTED_TICKER_COUNT:
        _fail("replay/backfill file counts must both equal 623")
    if replay != paid or backfill != paid:
        _fail("paid/replay/backfill ticker sets are not identical")


def load_selected_paid_rows(
    parquet_path: Path,
    selected_tickers: Sequence[str],
) -> dict[str, list[Mapping[str, Any]]]:
    selected = tuple(sorted(set(str(x) for x in selected_tickers)))
    if len(selected) != EXPECTED_STRUCTURAL_TICKER_COUNT:
        _fail("exactly 20 structural tickers must be loaded")
    output: dict[str, list[Mapping[str, Any]]] = {ticker: [] for ticker in selected}
    value_set = pa.array(selected, type=pa.string())
    parquet = pq.ParquetFile(parquet_path)
    for batch in parquet.iter_batches(batch_size=131_072, columns=list(PAID_COLUMNS)):
        ticker_column = batch.column(batch.schema.get_field_index("ticker"))
        mask = pc.is_in(ticker_column, value_set=value_set)
        if not pc.any(mask).as_py():
            continue
        filtered = batch.filter(mask)
        for row in filtered.to_pylist():
            ticker = str(row["ticker"])
            if ticker in output:
                output[ticker].append(row)
    for ticker, rows in output.items():
        if not rows:
            _fail(f"zero paid deltas for structural ticker {ticker}")
        rows.sort(key=lambda r: (int(r["timestamp"]), int(r["sequence"])))
    return output


def _validate_replay_ticker_artifact(
    *,
    path: Path,
    ticker: str,
    timeline: VerifiedTickerTimeline,
) -> Mapping[str, Any]:
    if not path.is_file():
        _fail(f"per-ticker replay artifact missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        _fail(f"per-ticker replay artifact must be object: {ticker}")
    if payload.get("ticker") != ticker:
        _fail(f"per-ticker replay ticker mismatch: {ticker}")
    _require_false(payload, "candidate_e_scored", ticker)
    _require_false(payload, "outcomes_accessed", ticker)
    _require_false(payload, "strategy_pnl_calculated", ticker)
    _require_zero(payload, "network_requests", ticker)
    _require_zero(payload, "orders_placed", ticker)
    segments = payload.get("segments")
    if not isinstance(segments, list):
        _fail(f"replay segments missing: {ticker}")
    frozen_bounds = [
        (int(s["start_timestamp"]), int(s["end_timestamp"]))
        for s in segments
    ]
    runtime_bounds = [
        (s.start_timestamp_ms, s.end_timestamp_ms)
        for s in timeline.segments
    ]
    if runtime_bounds != frozen_bounds:
        _fail(f"runtime replay segment boundaries differ from frozen audit: {ticker}")
    return payload


def build_structural_timelines(
    *,
    repo_root: str | Path,
    structural_rows: Sequence[Mapping[str, Any]],
    paid_rows_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, VerifiedTickerTimeline]:
    repo = Path(repo_root)
    output: dict[str, VerifiedTickerTimeline] = {}
    for row in structural_rows:
        ticker = str(row["market_ticker"])
        backfill_path = repo / BACKFILL_ROOT_RELATIVE_PATH / f"{ticker}_raw_pages.jsonl"
        snapshots = load_backfill_snapshots(backfill_path, ticker=ticker)
        timeline = build_verified_ticker_timeline(
            ticker=ticker,
            snapshots=snapshots,
            paid_rows=paid_rows_by_ticker[ticker],
        )
        replay_path = repo / REPLAY_TICKER_ROOT_RELATIVE_PATH / f"{ticker}.json"
        _validate_replay_ticker_artifact(path=replay_path, ticker=ticker, timeline=timeline)
        output[ticker] = timeline
    if set(output) != {str(row["market_ticker"]) for row in structural_rows}:
        _fail("structural timeline set mismatch")
    return output


def _safe_signal_candidates(
    *,
    event_ticker: str,
    market_ticker: str,
    structural_role: str,
    ttc_target_minutes: int,
    decision_timestamp_ms: int,
    btc_spot: Decimal,
    strike: Decimal,
    timeline: VerifiedTickerTimeline,
) -> tuple[str, tuple[SignalCandidate, ...]]:
    segment = timeline.unique_segment_for_interval(decision_timestamp_ms, decision_timestamp_ms)
    if segment is None:
        return "SOURCE_UNAVAILABLE_DECISION_TIMESTAMP", ()
    state = segment.state_at(decision_timestamp_ms)
    try:
        best_yes_quote(state)
    except ExecutableConvergenceSimulatorError as exc:
        message = str(exc)
        if message in {"two-sided YES book required", "crossed YES book"}:
            return "INVALID_TWO_SIDED_BOOK", ()
        raise
    candidates = build_signal_candidates(
        event_ticker=event_ticker,
        market_ticker=market_ticker,
        structural_role=structural_role,
        ttc_target_minutes=ttc_target_minutes,
        decision_timestamp_ms=decision_timestamp_ms,
        btc_spot=btc_spot,
        strike=strike,
        timeline=timeline,
    )
    if not candidates:
        return "NO_SIDE_WITH_FULL_DECISION_LEVEL_DEPTH", ()
    return "SIGNAL_CANDIDATES_AVAILABLE", candidates


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".") or "0"
        return text
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    return value


def _find_forbidden_keys(value: Any, found: set[str] | None = None) -> set[str]:
    found = found if found is not None else set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_OUTPUT_KEYS:
                found.add(lowered)
            _find_forbidden_keys(child, found)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _find_forbidden_keys(child, found)
    return found


def _materialization_firewall(payload: Mapping[str, Any]) -> None:
    forbidden = _find_forbidden_keys(payload)
    if forbidden:
        _fail(f"forbidden outcome/P&L keys escaped materializer: {sorted(forbidden)}")
    safety = payload.get("safety")
    if not isinstance(safety, Mapping):
        _fail("materialization safety block missing")
    required = {
        "outcomes_accessed": False,
        "strategy_pnl_calculated": False,
        "candidate_e_refit": False,
        "network_requests": 0,
        "predexon_paid_purchases": 0,
        "orders_placed": 0,
        "paper_broker": False,
        "demo_execution": False,
        "real_money_execution": False,
    }
    for key, expected in required.items():
        if safety.get(key) != expected:
            _fail(f"materialization safety invariant failed: {key}")


def materialize_outcome_blind_binding(repo_root: str | Path = ".") -> Mapping[str, Any]:
    """Bind July 10 inputs and simulate settlement-blind execution paths.

    This function intentionally has no parameter for outcomes/labels.  It reads
    only frozen BTC state, paid order-book deltas, free snapshot backfill, and
    frozen replay audit artifacts.
    """
    repo = Path(repo_root)
    parent_fingerprints = validate_frozen_parents(repo)
    validate_21n_r_freeze(repo)

    btc_rows = load_and_validate_btc_materialization(repo)
    replay_summary = load_and_validate_replay_summary(repo)
    paid_path = repo / PAID_TICKS_RELATIVE_PATH
    paid_sha = _require_hash(paid_path, EXPECTED_PAID_TICKS_SHA256, "paid Predexon tick shard")
    paid_tickers = collect_paid_tickers(paid_path)
    validate_file_set_alignment(repo_root=repo, paid_tickers=paid_tickers)
    structural = derive_structural_universe(paid_tickers)
    selected_tickers = [str(row["market_ticker"]) for row in structural]
    paid_rows = load_selected_paid_rows(paid_path, selected_tickers)
    timelines = build_structural_timelines(
        repo_root=repo,
        structural_rows=structural,
        paid_rows_by_ticker=paid_rows,
    )

    structural_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in structural:
        structural_by_event.setdefault(str(row["event_ticker"]), []).append(row)

    candidate_objects_by_event: dict[str, list[SignalCandidate]] = {
        event: [] for event in EXPECTED_EVENT_MARKET_COUNTS
    }
    decision_states: list[Mapping[str, Any]] = []
    for btc in sorted(
        btc_rows,
        key=lambda row: (
            str(row["event_ticker"]),
            ANCHOR_ORDER.index(int(row["ttc_target_minutes"])),
        ),
    ):
        event = str(btc["event_ticker"])
        ttc = int(btc["ttc_target_minutes"])
        decision_ms = iso_utc_to_epoch_ms(str(btc["decision_time_utc"]))
        btc_spot = _d(btc["coinbase_current_price"], "coinbase_current_price")
        for market in structural_by_event[event]:
            ticker = str(market["market_ticker"])
            status, candidates = _safe_signal_candidates(
                event_ticker=event,
                market_ticker=ticker,
                structural_role=str(market["structural_role"]),
                ttc_target_minutes=ttc,
                decision_timestamp_ms=decision_ms,
                btc_spot=btc_spot,
                strike=_d(market["strike"], "strike"),
                timeline=timelines[ticker],
            )
            candidate_objects_by_event[event].extend(candidates)
            decision_states.append(
                {
                    "event_ticker": event,
                    "ttc_target_minutes": ttc,
                    "decision_timestamp_ms": decision_ms,
                    "market_ticker": ticker,
                    "structural_role": market["structural_role"],
                    "strike": market["strike"],
                    "btc_spot_coinbase": btc_spot,
                    "status": status,
                    "signal_candidates": candidates,
                }
            )
    if len(decision_states) != EXPECTED_ROLE_ANCHOR_STATE_COUNT:
        _fail("role-anchor decision-state count must equal 120")

    btc_by_event = {str(row["event_ticker"]): row for row in btc_rows if int(row["ttc_target_minutes"]) == 55}
    if set(btc_by_event) != set(EXPECTED_EVENT_MARKET_COUNTS):
        _fail("could not resolve one event-close timestamp per event")

    selections: list[Mapping[str, Any]] = []
    scenarios: list[Mapping[str, Any]] = []
    for event in sorted(EXPECTED_EVENT_MARKET_COUNTS):
        event_candidates = candidate_objects_by_event[event]
        close_ms = iso_utc_to_epoch_ms(str(btc_by_event[event]["event_close_time_utc"]))
        for threshold in THRESHOLDS:
            selected = select_event_signal(event_candidates, threshold=threshold)
            selections.append(
                {
                    "event_ticker": event,
                    "threshold_dollars": threshold,
                    "selected_signal": selected,
                }
            )
            if selected is None:
                continue
            timeline = timelines[selected.market_ticker]
            for latency_ms in LATENCY_MS:
                scenario = simulate_scenario(
                    signal=selected,
                    timeline=timeline,
                    latency_ms=latency_ms,
                    event_close_timestamp_ms=close_ms,
                )
                scenarios.append(
                    {
                        "event_ticker": event,
                        "threshold_dollars": threshold,
                        "latency_ms": latency_ms,
                        "scenario": scenario,
                    }
                )

    structural_serialized = _jsonable(structural)
    payload: Mapping[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "strategy_id": STRATEGY_ID,
        "evidence_role": "four_event_july10_exploratory_methodology_debug_only",
        "advancement_gate": "NONE_N_EQ_4",
        "frozen_parents": {
            **parent_fingerprints,
            "simulator_implementation_fingerprint_21n_r": EXPECTED_R_IMPLEMENTATION_FINGERPRINT,
        },
        "source_hashes": {
            "btc_materialization_sha256": EXPECTED_BTC_SHA256,
            "paid_predexon_tick_shard_sha256": paid_sha,
            "full_ladder_replay_summary_sha256": EXPECTED_REPLAY_SUMMARY_SHA256,
        },
        "source_counts": {
            "event_count": EXPECTED_EVENT_COUNT,
            "full_ladder_ticker_count": EXPECTED_TICKER_COUNT,
            "structural_ticker_count": EXPECTED_STRUCTURAL_TICKER_COUNT,
            "btc_anchor_count": EXPECTED_BTC_ANCHOR_COUNT,
            "role_anchor_state_count": EXPECTED_ROLE_ANCHOR_STATE_COUNT,
            "paid_delta_count": EXPECTED_PAID_DELTA_COUNT,
            "snapshot_count": int(replay_summary["snapshot_count"]),
            "pair_count": int(replay_summary["pair_count"]),
            "exact_pair_count": int(replay_summary["exact_pair_count"]),
            "unreconciled_pair_count": int(replay_summary["unreconciled_pair_count"]),
        },
        "structural_markets": structural_serialized,
        "decision_states": _jsonable(decision_states),
        "threshold_selections": _jsonable(selections),
        "execution_scenarios": _jsonable(scenarios),
        "execution_model_assumptions": {
            "same_millisecond_state": "right_continuous_final_reconstructed_state_per_millisecond",
            "same_millisecond_transients_exposed": False,
            "future_book_after_counterfactual_ioc": "historical_path_exogenous_small_order_nonimpacting_assumption",
            "future_book_impact_claimed_observed": False,
            "aggregate_level_fill_partition": "one_synthetic_fill_per_consumed_price_level",
            "queue_priority_claimed": False,
        },
        "safety": {
            "outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "candidate_e_refit": False,
            "model2_used": False,
            "network_requests": 0,
            "predexon_paid_purchases": 0,
            "orders_placed": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
            "protected_reserve_accessed": False,
        },
    }
    _materialization_firewall(payload)
    return payload


def materialize_to_path(
    *,
    repo_root: str | Path = ".",
    output_path: str | Path | None = None,
) -> tuple[Path, str, Mapping[str, Any]]:
    repo = Path(repo_root)
    payload = materialize_outcome_blind_binding(repo)
    if output_path is None:
        output = repo / DEFAULT_OUTPUT_RELATIVE_PATH
    else:
        output = Path(output_path)
        if not output.is_absolute():
            output = repo / output
    raw = canonical_json_bytes(payload)
    if output.exists():
        previous = output.read_bytes()
        if previous != raw:
            _fail(
                f"refusing to overwrite non-identical existing materialization: {output}"
            )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return output, digest, payload


__all__ = [
    "OutcomeBlindBindingError",
    "SCHEMA_VERSION",
    "EXPECTED_BTC_SHA256",
    "EXPECTED_PAID_TICKS_SHA256",
    "EXPECTED_REPLAY_SUMMARY_SHA256",
    "DEFAULT_OUTPUT_RELATIVE_PATH",
    "sha256_file",
    "canonical_json_bytes",
    "iso_utc_to_epoch_ms",
    "parse_kxbtcd_threshold_ticker",
    "validate_21n_r_freeze",
    "load_and_validate_btc_materialization",
    "load_and_validate_replay_summary",
    "collect_paid_tickers",
    "derive_structural_universe",
    "validate_file_set_alignment",
    "load_selected_paid_rows",
    "build_structural_timelines",
    "materialize_outcome_blind_binding",
    "materialize_to_path",
]

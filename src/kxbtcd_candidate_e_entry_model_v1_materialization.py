"""Outcome-blind deterministic materialization for Candidate-E Entry Model v1.

The materializer joins already-frozen Candidate-E decision states/probabilities
with the read-only execution archive.  It intentionally projects prediction
sources onto identity + probability fields before feature construction; source
outcomes are not copied into, consulted by, or emitted from feature rows.

Only H1_OOF, H2, and H3 development evidence is accepted here.  C1/C2/C3 and
any protected-reserve source are outside this module's authorized stage set.
"""
from __future__ import annotations

from bisect import bisect_right
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_entry_model_v1 import (
    CANDIDATE_E_ID,
    DEVELOPMENT_STAGES,
    EXPECTED_DEVELOPMENT_EVENT_COUNTS,
    EXPECTED_DEVELOPMENT_ROW_COUNTS,
    MODEL_ID,
    ROW_SCHEMA_VERSION,
    build_development_event_map,
    canonical_rows_fingerprint,
    canonical_sha256,
    validate_feature_rows,
)

H1_PREDICTION_SCHEMA = "kxbtcd_candidate_e_h1_oof_prediction.v1"
H2_PREDICTION_SCHEMA = "kxbtcd_candidate_e_h2_prediction.v1"
H3_PREDICTION_SCHEMA = "kxbtcd_candidate_e_h3_prediction.v1"
FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_entry_model_v1_preparation_freeze.v1"
FEATURE_FIELDS = (
    "schema_version",
    "model_id",
    "stage",
    "state_id",
    "event_ticker",
    "event_close_time_utc",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "decision_time_utc",
    "candidate_probability",
    "r_5m",
    "spread_t",
    "mid_move_1m",
    "spread_change_1m",
    "bid_range_1m",
    "ask_range_1m",
    "log1p_volume_1m",
    "log1p_open_interest",
    "log1p_trade_count_5m",
    "log1p_contracts_5m",
    "taker_imbalance_5m",
)
IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_entry_model_v1.py",
    "src/kxbtcd_candidate_e_entry_model_v1_materialization.py",
    "prepare_kxbtcd_candidate_e_entry_model_v1.py",
    "validate_kxbtcd_candidate_e_entry_model_v1_preparation.py",
)
SOURCE_FILE_KEYS = (
    "preoutcome",
    "h1_predictions",
    "h2_predictions",
    "h3_predictions",
    "archive_allowlist",
    "archive_candles",
    "archive_trades",
)

EVENT_MAP_FIELDS = (
    "schema_version",
    "model_id",
    "stage",
    "stage_event_index_zero_based",
    "event_ticker",
    "event_close_time_utc",
    "row_count",
)


class CandidateEEntryMaterializationError(RuntimeError):
    """Raised when deterministic Model-2 feature materialization fails closed."""


def _error(message: str) -> None:
    raise CandidateEEntryMaterializationError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CandidateEEntryMaterializationError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    if nonnegative and result < 0.0:
        _error(f"{name} must be nonnegative")
    return result


def _parse_utc(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateEEntryMaterializationError(f"{name} must be ISO-8601") from exc
    if dt.tzinfo is None:
        _error(f"{name} must include timezone")
    return dt.astimezone(timezone.utc)


def _format_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _state_id(row: Mapping[str, Any]) -> str:
    event = _text(row.get("event_ticker"), "preoutcome.event_ticker")
    market = _text(row.get("market_ticker"), "preoutcome.market_ticker")
    try:
        ttc = int(row.get("ttc_target_minutes"))
    except (TypeError, ValueError) as exc:
        raise CandidateEEntryMaterializationError("preoutcome.ttc_target_minutes must be integer") from exc
    role = _text(row.get("structural_role"), "preoutcome.structural_role")
    return f"{event}|{market}|TTC{ttc}|{role}"


def _prediction_projection(
    rows: Sequence[Mapping[str, Any]],
    *,
    stage: str,
    schema_version: str,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for index, source in enumerate(rows):
        if source.get("schema_version") != schema_version:
            _error(f"{stage} prediction row[{index}] schema mismatch")
        if source.get("candidate_id") != CANDIDATE_E_ID:
            # H1 OOF contains the rejected momentum challenger too.  It is ignored
            # rather than allowed to alter the frozen Model-2 state set.
            continue
        state = _text(source.get("state_id"), f"{stage} prediction row[{index}].state_id")
        if state in result:
            _error(f"duplicate {stage} Candidate-E state_id {state}")
        result[state] = {
            "state_id": state,
            "event_ticker": _text(source.get("event_ticker"), f"{stage}[{index}].event_ticker"),
            "market_ticker": _text(source.get("market_ticker"), f"{stage}[{index}].market_ticker"),
            "candidate_probability": _text(
                str(source.get("candidate_probability", "")),
                f"{stage}[{index}].candidate_probability",
            ),
        }
    if not result:
        _error(f"{stage} Candidate-E prediction projection is empty")
    return result


def project_development_predictions(
    h1_rows: Sequence[Mapping[str, Any]],
    h2_rows: Sequence[Mapping[str, Any]],
    h3_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> dict[str, dict[str, dict[str, str]]]:
    projected = {
        "H1_OOF": _prediction_projection(h1_rows, stage="H1_OOF", schema_version=H1_PREDICTION_SCHEMA),
        "H2": _prediction_projection(h2_rows, stage="H2", schema_version=H2_PREDICTION_SCHEMA),
        "H3": _prediction_projection(h3_rows, stage="H3", schema_version=H3_PREDICTION_SCHEMA),
    }
    if enforce_frozen_counts:
        for stage in DEVELOPMENT_STAGES:
            if len(projected[stage]) != EXPECTED_DEVELOPMENT_ROW_COUNTS[stage]:
                _error(
                    f"{stage} Candidate-E prediction count changed: {len(projected[stage])} != "
                    f"{EXPECTED_DEVELOPMENT_ROW_COUNTS[stage]}"
                )
            events = {row["event_ticker"] for row in projected[stage].values()}
            if len(events) != EXPECTED_DEVELOPMENT_EVENT_COUNTS[stage]:
                _error(
                    f"{stage} Candidate-E prediction event count changed: {len(events)} != "
                    f"{EXPECTED_DEVELOPMENT_EVENT_COUNTS[stage]}"
                )
    return projected


@dataclass(frozen=True)
class TradeSeries:
    times: tuple[float, ...]
    prefix_contracts: tuple[float, ...]
    prefix_yes: tuple[float, ...]
    prefix_no: tuple[float, ...]

    def trailing_5m(self, decision_epoch: float) -> tuple[int, float, float, float]:
        # Frozen causal window: decision-300 < t <= decision.
        left = bisect_right(self.times, decision_epoch - 300.0)
        right = bisect_right(self.times, decision_epoch)
        count = right - left
        contracts = self.prefix_contracts[right] - self.prefix_contracts[left]
        yes = self.prefix_yes[right] - self.prefix_yes[left]
        no = self.prefix_no[right] - self.prefix_no[left]
        return count, contracts, yes, no


def build_trade_index(
    rows: Sequence[Mapping[str, Any]],
    *,
    allowed_markets: set[str] | None = None,
    expected_identity_by_market: Mapping[str, tuple[str, str]] | None = None,
) -> dict[str, TradeSeries]:
    by_market: dict[str, list[tuple[float, str, float, str]]] = {}
    seen_ids: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        market = _text(row.get("market_ticker"), f"trade[{index}].market_ticker")
        if allowed_markets is not None and market not in allowed_markets:
            continue
        if expected_identity_by_market is not None:
            expected = expected_identity_by_market.get(market)
            if expected is None:
                _error(f"trade[{index}] market is outside selected development identities")
            stage = _text(row.get("stage"), f"trade[{index}].stage")
            event = _text(row.get("event_ticker"), f"trade[{index}].event_ticker")
            if (stage, event) != expected:
                _error(
                    f"trade[{index}] stage/event identity mismatch for {market}: "
                    f"{stage}/{event} != {expected[0]}/{expected[1]}"
                )
        trade_id = _text(row.get("trade_id"), f"trade[{index}].trade_id")
        identity = (market, trade_id)
        if identity in seen_ids:
            _error(f"duplicate trade identity {market}/{trade_id}")
        seen_ids.add(identity)
        created = _parse_utc(row.get("created_time"), f"trade[{index}].created_time").timestamp()
        contracts = _number(row.get("count_fp"), f"trade[{index}].count_fp", nonnegative=True)
        side = _text(row.get("taker_outcome_side"), f"trade[{index}].taker_outcome_side").lower()
        if side not in {"yes", "no"}:
            _error(f"trade[{index}] taker_outcome_side must be yes/no")
        by_market.setdefault(market, []).append((created, trade_id, contracts, side))

    result: dict[str, TradeSeries] = {}
    for market, values in by_market.items():
        values.sort(key=lambda item: (item[0], item[1]))
        times: list[float] = []
        contracts_prefix = [0.0]
        yes_prefix = [0.0]
        no_prefix = [0.0]
        for created, _trade_id, contracts, side in values:
            times.append(created)
            contracts_prefix.append(contracts_prefix[-1] + contracts)
            yes_prefix.append(yes_prefix[-1] + (contracts if side == "yes" else 0.0))
            no_prefix.append(no_prefix[-1] + (contracts if side == "no" else 0.0))
        result[market] = TradeSeries(
            tuple(times), tuple(contracts_prefix), tuple(yes_prefix), tuple(no_prefix)
        )
    return result


def build_candle_index(
    rows: Sequence[Mapping[str, Any]],
    *,
    allowed_markets: set[str] | None = None,
) -> dict[tuple[str, int], Mapping[str, Any]]:
    result: dict[tuple[str, int], Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        market = _text(row.get("market_ticker"), f"candle[{index}].market_ticker")
        if allowed_markets is not None and market not in allowed_markets:
            continue
        try:
            end_ts = int(row.get("end_period_ts"))
        except (TypeError, ValueError) as exc:
            raise CandidateEEntryMaterializationError(
                f"candle[{index}].end_period_ts must be integer"
            ) from exc
        key = (market, end_ts)
        if key in result:
            _error(f"duplicate exact candle key {market}/{end_ts}")
        result[key] = row
    return result


def _preoutcome_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        stage = str(row.get("stage", ""))
        if stage not in {"H1", "H2", "H3"}:
            continue
        state = _state_id(row)
        if state in result:
            _error(f"duplicate Candidate-E preoutcome state {state}")
        result[state] = row
    if not result:
        _error("Candidate-E preoutcome index is empty")
    return result


def _archive_stage_map(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    allowed = set(DEVELOPMENT_STAGES) | {"C1", "C2", "C3"}
    for index, row in enumerate(rows):
        stage = _text(row.get("stage"), f"allowlist[{index}].stage")
        if stage not in allowed:
            _error(f"archive allow-list contains unrecognized/protected stage {stage!r}")
        if stage not in DEVELOPMENT_STAGES:
            # Validation identities are deliberately not indexed during 21M.
            # This keeps C1/C2/C3 outside Model-2 development materialization.
            continue
        event = _text(row.get("event_ticker"), f"allowlist[{index}].event_ticker")
        market = _text(row.get("market_ticker"), f"allowlist[{index}].market_ticker")
        key = (event, market)
        if key in result and result[key] != stage:
            _error(f"archive market {event}/{market} crosses stages")
        result[key] = stage
    return result


def materialize_development_features(
    *,
    preoutcome_rows: Sequence[Mapping[str, Any]],
    h1_prediction_rows: Sequence[Mapping[str, Any]],
    h2_prediction_rows: Sequence[Mapping[str, Any]],
    h3_prediction_rows: Sequence[Mapping[str, Any]],
    archive_allowlist_rows: Sequence[Mapping[str, Any]],
    candle_rows: Sequence[Mapping[str, Any]],
    trade_rows: Sequence[Mapping[str, Any]],
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    predictions = project_development_predictions(
        h1_prediction_rows, h2_prediction_rows, h3_prediction_rows,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    preoutcome = _preoutcome_index(preoutcome_rows)
    archive_stage = _archive_stage_map(archive_allowlist_rows)
    selected_states = [
        (stage, state, prediction)
        for stage in DEVELOPMENT_STAGES
        for state, prediction in predictions[stage].items()
    ]
    selected_markets = {prediction["market_ticker"] for _, _, prediction in selected_states}
    selected_market_identity: dict[str, tuple[str, str]] = {}
    for stage, _state, prediction in selected_states:
        market = prediction["market_ticker"]
        identity = (stage, prediction["event_ticker"])
        prior = selected_market_identity.setdefault(market, identity)
        if prior != identity:
            _error(f"selected market {market} crosses development stage/event identities")
    candles = build_candle_index(candle_rows, allowed_markets=selected_markets)
    trades = build_trade_index(
        trade_rows,
        allowed_markets=selected_markets,
        expected_identity_by_market=selected_market_identity,
    )

    result: list[dict[str, Any]] = []
    for stage, state, prediction in selected_states:
        source = preoutcome.get(state)
        if source is None:
            _error(f"Candidate-E prediction state missing preoutcome source: {state}")
        event = prediction["event_ticker"]
        market = prediction["market_ticker"]
        if _text(source.get("event_ticker"), "preoutcome.event_ticker") != event:
            _error(f"state {state} event identity mismatch")
        if _text(source.get("market_ticker"), "preoutcome.market_ticker") != market:
            _error(f"state {state} market identity mismatch")
        source_stage = _text(source.get("stage"), "preoutcome.stage")
        expected_source_stage = "H1" if stage == "H1_OOF" else stage
        if source_stage != expected_source_stage:
            _error(f"state {state} preoutcome stage mismatch: {source_stage} != {expected_source_stage}")
        if archive_stage.get((event, market)) != stage:
            _error(f"state {state} execution-archive stage mismatch")

        decision_dt = _parse_utc(source.get("decision_target_utc"), f"{state}.decision_target_utc")
        decision_ts_float = decision_dt.timestamp()
        decision_ts = int(decision_ts_float)
        if decision_dt.microsecond != 0 or decision_ts_float != float(decision_ts) or decision_ts % 60 != 0:
            _error(f"state {state} decision timestamp is not an exact minute boundary")

        # Candidate E was frozen under the pre-outcome rule "latest valid real
        # two-sided quote with end_period_ts <= scheduled target and <=60 seconds
        # stale".  Therefore the exact archive candle for Model-2 quote features
        # is the already-frozen Candidate-E quote timestamp, not necessarily the
        # scheduled decision minute.  We reconstruct that exact state and never
        # search for a nearest/later replacement.
        try:
            quote_ts = int(source.get("kalshi_quote_end_period_ts"))
            quote_staleness = int(source.get("kalshi_quote_staleness_seconds"))
        except (TypeError, ValueError) as exc:
            raise CandidateEEntryMaterializationError(
                f"state {state} frozen Kalshi quote timestamp/staleness must be integer"
            ) from exc
        if quote_ts % 60 != 0:
            _error(f"state {state} frozen Kalshi quote timestamp is not an exact minute boundary")
        observed_staleness = decision_ts - quote_ts
        if quote_ts > decision_ts:
            _error(f"state {state} frozen Kalshi quote timestamp is after decision timestamp")
        if quote_staleness != observed_staleness:
            _error(
                f"state {state} frozen Kalshi quote staleness mismatch: "
                f"{quote_staleness} != {observed_staleness}"
            )
        if not 0 <= quote_staleness <= 60:
            _error(f"state {state} frozen Kalshi quote staleness is outside [0, 60] seconds")

        candle = candles.get((market, quote_ts))
        if candle is None:
            _error(f"state {state} has no exact one-minute candle at frozen Kalshi quote timestamp")
        if _text(candle.get("event_ticker"), f"{state}.candle.event_ticker") != event:
            _error(f"state {state} candle event identity mismatch")
        if str(candle.get("stage", "")) != stage:
            _error(f"state {state} candle stage mismatch")

        yes_bid = _number(source.get("yes_bid"), f"{state}.yes_bid")
        yes_ask = _number(source.get("yes_ask"), f"{state}.yes_ask")
        if not 0.0 <= yes_bid <= yes_ask <= 1.0:
            _error(f"state {state} invalid Candidate-E two-sided quote")
        bid_open = _number(candle.get("yes_bid_open_dollars"), f"{state}.yes_bid_open")
        bid_low = _number(candle.get("yes_bid_low_dollars"), f"{state}.yes_bid_low")
        bid_high = _number(candle.get("yes_bid_high_dollars"), f"{state}.yes_bid_high")
        bid_close = _number(candle.get("yes_bid_close_dollars"), f"{state}.yes_bid_close")
        ask_open = _number(candle.get("yes_ask_open_dollars"), f"{state}.yes_ask_open")
        ask_low = _number(candle.get("yes_ask_low_dollars"), f"{state}.yes_ask_low")
        ask_high = _number(candle.get("yes_ask_high_dollars"), f"{state}.yes_ask_high")
        ask_close = _number(candle.get("yes_ask_close_dollars"), f"{state}.yes_ask_close")
        if abs(bid_close - yes_bid) > 1e-12 or abs(ask_close - yes_ask) > 1e-12:
            _error(f"state {state} frozen Candidate-E quote does not match exact archive candle close")
        volume = _number(candle.get("volume_fp"), f"{state}.volume_fp", nonnegative=True)
        open_interest = _number(candle.get("open_interest_fp"), f"{state}.open_interest_fp", nonnegative=True)
        if not (bid_low <= min(bid_open, bid_close) <= max(bid_open, bid_close) <= bid_high):
            _error(f"state {state} inconsistent YES-bid candle OHLC")
        if not (ask_low <= min(ask_open, ask_close) <= max(ask_open, ask_close) <= ask_high):
            _error(f"state {state} inconsistent YES-ask candle OHLC")

        series = trades.get(market)
        if series is None:
            trade_count, contracts, yes_contracts, no_contracts = 0, 0.0, 0.0, 0.0
        else:
            trade_count, contracts, yes_contracts, no_contracts = series.trailing_5m(decision_dt.timestamp())
        taker_denominator = yes_contracts + no_contracts
        taker_imbalance = 0.0 if taker_denominator == 0.0 else (
            (yes_contracts - no_contracts) / taker_denominator
        )

        row = {
            "schema_version": ROW_SCHEMA_VERSION,
            "model_id": MODEL_ID,
            "stage": stage,
            "state_id": state,
            "event_ticker": event,
            "event_close_time_utc": _format_utc(
                _parse_utc(source.get("event_close_time_utc"), f"{state}.event_close_time_utc")
            ),
            "market_ticker": market,
            "structural_role": _text(source.get("structural_role"), f"{state}.structural_role"),
            "ttc_target_minutes": int(source.get("ttc_target_minutes")),
            "decision_time_utc": _format_utc(decision_dt),
            "candidate_probability": _number(
                prediction["candidate_probability"], f"{state}.candidate_probability"
            ),
            "r_5m": _number(source.get("r_5m"), f"{state}.r_5m"),
            "spread_t": yes_ask - yes_bid,
            "mid_move_1m": ((bid_close + ask_close) - (bid_open + ask_open)) / 2.0,
            "spread_change_1m": (ask_close - bid_close) - (ask_open - bid_open),
            "bid_range_1m": bid_high - bid_low,
            "ask_range_1m": ask_high - ask_low,
            "log1p_volume_1m": math.log1p(volume),
            "log1p_open_interest": math.log1p(open_interest),
            "log1p_trade_count_5m": math.log1p(trade_count),
            "log1p_contracts_5m": math.log1p(contracts),
            "taker_imbalance_5m": taker_imbalance,
        }
        result.append(row)

    result.sort(key=lambda row: (DEVELOPMENT_STAGES.index(row["stage"]), row["event_close_time_utc"], row["event_ticker"], row["state_id"]))
    validate_feature_rows(result, enforce_frozen_counts=enforce_frozen_counts)
    build_development_event_map(result, enforce_frozen_counts=enforce_frozen_counts)
    return tuple(result)


def read_csv(path: str | Path) -> list[dict[str, str]]:
    target = Path(path)
    try:
        with target.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError as exc:
        raise CandidateEEntryMaterializationError(f"could not read CSV {target}: {exc}") from exc


def write_csv(path: str | Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows):
            if set(row) != set(fields):
                _error(
                    f"output row[{index}] schema mismatch for {target.name}; "
                    f"missing={sorted(set(fields)-set(row))}, extra={sorted(set(row)-set(fields))}"
                )
            writer.writerow({field: row[field] for field in fields})
    temp.replace(target)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_preparation_freeze(
    feature_rows: Sequence[Mapping[str, Any]],
    event_map_rows: Sequence[Mapping[str, Any]],
    *,
    source_files: Mapping[str, str | Path],
    implementation_sha256s: Mapping[str, str],
    prepared_output_files: Mapping[str, str | Path] | None = None,
    enforce_frozen_counts: bool = True,
) -> dict[str, Any]:
    validate_feature_rows(feature_rows, enforce_frozen_counts=enforce_frozen_counts)
    expected_event_map = build_development_event_map(
        feature_rows, enforce_frozen_counts=enforce_frozen_counts
    )
    if tuple(dict(row) for row in event_map_rows) != expected_event_map:
        _error("development event map differs from deterministic derivation")
    source_hashes = {name: sha256_file(path) for name, path in sorted(source_files.items())}
    output_hashes = {
        name: sha256_file(path) for name, path in sorted((prepared_output_files or {}).items())
    }
    payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21M",
        "model_id": MODEL_ID,
        "feature_contract": list(FEATURE_FIELDS),
        "continuous_feature_count": 11,
        "learned_parameter_count": 21,
        "development_stages": list(DEVELOPMENT_STAGES),
        "development_event_counts": dict(EXPECTED_DEVELOPMENT_EVENT_COUNTS),
        "development_row_counts": dict(EXPECTED_DEVELOPMENT_ROW_COUNTS),
        "feature_rows_fingerprint": canonical_rows_fingerprint(feature_rows),
        "development_event_map_fingerprint": canonical_rows_fingerprint(
            event_map_rows, key="event_ticker"
        ),
        "source_file_sha256s": source_hashes,
        "prepared_output_sha256s": output_hashes,
        "implementation_sha256s": dict(sorted(implementation_sha256s.items())),
        "outcomes_in_feature_rows": False,
        "strategy_v1_pnl_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "execution_enabled": False,
    }
    payload["preparation_fingerprint"] = canonical_sha256(payload)
    return payload


__all__ = [
    "CandidateEEntryMaterializationError",
    "EVENT_MAP_FIELDS",
    "FEATURE_FIELDS",
    "FREEZE_SCHEMA_VERSION",
    "H1_PREDICTION_SCHEMA",
    "H2_PREDICTION_SCHEMA",
    "H3_PREDICTION_SCHEMA",
    "IMPLEMENTATION_FILES",
    "SOURCE_FILE_KEYS",
    "build_candle_index",
    "build_preparation_freeze",
    "build_trade_index",
    "materialize_development_features",
    "project_development_predictions",
    "read_csv",
    "sha256_file",
    "write_csv",
]

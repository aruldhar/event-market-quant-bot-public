"""Checkpoint 21M: outcome-blind C1+C2 Model-2 validation preparation.

This module:
- reads only frozen C1/C2 pre-outcome rows;
- reconstructs stage-native Candidate-E probabilities from Champion-R0 (C1)
  and Champion-R1 (C2);
- uses the frozen execution archive to build the unchanged Model-2 entry-state
  features;
- assigns the combined 1,000 validation events to five chronological 200-event
  blocks; and
- emits no outcome, settlement, P&L, or execution field.

Historical C1/C2 prediction CSVs are intentionally not inputs because those
files contain an outcome column.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_entry_model_v1 import (
    CANDIDATE_E_ID,
    CONTINUOUS_FEATURES,
    MODEL_ID,
    ROW_SCHEMA_VERSION,
    STRUCTURAL_ROLES,
    TTC_LEVELS,
    canonical_rows_fingerprint,
    canonical_sha256,
    stable_sigmoid,
)
from .kxbtcd_candidate_e_entry_model_v1_materialization import (
    build_candle_index,
    build_trade_index,
)
from .kxbtcd_candidate_e_predeclaration import market_logit_offset

PARENT_COMMIT = "1ba8281628ba8b406218fa629a73bcdc6e4801c7"
DEVELOPMENT_FREEZE_FINGERPRINT = "a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e"
SELECTED_LAMBDA = 0.01

VALIDATION_STAGES = ("C1", "C2")
EXPECTED_STAGE_EVENT_COUNTS = {"C1": 500, "C2": 500}
EXPECTED_STAGE_ROW_COUNTS = {"C1": 14887, "C2": 14007}
EXPECTED_VALIDATION_EVENTS = 1000
EXPECTED_VALIDATION_ROWS = 28894
VALIDATION_BLOCKS = ("V0", "V1", "V2", "V3", "V4")
EVENTS_PER_VALIDATION_BLOCK = 200

C1_PREOUTCOME_SHA256 = "a2ee363f89308a74c6ac69d1e0f0c8cba9ef446407d95d6ebd5dacf7a91939d9"
C2_PREOUTCOME_SHA256 = "95c0189e078bfc4db656fef387721b3fd8f344c0e8ab3a7ce7f34fd2824ac0f0"
ARCHIVE_SHA256S = {
    "archive_allowlist": "cd80fb8a891c30127f8cc0404a7b525238c3c3d06f2f105825b8541399f3443a",
    "archive_candles": "fef40a30cb2d61229676a3927873d90cda449c83167ab8dc7226b966b787b73f",
    "archive_trades": "8af2f184f7181b2cb7cef1873559bcfb96c0121065265172c1505dd671bb59a1",
}

CHAMPION = {
    "C1": {
        "schema_version": "kxbtcd_candidate_e_champion_r0.v1",
        "fingerprint_field": "champion_r0_fingerprint",
        "fingerprint": "ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa",
        "beta_distance": 0.014447239079794087,
    },
    "C2": {
        "schema_version": "kxbtcd_candidate_e_champion_r1.v1",
        "fingerprint_field": "champion_r1_fingerprint",
        "fingerprint": "863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee",
        "beta_distance": 0.014529004270980883,
    },
}

FORBIDDEN_SOURCE_FIELDS = {"outcome", "settlement", "settled", "result", "label", "target", "y"}

FEATURE_FIELDS = (
    "schema_version", "model_id", "stage", "state_id", "event_ticker",
    "event_close_time_utc", "market_ticker", "structural_role",
    "ttc_target_minutes", "decision_time_utc", "candidate_probability",
    "r_5m", "spread_t", "mid_move_1m", "spread_change_1m",
    "bid_range_1m", "ask_range_1m", "log1p_volume_1m",
    "log1p_open_interest", "log1p_trade_count_5m", "log1p_contracts_5m",
    "taker_imbalance_5m",
)
OFFSET_SCHEMA_VERSION = "kxbtcd_candidate_e_entry_model_v1_validation_offset.v1"
OFFSET_FIELDS = (
    "schema_version", "model_id", "stage", "state_id", "candidate_logit_offset",
)
EVENT_MAP_FIELDS = (
    "schema_version", "model_id", "validation_block",
    "validation_event_index_zero_based", "stage", "stage_event_index_zero_based",
    "event_ticker", "event_close_time_utc", "row_count",
)
EVENT_MAP_SCHEMA_VERSION = "kxbtcd_candidate_e_entry_model_v1_validation_event.v1"
FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_entry_model_v1_validation_preparation_freeze.v1"


class ValidationPreparationError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise ValidationPreparationError(message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationPreparationError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    if nonnegative and result < 0.0:
        _error(f"{name} must be nonnegative")
    return result


def _parse_utc(value: Any, name: str):
    from datetime import datetime, timezone
    text = _text(value, name)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationPreparationError(f"{name} must be ISO-8601") from exc
    if dt.tzinfo is None:
        _error(f"{name} must include timezone")
    return dt.astimezone(timezone.utc)


def _format_utc(dt) -> str:
    from datetime import timezone
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _state_id(row: Mapping[str, Any]) -> str:
    event = _text(row.get("event_ticker"), "preoutcome.event_ticker")
    market = _text(row.get("market_ticker"), "preoutcome.market_ticker")
    role = _text(row.get("structural_role"), "preoutcome.structural_role")
    try:
        ttc = int(row.get("ttc_target_minutes"))
    except (TypeError, ValueError) as exc:
        raise ValidationPreparationError("preoutcome.ttc_target_minutes must be integer") from exc
    return f"{event}|{market}|TTC{ttc}|{role}"


def read_preoutcome_csv_strict(path: str | Path, *, expected_stage: str) -> list[dict[str, str]]:
    """Require duplicate stage/block_id columns to agree before normalization."""
    target = Path(path)
    try:
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            positions: dict[str, list[int]] = {}
            for index, name in enumerate(header):
                positions.setdefault(name, []).append(index)

            for required in ("stage", "block_id"):
                if len(positions.get(required, [])) != 2:
                    _error(f"{target.name}: expected exactly two {required!r} columns")

            forbidden = sorted(FORBIDDEN_SOURCE_FIELDS.intersection(header))
            if forbidden:
                _error(f"{target.name}: forbidden outcome-like fields present: {forbidden}")

            unique_header: list[str] = []
            for name in header:
                if name not in unique_header:
                    unique_header.append(name)

            rows: list[dict[str, str]] = []
            for row_number, values in enumerate(reader, start=2):
                if len(values) != len(header):
                    _error(f"{target.name} row {row_number}: width mismatch")
                normalized: dict[str, str] = {}
                for name in unique_header:
                    observed = [values[i] for i in positions[name]]
                    if any(value != observed[0] for value in observed[1:]):
                        _error(f"{target.name} row {row_number}: duplicate {name!r} values disagree")
                    normalized[name] = observed[0]
                if normalized.get("stage") != expected_stage:
                    _error(
                        f"{target.name} row {row_number}: stage "
                        f"{normalized.get('stage')!r} != {expected_stage!r}"
                    )
                rows.append(normalized)
            return rows
    except OSError as exc:
        raise ValidationPreparationError(f"could not read pre-outcome CSV {target}: {exc}") from exc


def read_csv_filtered(path: str | Path, *, allowed_markets: set[str] | None = None) -> list[dict[str, str]]:
    target = Path(path)
    result: list[dict[str, str]] = []
    try:
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                _error(f"{target.name}: empty CSV header")
            for row in reader:
                if allowed_markets is not None and row.get("market_ticker") not in allowed_markets:
                    continue
                result.append(dict(row))
    except OSError as exc:
        raise ValidationPreparationError(f"could not read CSV {target}: {exc}") from exc
    return result


def read_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationPreparationError(f"could not read JSON {target}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {target}")
    return value


def validate_champion_config(document: Mapping[str, Any], *, stage: str) -> float:
    expected = CHAMPION[stage]
    if document.get("schema_version") != expected["schema_version"]:
        _error(f"{stage} champion schema changed")
    if document.get("candidate_id") != CANDIDATE_E_ID:
        _error(f"{stage} champion candidate changed")
    if document.get(expected["fingerprint_field"]) != expected["fingerprint"]:
        _error(f"{stage} champion fingerprint changed")
    model = document.get("model")
    if not isinstance(model, Mapping):
        _error(f"{stage} champion model missing")
    beta = _number(model.get("beta_distance"), f"{stage}.beta_distance")
    if beta != expected["beta_distance"]:
        _error(f"{stage} beta_distance changed")
    if model.get("formula") != "logit(p)=market_logit_offset + beta_distance*d_BTC":
        _error(f"{stage} Candidate-E formula changed")
    if model.get("market_logit_offset_clip") != "0.001":
        _error(f"{stage} Candidate-E market-logit clip changed")
    return beta


def reconstruct_candidate_state(
    *, stage: str, q_market: Any, d_btc: Any, beta_distance: float
) -> tuple[float, float]:
    """Return exact finite Candidate-E latent logit plus historical float probability.

    The probability may round to 0.0/1.0 in IEEE-754 for an extreme but finite
    latent logit.  That endpoint is preserved for historical-probability
    compatibility; it is never clipped.  Model-2 validation must use the finite
    latent logit as its offset, which is mathematically identical to
    logit(sigmoid(z)) without the lossy probability round-trip.
    """
    if stage not in VALIDATION_STAGES:
        _error(f"unauthorized validation stage {stage!r}")
    q = _number(q_market, f"{stage}.q_market")
    d = _number(d_btc, f"{stage}.d_BTC")
    if not 0.0 <= q <= 1.0:
        _error(f"{stage}.q_market must be in [0,1]")
    if beta_distance != CHAMPION[stage]["beta_distance"]:
        _error(f"{stage} beta_distance does not match frozen champion")
    latent_logit = market_logit_offset(q) + beta_distance * d
    if not math.isfinite(latent_logit):
        _error(f"{stage} reconstructed Candidate-E latent logit is non-finite")
    probability = stable_sigmoid(latent_logit)
    if not 0.0 <= probability <= 1.0:
        _error(f"{stage} reconstructed Candidate-E probability is outside [0,1]")
    return latent_logit, probability


def reconstruct_candidate_probability(
    *, stage: str, q_market: Any, d_btc: Any, beta_distance: float
) -> float:
    return reconstruct_candidate_state(
        stage=stage, q_market=q_market, d_btc=d_btc, beta_distance=beta_distance
    )[1]


def reconstruct_candidate_logit(
    *, stage: str, q_market: Any, d_btc: Any, beta_distance: float
) -> float:
    return reconstruct_candidate_state(
        stage=stage, q_market=q_market, d_btc=d_btc, beta_distance=beta_distance
    )[0]


def _archive_stage_map(
    rows: Sequence[Mapping[str, Any]], *, selected_markets: set[str]
) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for index, row in enumerate(rows):
        market = _text(row.get("market_ticker"), f"allowlist[{index}].market_ticker")
        if market not in selected_markets:
            continue
        stage = _text(row.get("stage"), f"allowlist[{index}].stage")
        if stage not in VALIDATION_STAGES:
            _error(f"selected validation market {market} has archive stage {stage!r}")
        event = _text(row.get("event_ticker"), f"allowlist[{index}].event_ticker")
        key = (event, market)
        prior = result.setdefault(key, stage)
        if prior != stage:
            _error(f"archive identity {event}/{market} crosses stages")
    return result


def validate_feature_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    if len(rows) != EXPECTED_VALIDATION_ROWS:
        _error(f"validation feature row count changed: {len(rows)} != {EXPECTED_VALIDATION_ROWS}")
    if any(set(row) != set(FEATURE_FIELDS) for row in rows):
        _error("validation feature-row schema changed")
    seen_states: set[str] = set()
    by_stage_events = {stage: set() for stage in VALIDATION_STAGES}
    by_stage_rows = {stage: 0 for stage in VALIDATION_STAGES}
    for index, row in enumerate(rows):
        if row.get("schema_version") != ROW_SCHEMA_VERSION:
            _error(f"feature row[{index}] schema changed")
        if row.get("model_id") != MODEL_ID:
            _error(f"feature row[{index}] model changed")
        stage = str(row.get("stage"))
        if stage not in VALIDATION_STAGES:
            _error(f"feature row[{index}] unauthorized stage {stage!r}")
        state = str(row.get("state_id"))
        if not state or state in seen_states:
            _error(f"feature row[{index}] duplicate/blank state_id {state!r}")
        seen_states.add(state)
        event = _text(row.get("event_ticker"), f"feature[{index}].event_ticker")
        by_stage_events[stage].add(event)
        by_stage_rows[stage] += 1
        if row.get("structural_role") not in STRUCTURAL_ROLES:
            _error(f"feature row[{index}] structural role changed")
        try:
            ttc = int(row.get("ttc_target_minutes"))
        except (TypeError, ValueError) as exc:
            raise ValidationPreparationError(f"feature row[{index}] TTC must be integer") from exc
        if ttc not in TTC_LEVELS:
            _error(f"feature row[{index}] TTC changed")
        p = _number(row.get("candidate_probability"), f"feature[{index}].candidate_probability")
        if not 0.0 <= p <= 1.0:
            _error(f"feature row[{index}] candidate probability must be inside [0,1]")
        for feature in CONTINUOUS_FEATURES:
            _number(row.get(feature), f"feature[{index}].{feature}")
    for stage in VALIDATION_STAGES:
        if by_stage_rows[stage] != EXPECTED_STAGE_ROW_COUNTS[stage]:
            _error(f"{stage} row count changed")
        if len(by_stage_events[stage]) != EXPECTED_STAGE_EVENT_COUNTS[stage]:
            _error(f"{stage} event count changed")
    if len(by_stage_events["C1"] | by_stage_events["C2"]) != EXPECTED_VALIDATION_EVENTS:
        _error("C1/C2 event identities overlap or validation event count changed")


def validate_offset_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_feature_states: set[str] | None = None,
) -> None:
    if len(rows) != EXPECTED_VALIDATION_ROWS:
        _error(f"validation offset row count changed: {len(rows)} != {EXPECTED_VALIDATION_ROWS}")
    seen: set[str] = set()
    by_stage = {stage: 0 for stage in VALIDATION_STAGES}
    for index, row in enumerate(rows):
        if set(row) != set(OFFSET_FIELDS):
            _error(f"validation offset row[{index}] schema changed")
        if row.get("schema_version") != OFFSET_SCHEMA_VERSION:
            _error(f"validation offset row[{index}] schema version changed")
        if row.get("model_id") != MODEL_ID:
            _error(f"validation offset row[{index}] model id changed")
        stage = str(row.get("stage"))
        if stage not in VALIDATION_STAGES:
            _error(f"validation offset row[{index}] unauthorized stage {stage!r}")
        state = _text(row.get("state_id"), f"offset[{index}].state_id")
        if state in seen:
            _error(f"duplicate validation offset state {state}")
        seen.add(state)
        _number(row.get("candidate_logit_offset"), f"offset[{index}].candidate_logit_offset")
        by_stage[stage] += 1
    for stage in VALIDATION_STAGES:
        if by_stage[stage] != EXPECTED_STAGE_ROW_COUNTS[stage]:
            _error(f"{stage} validation offset count changed")
    if expected_feature_states is not None and seen != expected_feature_states:
        _error("validation offset states differ from feature states")


def build_validation_offset_rows(
    *,
    c1_preoutcome_rows: Sequence[Mapping[str, Any]],
    c2_preoutcome_rows: Sequence[Mapping[str, Any]],
    champion_r0: Mapping[str, Any],
    champion_r1: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    beta_by_stage = {
        "C1": validate_champion_config(champion_r0, stage="C1"),
        "C2": validate_champion_config(champion_r1, stage="C2"),
    }
    sources = {"C1": list(c1_preoutcome_rows), "C2": list(c2_preoutcome_rows)}
    result: list[dict[str, Any]] = []
    for stage in VALIDATION_STAGES:
        if len(sources[stage]) != EXPECTED_STAGE_ROW_COUNTS[stage]:
            _error(f"{stage} pre-outcome row count changed while building offsets")
        beta = beta_by_stage[stage]
        for source in sources[stage]:
            state = _state_id(source)
            latent_logit, _ = reconstruct_candidate_state(
                stage=stage,
                q_market=source.get("q_market"),
                d_btc=source.get("d_BTC"),
                beta_distance=beta,
            )
            result.append({
                "schema_version": OFFSET_SCHEMA_VERSION,
                "model_id": MODEL_ID,
                "stage": stage,
                "state_id": state,
                "candidate_logit_offset": latent_logit,
            })
    result.sort(key=lambda row: row["state_id"])
    validate_offset_rows(result)
    return tuple(result)


def build_validation_event_map(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    validate_feature_rows(rows)
    event_data: dict[str, dict[str, Any]] = {}
    for row in rows:
        event = str(row["event_ticker"])
        stage = str(row["stage"])
        close = str(row["event_close_time_utc"])
        item = event_data.setdefault(
            event, {"stage": stage, "event_close_time_utc": close, "row_count": 0}
        )
        if item["stage"] != stage or item["event_close_time_utc"] != close:
            _error(f"event {event} has inconsistent validation identity")
        item["row_count"] += 1

    ordered = sorted(
        event_data.items(),
        key=lambda item: (_parse_utc(item[1]["event_close_time_utc"], f"{item[0]}.close"), item[0]),
    )
    if len(ordered) != EXPECTED_VALIDATION_EVENTS:
        _error("validation event map count changed")

    stage_index = {"C1": 0, "C2": 0}
    result: list[dict[str, Any]] = []
    for global_index, (event, item) in enumerate(ordered):
        block_index = global_index // EVENTS_PER_VALIDATION_BLOCK
        if block_index >= len(VALIDATION_BLOCKS):
            _error("validation block overflow")
        stage = str(item["stage"])
        result.append({
            "schema_version": EVENT_MAP_SCHEMA_VERSION,
            "model_id": MODEL_ID,
            "validation_block": VALIDATION_BLOCKS[block_index],
            "validation_event_index_zero_based": global_index,
            "stage": stage,
            "stage_event_index_zero_based": stage_index[stage],
            "event_ticker": event,
            "event_close_time_utc": item["event_close_time_utc"],
            "row_count": item["row_count"],
        })
        stage_index[stage] += 1

    counts = {block: sum(1 for row in result if row["validation_block"] == block) for block in VALIDATION_BLOCKS}
    if counts != {block: EVENTS_PER_VALIDATION_BLOCK for block in VALIDATION_BLOCKS}:
        _error(f"validation block sizes changed: {counts}")
    return tuple(result)


def materialize_validation_features(
    *,
    c1_preoutcome_rows: Sequence[Mapping[str, Any]],
    c2_preoutcome_rows: Sequence[Mapping[str, Any]],
    champion_r0: Mapping[str, Any],
    champion_r1: Mapping[str, Any],
    archive_allowlist_rows: Sequence[Mapping[str, Any]],
    candle_rows: Sequence[Mapping[str, Any]],
    trade_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    beta_by_stage = {
        "C1": validate_champion_config(champion_r0, stage="C1"),
        "C2": validate_champion_config(champion_r1, stage="C2"),
    }
    sources = {"C1": list(c1_preoutcome_rows), "C2": list(c2_preoutcome_rows)}
    for stage in VALIDATION_STAGES:
        if len(sources[stage]) != EXPECTED_STAGE_ROW_COUNTS[stage]:
            _error(f"{stage} pre-outcome row count changed")
        if len({str(row.get("event_ticker")) for row in sources[stage]}) != EXPECTED_STAGE_EVENT_COUNTS[stage]:
            _error(f"{stage} pre-outcome event count changed")

    selected_markets = {
        _text(row.get("market_ticker"), f"{stage}.market_ticker")
        for stage in VALIDATION_STAGES for row in sources[stage]
    }
    selected_market_identity: dict[str, tuple[str, str]] = {}
    for stage in VALIDATION_STAGES:
        for row in sources[stage]:
            market = _text(row.get("market_ticker"), f"{stage}.market_ticker")
            event = _text(row.get("event_ticker"), f"{stage}.event_ticker")
            prior = selected_market_identity.setdefault(market, (stage, event))
            if prior != (stage, event):
                _error(f"selected market {market} crosses stage/event identities")

    archive_stage = _archive_stage_map(archive_allowlist_rows, selected_markets=selected_markets)
    candles = build_candle_index(candle_rows, allowed_markets=selected_markets)
    trades = build_trade_index(
        trade_rows,
        allowed_markets=selected_markets,
        expected_identity_by_market=selected_market_identity,
    )

    result: list[dict[str, Any]] = []
    seen_states: set[str] = set()
    for stage in VALIDATION_STAGES:
        beta = beta_by_stage[stage]
        for source in sources[stage]:
            state = _state_id(source)
            if state in seen_states:
                _error(f"duplicate validation state {state}")
            seen_states.add(state)
            event = _text(source.get("event_ticker"), f"{state}.event_ticker")
            market = _text(source.get("market_ticker"), f"{state}.market_ticker")
            if archive_stage.get((event, market)) != stage:
                _error(f"state {state} execution-archive stage mismatch")

            decision_dt = _parse_utc(source.get("decision_target_utc"), f"{state}.decision_target_utc")
            decision_ts_float = decision_dt.timestamp()
            decision_ts = int(decision_ts_float)
            if decision_dt.microsecond != 0 or decision_ts_float != float(decision_ts) or decision_ts % 60 != 0:
                _error(f"state {state} decision timestamp is not minute-aligned")

            try:
                quote_ts = int(source.get("kalshi_quote_end_period_ts"))
                quote_staleness = int(source.get("kalshi_quote_staleness_seconds"))
            except (TypeError, ValueError) as exc:
                raise ValidationPreparationError(f"state {state} quote timestamp/staleness must be integer") from exc
            if quote_ts % 60 != 0:
                _error(f"state {state} quote timestamp is not minute-aligned")
            observed_staleness = decision_ts - quote_ts
            if quote_ts > decision_ts or quote_staleness != observed_staleness or not 0 <= quote_staleness <= 60:
                _error(f"state {state} frozen quote timing mismatch")

            candle = candles.get((market, quote_ts))
            if candle is None:
                _error(f"state {state} missing exact archive candle")
            if _text(candle.get("event_ticker"), f"{state}.candle.event") != event:
                _error(f"state {state} candle event mismatch")
            if _text(candle.get("stage"), f"{state}.candle.stage") != stage:
                _error(f"state {state} candle stage mismatch")

            yes_bid = _number(source.get("yes_bid"), f"{state}.yes_bid")
            yes_ask = _number(source.get("yes_ask"), f"{state}.yes_ask")
            if not 0.0 <= yes_bid <= yes_ask <= 1.0:
                _error(f"state {state} invalid two-sided quote")

            bid_open = _number(candle.get("yes_bid_open_dollars"), f"{state}.bid_open")
            bid_low = _number(candle.get("yes_bid_low_dollars"), f"{state}.bid_low")
            bid_high = _number(candle.get("yes_bid_high_dollars"), f"{state}.bid_high")
            bid_close = _number(candle.get("yes_bid_close_dollars"), f"{state}.bid_close")
            ask_open = _number(candle.get("yes_ask_open_dollars"), f"{state}.ask_open")
            ask_low = _number(candle.get("yes_ask_low_dollars"), f"{state}.ask_low")
            ask_high = _number(candle.get("yes_ask_high_dollars"), f"{state}.ask_high")
            ask_close = _number(candle.get("yes_ask_close_dollars"), f"{state}.ask_close")

            if abs(bid_close - yes_bid) > 1e-12 or abs(ask_close - yes_ask) > 1e-12:
                _error(f"state {state} frozen quote != archive candle close")
            if not (bid_low <= min(bid_open, bid_close) <= max(bid_open, bid_close) <= bid_high):
                _error(f"state {state} inconsistent YES-bid OHLC")
            if not (ask_low <= min(ask_open, ask_close) <= max(ask_open, ask_close) <= ask_high):
                _error(f"state {state} inconsistent YES-ask OHLC")

            volume = _number(candle.get("volume_fp"), f"{state}.volume_fp", nonnegative=True)
            open_interest = _number(candle.get("open_interest_fp"), f"{state}.open_interest_fp", nonnegative=True)

            series = trades.get(market)
            if series is None:
                trade_count, contracts, yes_contracts, no_contracts = 0, 0.0, 0.0, 0.0
            else:
                trade_count, contracts, yes_contracts, no_contracts = series.trailing_5m(decision_dt.timestamp())
            denominator = yes_contracts + no_contracts
            taker_imbalance = 0.0 if denominator == 0.0 else (yes_contracts - no_contracts) / denominator

            result.append({
                "schema_version": ROW_SCHEMA_VERSION,
                "model_id": MODEL_ID,
                "stage": stage,
                "state_id": state,
                "event_ticker": event,
                "event_close_time_utc": _format_utc(_parse_utc(source.get("event_close_time_utc"), f"{state}.close")),
                "market_ticker": market,
                "structural_role": _text(source.get("structural_role"), f"{state}.role"),
                "ttc_target_minutes": int(source.get("ttc_target_minutes")),
                "decision_time_utc": _format_utc(decision_dt),
                "candidate_probability": reconstruct_candidate_probability(
                    stage=stage,
                    q_market=source.get("q_market"),
                    d_btc=source.get("d_BTC"),
                    beta_distance=beta,
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
            })

    result.sort(key=lambda row: (_parse_utc(row["event_close_time_utc"], "event_close_time_utc"), row["event_ticker"], row["state_id"]))
    validate_feature_rows(result)
    build_validation_event_map(result)
    return tuple(result)


def write_csv(path: str | Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows):
            if set(row) != set(fields):
                _error(f"output row[{index}] schema mismatch for {target.name}")
            writer.writerow({field: row[field] for field in fields})
    temp.replace(target)


def write_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    temp.replace(target)


def build_validation_preparation_freeze(
    *,
    feature_rows: Sequence[Mapping[str, Any]],
    offset_rows: Sequence[Mapping[str, Any]],
    event_map_rows: Sequence[Mapping[str, Any]],
    source_files: Mapping[str, str | Path],
    implementation_files: Mapping[str, str | Path],
    output_files: Mapping[str, str | Path],
    development_freeze_document: Mapping[str, Any],
) -> dict[str, Any]:
    validate_feature_rows(feature_rows)
    feature_by_state = {str(row["state_id"]): row for row in feature_rows}
    validate_offset_rows(offset_rows, expected_feature_states=set(feature_by_state))
    offset_by_state = {str(row["state_id"]): row for row in offset_rows}
    for state, feature in feature_by_state.items():
        offset = _number(
            offset_by_state[state]["candidate_logit_offset"],
            f"{state}.candidate_logit_offset",
        )
        probability = _number(
            feature["candidate_probability"], f"{state}.candidate_probability"
        )
        if stable_sigmoid(offset) != probability:
            _error(f"state {state} probability/finite-offset representation mismatch")
    deterministic_event_map = build_validation_event_map(feature_rows)
    if tuple(dict(row) for row in event_map_rows) != deterministic_event_map:
        _error("validation event map differs from deterministic derivation")
    if development_freeze_document.get("development_freeze_fingerprint") != DEVELOPMENT_FREEZE_FINGERPRINT:
        _error("parent Model-2 development freeze changed")
    selection = development_freeze_document.get("selection")
    if not isinstance(selection, Mapping) or selection.get("selected_lambda") != SELECTED_LAMBDA:
        _error("parent Model-2 selected lambda changed")

    payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21M",
        "model_id": MODEL_ID,
        "parent_commit": PARENT_COMMIT,
        "parent_development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "selected_lambda": SELECTED_LAMBDA,
        "candidate_e_baseline": {
            "C1": {"champion": "Champion-R0", "fingerprint": CHAMPION["C1"]["fingerprint"], "beta_distance": CHAMPION["C1"]["beta_distance"]},
            "C2": {"champion": "Champion-R1", "fingerprint": CHAMPION["C2"]["fingerprint"], "beta_distance": CHAMPION["C2"]["beta_distance"]},
            "probability_source": "reconstructed_from_frozen_preoutcome_q_market_and_d_BTC_only",
            "offset_source": "market_logit_offset(q_market)+beta_distance*d_BTC",
            "model2_offset_input": "finite_validation_offset_sidecar",
            "probability_endpoint_policy": "preserve_historical_float_endpoint_no_clipping",
            "log_loss_numerics": "use_finite_candidate_logit_offset_not_probability_round_trip",
            "historical_prediction_csv_rows_read": False,
        },
        "validation_event_counts": dict(EXPECTED_STAGE_EVENT_COUNTS),
        "validation_row_counts": dict(EXPECTED_STAGE_ROW_COUNTS),
        "validation_events_total": EXPECTED_VALIDATION_EVENTS,
        "validation_rows_total": EXPECTED_VALIDATION_ROWS,
        "chronological_validation_blocks": {
            "blocks": list(VALIDATION_BLOCKS),
            "events_per_block": EVENTS_PER_VALIDATION_BLOCK,
            "assignment": "sort_unique_events_by_event_close_time_utc_then_event_ticker;contiguous_200_event_blocks",
        },
        "feature_contract": list(FEATURE_FIELDS),
        "offset_contract": list(OFFSET_FIELDS),
        "feature_rows_fingerprint": canonical_rows_fingerprint(feature_rows),
        "validation_offset_rows_fingerprint": canonical_rows_fingerprint(offset_rows),
        "candidate_probability_endpoint_rows": sum(
            1 for row in feature_rows if float(row["candidate_probability"]) in (0.0, 1.0)
        ),
        "candidate_probability_zero_rows": sum(
            1 for row in feature_rows if float(row["candidate_probability"]) == 0.0
        ),
        "candidate_probability_one_rows": sum(
            1 for row in feature_rows if float(row["candidate_probability"]) == 1.0
        ),
        "validation_event_map_fingerprint": canonical_rows_fingerprint(event_map_rows, key="event_ticker"),
        "source_file_sha256s": {name: sha256_file(path) for name, path in sorted(source_files.items())},
        "implementation_sha256s": {name: sha256_file(path) for name, path in sorted(implementation_files.items())},
        "prepared_output_sha256s": {name: sha256_file(path) for name, path in sorted(output_files.items())},
        "duplicate_preoutcome_stage_block_columns_checked_equal": True,
        "outcomes_in_feature_rows": False,
        "validation_scores_calculated": False,
        "c1_c2_outcome_rows_read_for_model2": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "strategy_v1_pnl_calculated": False,
        "execution_enabled": False,
    }
    payload["validation_preparation_fingerprint"] = canonical_sha256(payload)
    return payload

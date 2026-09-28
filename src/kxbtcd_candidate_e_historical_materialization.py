"""Checkpoint-19G frozen Candidate-E historical pre-outcome materialization helpers.

This module is network-free. It validates the materialization contract, reconstructs
the exact Checkpoint-19F untouched queue from the frozen local source files, enforces
the historical BTC/Kalshi common-row eligibility rules, creates deterministic
H1/H2/H3 block maps, and fingerprints final pre-outcome artifacts.

It never loads a new Candidate-E outcome, fits a model, or performs execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .kxbtcd_candidate_e_historical_evidence_amendment import (
    FROZEN_AMENDMENT_FINGERPRINT,
    validate_amendment,
    verify_local_universe,
)
from .kxbtcd_candidate_e_predeclaration import (
    FROZEN_PREDECLARATION_FINGERPRINT,
    btc_return_5m_bps,
    btc_strike_log_distance_bps,
    validate_candidate_e_predeclaration,
)
from .kxbtcd_independent_btc_source_policy import (
    EXPECTED_POLICY_FINGERPRINT,
    disagreement_bps,
    load_and_validate_policy,
)

DEFAULT_CONTRACT_PATH = Path("configs/kxbtcd_candidate_e_historical_materialization_contract.json")
FROZEN_CONTRACT_FINGERPRINT = "cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145"
EXPECTED_REFERENCE_MATERIALIZATION_FINGERPRINT = "f9a2459f81b1bb90e1ff55d099e837cb47c78c6586195759d55b5029d676bdb5"
SCHEMA_VERSION = "kxbtcd_candidate_e_historical_materialization_contract.v1"
ROW_SCHEMA_VERSION = "kxbtcd_candidate_e_historical_preoutcome_row.v1"
EVENT_SCHEMA_VERSION = "kxbtcd_candidate_e_historical_event_materialization.v1"
ANCHOR_SCHEMA_VERSION = "kxbtcd_candidate_e_historical_anchor_materialization.v1"
COHORT_MAP_SCHEMA_VERSION = "kxbtcd_candidate_e_historical_cohort_map.v1"
EXCLUSION_SCHEMA_VERSION = "kxbtcd_candidate_e_historical_event_exclusion.v1"

STRUCTURAL_ROLES = ("q10", "q30", "q50", "q70", "q90")
TTC_TARGET_MINUTES = (55, 50, 45, 40, 35, 30)
STAGES = ("H1", "H2", "H3")
STAGE_TARGETS = {"H1": 1500, "H2": 750, "H3": 750}
BLOCK_COUNTS = {"H1": 7, "H2": 5, "H3": 5}
TOTAL_TARGET_EVENTS = 3000
UNTOUCHED_EVENT_COUNT = 9431
RAW_QUEUE_CONSUMPTION_LIMIT = 4431
MINIMUM_UNALLOCATED_TAIL = 5000
MAX_DISAGREEMENT_BPS = 5.0
MINIMUM_ELIGIBLE_ANCHORS = 4

# The historical market API can contain these fields. They may exist only in the
# immutable raw archive. They must never be projected into research metadata.
FORBIDDEN_SOURCE_OUTCOME_FIELDS = frozenset(
    {
        "result",
        "outcome",
        "label",
        "y",
        "settlement_value",
        "settlement_value_dollars",
        "yes_settlement_value_dollars",
        "expiration_value",
        "settlement_ts",
        "resolved_yes",
        "settled_yes",
    }
)

MARKET_METADATA_ALLOWLIST = (
    "event_ticker",
    "ticker",
    "rules_primary",
    "rules_secondary",
    "close_time",
    "strike_type",
    "floor_strike",
    "functional_strike",
)

PREOUTCOME_ROW_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
    "stage",
    "block_id",
    "structural_role",
    "market_ticker",
    "strike_dollars",
    "ttc_target_minutes",
    "decision_target_utc",
    "kalshi_quote_end_period_ts",
    "kalshi_quote_staleness_seconds",
    "yes_bid",
    "yes_ask",
    "spread",
    "q_market",
    "coinbase_current_minute_start_utc",
    "coinbase_current_price",
    "kraken_current_price",
    "current_disagreement_bps",
    "coinbase_lookback_minute_start_utc",
    "coinbase_lookback_price",
    "kraken_lookback_price",
    "lookback_disagreement_bps",
    "d_BTC",
    "r_5m",
    "event_row_weight",
    "raw_observation_refs",
)

COHORT_MAP_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
    "stage",
    "stage_event_index_zero_based",
    "block_id",
    "eligible_anchor_count",
    "common_row_count",
    "source_chunk_run_id",
)

EXCLUSION_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
    "eligible_anchor_count",
    "common_row_count",
    "exclusion_reasons",
    "source_chunk_run_id",
)


class CandidateEHistoricalMaterializationError(RuntimeError):
    """Raised when a Checkpoint-19G pre-outcome invariant is violated."""


@dataclass(frozen=True)
class HistoricalBtcPairDecision:
    eligible: bool
    current_disagreement_bps: float | None
    lookback_disagreement_bps: float | None
    exclusion_reasons: tuple[str, ...]


def _err(message: str) -> None:
    raise CandidateEHistoricalMaterializationError(message)


def _load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEHistoricalMaterializationError(f"could not read {p}: {exc}") from exc
    if not isinstance(value, dict):
        _err(f"{p} root must be an object")
    return value


def _canonical_fingerprint(document: Mapping[str, Any]) -> str:
    payload = {k: v for k, v in document.items() if k != "contract_fingerprint"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _err(f"{name} must be non-empty UTC text")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CandidateEHistoricalMaterializationError(f"{name} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _err(f"{name} must be UTC")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CandidateEHistoricalMaterializationError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _err(f"{name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_rows_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(list(rows), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_contract(
    path: str | Path = DEFAULT_CONTRACT_PATH,
    *,
    verify_parents: bool = True,
) -> str:
    document = _load_json(path)
    if document.get("schema_version") != SCHEMA_VERSION:
        _err("historical materialization schema_version changed")
    if document.get("checkpoint_id") != "19G":
        _err("historical materialization checkpoint_id changed")
    if document.get("contract_fingerprint") != FROZEN_CONTRACT_FINGERPRINT:
        _err("historical materialization fingerprint field changed")
    if _canonical_fingerprint(document) != FROZEN_CONTRACT_FINGERPRINT:
        _err("historical materialization canonical fingerprint mismatch")

    parents = document["parents"]
    expected_parents = {
        "historical_evidence_amendment_fingerprint": FROZEN_AMENDMENT_FINGERPRINT,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "independent_btc_source_policy_fingerprint": EXPECTED_POLICY_FINGERPRINT,
        "reference_kxbtcd_materialization_fingerprint": EXPECTED_REFERENCE_MATERIALIZATION_FINGERPRINT,
    }
    if parents != expected_parents:
        _err("historical materialization parent fingerprints changed")

    queue = document["frozen_queue"]
    if queue["event_count"] != UNTOUCHED_EVENT_COUNT:
        _err("untouched queue count changed")
    if queue["fingerprint"] != "d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90":
        _err("untouched queue fingerprint changed")

    event_gate = document["event_eligibility"]
    if event_gate["scheduled_anchor_count"] != 6 or event_gate["minimum_eligible_anchor_count"] != 4:
        _err("4-of-6 event eligibility changed")
    common = document["common_candidate_row_universe"]
    if common["all_five_structural_quotes_required_per_anchor"] is not False:
        _err("per-anchor all-five-strike gate was introduced")
    if "at least one" not in common["anchor_is_eligible_when"]:
        _err("eligible-anchor common-row rule changed")

    fill = document["partition_fill"]
    observed = (fill["H1_train_events"], fill["H2_validation_events"], fill["H3_locked_test_events"])
    if observed != (1500, 750, 750):
        _err("H1/H2/H3 target counts changed")
    if fill["raw_queue_consumption_limit"] != RAW_QUEUE_CONSUMPTION_LIMIT:
        _err("raw queue consumption limit changed")
    if fill["minimum_unallocated_tail_events"] != MINIMUM_UNALLOCATED_TAIL:
        _err("unallocated reserve floor changed")

    state = document["independent_btc_historical_state"]
    if state["max_current_disagreement_bps"] != MAX_DISAGREEMENT_BPS:
        _err("current disagreement gate changed")
    if state["max_lookback_disagreement_bps"] != MAX_DISAGREEMENT_BPS:
        _err("lookback disagreement gate changed")
    for key in (
        "future_interpolation_allowed",
        "nearest_sampling_allowed",
        "carry_forward_allowed",
        "source_substitution_allowed",
    ):
        if state[key] is not False:
            _err(f"historical source rule changed: {key}")

    firewall = document["unavoidable_source_outcome_firewall"]
    if firewall["raw_payload_preserved_unchanged"] is not True:
        _err("raw-first source preservation changed")
    if firewall["forbidden_source_fields_may_affect_branching_selection_or_derived_output"] is not False:
        _err("source outcome firewall weakened")
    if firewall["derived_artifacts_may_contain_outcomes"] is not False:
        _err("derived outcome fields became authorized")

    safety = document["safety"]
    for key in (
        "candidate_e_fitting_authorized",
        "new_candidate_e_outcome_access_authorized",
        "paper_execution",
        "demo_execution",
        "real_money_execution",
        "order_creation",
        "order_cancellation",
        "transfers",
    ):
        if safety[key] is not False:
            _err(f"safety boundary changed: {key}")

    if verify_parents:
        if validate_amendment() != FROZEN_AMENDMENT_FINGERPRINT:
            _err("local 19F amendment parent failed validation")
        if validate_candidate_e_predeclaration() != FROZEN_PREDECLARATION_FINGERPRINT:
            _err("local Candidate-E predeclaration parent failed validation")
        policy = load_and_validate_policy()
        if policy.get("policy_fingerprint") != EXPECTED_POLICY_FINGERPRINT:
            _err("local 19D-B source-policy parent failed validation")
    return FROZEN_CONTRACT_FINGERPRINT


def project_historical_market_metadata(source_market: Mapping[str, Any]) -> dict[str, Any]:
    """Project an outcome-bearing historical market payload onto metadata only.

    The function deliberately ignores every field outside MARKET_METADATA_ALLOWLIST.
    This means changing ``result`` or settlement-value fields cannot alter output.
    """
    if not isinstance(source_market, Mapping):
        _err("historical market source object must be a mapping")
    projected = {key: source_market.get(key) for key in MARKET_METADATA_ALLOWLIST}
    required = ("event_ticker", "ticker", "rules_primary", "rules_secondary", "close_time", "strike_type")
    for key in required:
        value = projected.get(key)
        if not isinstance(value, str) or not value.strip():
            _err(f"historical market metadata missing required field {key}")
    if all(projected.get(key) in (None, "") for key in ("floor_strike", "functional_strike")):
        _err("historical market metadata has no threshold strike field")
    return projected


def load_frozen_untouched_queue(
    amendment_path: str | Path = "configs/kxbtcd_candidate_e_historical_evidence_amendment.json",
) -> tuple[dict[str, Any], ...]:
    """Reconstruct the exact 19F outcome-untouched queue using event identities only."""
    verify_local_universe(amendment_path)
    amendment = _load_json(amendment_path)
    source_files = amendment["frozen_universe"]["source_files"]
    census_path = Path(source_files["census"]["path"])
    with census_path.open("r", encoding="utf-8-sig", newline="") as handle:
        census = list(csv.DictReader(handle))

    exposed: set[str] = set()
    for item in source_files["exposure_files"]:
        path = Path(item["path"])
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "event_ticker" not in (reader.fieldnames or []):
                _err(f"event_ticker missing from exposure source {path}")
            for row in reader:
                ticker = (row.get("event_ticker") or "").strip()
                if ticker:
                    exposed.add(ticker)

    queue = [
        {
            "event_ticker": row["event_ticker"].strip(),
            "strike_date_utc": row["strike_date_utc"].strip(),
        }
        for row in census
        if row["event_ticker"].strip() not in exposed
    ]
    queue.sort(key=lambda row: (row["strike_date_utc"], row["event_ticker"]))
    if len(queue) != UNTOUCHED_EVENT_COUNT:
        _err(f"untouched queue count mismatch: {len(queue)}")
    queue_fp = hashlib.sha256(
        "".join(f"{row['strike_date_utc']}|{row['event_ticker']}\n" for row in queue).encode("utf-8")
    ).hexdigest()
    if queue_fp != amendment["frozen_universe"]["untouched_chronological_universe_sha256"]:
        _err("untouched queue fingerprint mismatch")
    for index, row in enumerate(queue):
        row["queue_index_zero_based"] = index
    return tuple(queue)


def decision_target_utc(event_close_time_utc: str, ttc_target_minutes: int) -> str:
    if ttc_target_minutes not in TTC_TARGET_MINUTES:
        _err(f"unsupported TTC target: {ttc_target_minutes}")
    close = _parse_utc(event_close_time_utc, "event_close_time_utc")
    return _format_utc(close - timedelta(minutes=ttc_target_minutes))


def evaluate_historical_btc_pair(
    *,
    coinbase_current_price: Any | None,
    kraken_current_price: Any | None,
    coinbase_lookback_price: Any | None,
    kraken_lookback_price: Any | None,
) -> HistoricalBtcPairDecision:
    reasons: list[str] = []

    def positive(value: Any | None, reason: str) -> float | None:
        if value is None:
            reasons.append(reason)
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            reasons.append(reason + "_invalid")
            return None
        if not math.isfinite(numeric) or numeric <= 0:
            reasons.append(reason + "_invalid")
            return None
        return numeric

    cb_now = positive(coinbase_current_price, "missing_coinbase_current")
    kr_now = positive(kraken_current_price, "missing_kraken_current")
    cb_back = positive(coinbase_lookback_price, "missing_coinbase_lookback")
    kr_back = positive(kraken_lookback_price, "missing_kraken_lookback")

    current_disagreement = None
    if cb_now is not None and kr_now is not None:
        current_disagreement = disagreement_bps(cb_now, kr_now)
        if current_disagreement > MAX_DISAGREEMENT_BPS:
            reasons.append("current_cross_source_disagreement_above_5bp")

    lookback_disagreement = None
    if cb_back is not None and kr_back is not None:
        lookback_disagreement = disagreement_bps(cb_back, kr_back)
        if lookback_disagreement > MAX_DISAGREEMENT_BPS:
            reasons.append("lookback_cross_source_disagreement_above_5bp")

    return HistoricalBtcPairDecision(
        eligible=not reasons,
        current_disagreement_bps=current_disagreement,
        lookback_disagreement_bps=lookback_disagreement,
        exclusion_reasons=tuple(reasons),
    )


def anchor_is_eligible(*, btc_pair_eligible: bool, valid_common_row_count: int) -> bool:
    if valid_common_row_count < 0:
        _err("valid_common_row_count cannot be negative")
    return bool(btc_pair_eligible and valid_common_row_count >= 1)


def event_is_eligible(anchor_eligibility: Sequence[bool]) -> tuple[bool, int]:
    if len(anchor_eligibility) != len(TTC_TARGET_MINUTES):
        _err("event eligibility requires exactly six scheduled anchors")
    count = sum(bool(value) for value in anchor_eligibility)
    return count >= MINIMUM_ELIGIBLE_ANCHORS, count


def build_common_candidate_row(
    *,
    event_ticker: str,
    event_close_time_utc: str,
    queue_index_zero_based: int,
    structural_role: str,
    market_ticker: str,
    strike_dollars: Any,
    ttc_target_minutes: int,
    decision_target: str,
    kalshi_anchor: Mapping[str, Any],
    coinbase_current_minute_start_utc: str,
    coinbase_current_price: Any,
    kraken_current_price: Any,
    current_disagreement_bps: float,
    coinbase_lookback_minute_start_utc: str,
    coinbase_lookback_price: Any,
    kraken_lookback_price: Any,
    lookback_disagreement_bps: float,
    raw_observation_refs: Sequence[str],
) -> dict[str, Any]:
    if structural_role not in STRUCTURAL_ROLES:
        _err(f"unknown structural role: {structural_role}")
    if ttc_target_minutes not in TTC_TARGET_MINUTES:
        _err(f"unknown TTC target: {ttc_target_minutes}")
    strike = float(_decimal(strike_dollars, "strike_dollars"))
    cb_now = float(_decimal(coinbase_current_price, "coinbase_current_price"))
    cb_back = float(_decimal(coinbase_lookback_price, "coinbase_lookback_price"))
    bid = _decimal(kalshi_anchor["yes_bid"], "yes_bid")
    ask = _decimal(kalshi_anchor["yes_ask"], "yes_ask")
    midpoint = _decimal(kalshi_anchor["midpoint"], "midpoint")
    spread = _decimal(kalshi_anchor["spread"], "spread")
    if bid < 0 or ask > 1 or bid > ask:
        _err("Kalshi common-row quote is invalid")
    if abs(midpoint - (bid + ask) / Decimal("2")) > Decimal("1e-9"):
        _err("Kalshi midpoint mismatch")
    if abs(spread - (ask - bid)) > Decimal("1e-9"):
        _err("Kalshi spread mismatch")
    refs = list(dict.fromkeys(str(value) for value in raw_observation_refs if str(value).strip()))
    if not refs:
        _err("common row requires raw observation lineage")
    return {
        "schema_version": ROW_SCHEMA_VERSION,
        "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "event_ticker": event_ticker,
        "event_close_time_utc": event_close_time_utc,
        "queue_index_zero_based": int(queue_index_zero_based),
        "stage": "",
        "block_id": "",
        "structural_role": structural_role,
        "market_ticker": market_ticker,
        "strike_dollars": _decimal_text(_decimal(strike_dollars, "strike_dollars")),
        "ttc_target_minutes": int(ttc_target_minutes),
        "decision_target_utc": decision_target,
        "kalshi_quote_end_period_ts": int(kalshi_anchor["selected_end_period_ts"]),
        "kalshi_quote_staleness_seconds": int(kalshi_anchor["staleness_seconds"]),
        "yes_bid": _decimal_text(bid),
        "yes_ask": _decimal_text(ask),
        "spread": _decimal_text(spread),
        "q_market": _decimal_text(midpoint),
        "coinbase_current_minute_start_utc": coinbase_current_minute_start_utc,
        "coinbase_current_price": _decimal_text(_decimal(coinbase_current_price, "coinbase_current_price")),
        "kraken_current_price": _decimal_text(_decimal(kraken_current_price, "kraken_current_price")),
        "current_disagreement_bps": repr(float(current_disagreement_bps)),
        "coinbase_lookback_minute_start_utc": coinbase_lookback_minute_start_utc,
        "coinbase_lookback_price": _decimal_text(_decimal(coinbase_lookback_price, "coinbase_lookback_price")),
        "kraken_lookback_price": _decimal_text(_decimal(kraken_lookback_price, "kraken_lookback_price")),
        "lookback_disagreement_bps": repr(float(lookback_disagreement_bps)),
        "d_BTC": repr(btc_strike_log_distance_bps(cb_now, strike)),
        "r_5m": repr(btc_return_5m_bps(cb_now, cb_back)),
        "event_row_weight": "",
        "raw_observation_refs": refs,
    }


def balanced_block_ids(event_count: int, block_count: int, *, prefix: str = "B") -> tuple[str, ...]:
    if event_count < block_count or block_count <= 0:
        _err("block map needs at least one event per block")
    base, remainder = divmod(event_count, block_count)
    result: list[str] = []
    for index in range(block_count):
        size = base + (1 if index < remainder else 0)
        result.extend([f"{prefix}{index}"] * size)
    if len(result) != event_count:
        _err("block map size mismatch")
    return tuple(result)


def assign_cohorts(
    event_rows: Sequence[Mapping[str, Any]],
    *,
    require_complete: bool = True,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], dict[str, Any]]:
    """Assign first 3,000 eligible events to H1/H2/H3 without outcomes.

    ``event_rows`` must be a contiguous prefix of the frozen untouched queue.
    Ineligible events consume queue runway but do not fill a stage.
    """
    if not event_rows:
        _err("event_rows must not be empty")
    expected_index = 0
    selected_by_stage: dict[str, list[Mapping[str, Any]]] = {stage: [] for stage in STAGES}
    exclusions: list[dict[str, Any]] = []
    last_consumed_index = -1

    for original in event_rows:
        row = dict(original)
        index = int(row["queue_index_zero_based"])
        if index != expected_index:
            _err(f"event materialization is not a contiguous queue prefix at index {expected_index}")
        expected_index += 1
        if index >= RAW_QUEUE_CONSUMPTION_LIMIT:
            _err("Candidate-E materialization would consume the protected 5,000-event tail")
        last_consumed_index = index

        eligible = bool(row["eligible_event"])
        eligible_anchor_count = int(row["eligible_anchor_count"])
        common_row_count = int(row["common_row_count"])
        if eligible and (eligible_anchor_count < MINIMUM_ELIGIBLE_ANCHORS or common_row_count <= 0):
            _err("event marked eligible without satisfying common-row/anchor gate")
        if not eligible:
            exclusions.append(
                {
                    "schema_version": EXCLUSION_SCHEMA_VERSION,
                    "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                    "event_ticker": row["event_ticker"],
                    "event_close_time_utc": row["event_close_time_utc"],
                    "queue_index_zero_based": index,
                    "eligible_anchor_count": eligible_anchor_count,
                    "common_row_count": common_row_count,
                    "exclusion_reasons": list(row.get("exclusion_reasons", [])),
                    "source_chunk_run_id": row["source_chunk_run_id"],
                }
            )
            continue

        stage = next((s for s in STAGES if len(selected_by_stage[s]) < STAGE_TARGETS[s]), None)
        if stage is None:
            break
        selected_by_stage[stage].append(row)
        if sum(len(selected_by_stage[s]) for s in STAGES) == TOTAL_TARGET_EVENTS:
            break

    complete = all(len(selected_by_stage[s]) == STAGE_TARGETS[s] for s in STAGES)
    if require_complete and not complete:
        _err(
            "materialization prefix did not fill 1,500/750/750 eligible events before the protected reserve boundary"
        )

    cohort_map: list[dict[str, Any]] = []
    for stage in STAGES:
        events = selected_by_stage[stage]
        if not events:
            continue
        block_ids = balanced_block_ids(len(events), BLOCK_COUNTS[stage])
        for stage_index, (row, block_id) in enumerate(zip(events, block_ids)):
            cohort_map.append(
                {
                    "schema_version": COHORT_MAP_SCHEMA_VERSION,
                    "contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
                    "event_ticker": row["event_ticker"],
                    "event_close_time_utc": row["event_close_time_utc"],
                    "queue_index_zero_based": int(row["queue_index_zero_based"]),
                    "stage": stage,
                    "stage_event_index_zero_based": stage_index,
                    "block_id": block_id,
                    "eligible_anchor_count": int(row["eligible_anchor_count"]),
                    "common_row_count": int(row["common_row_count"]),
                    "source_chunk_run_id": row["source_chunk_run_id"],
                }
            )

    consumed = last_consumed_index + 1
    summary = {
        "complete": complete,
        "queue_events_consumed": consumed,
        "unallocated_tail_events": UNTOUCHED_EVENT_COUNT - consumed,
        "eligible_counts": {stage: len(selected_by_stage[stage]) for stage in STAGES},
        "excluded_event_count": len(exclusions),
    }
    if summary["unallocated_tail_events"] < MINIMUM_UNALLOCATED_TAIL:
        _err("protected unallocated tail fell below 5,000 events")
    return tuple(cohort_map), tuple(exclusions), summary


def attach_stage_block_and_weights(
    rows: Sequence[Mapping[str, Any]],
    cohort_map: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    mapping = {row["event_ticker"]: (row["stage"], row["block_id"]) for row in cohort_map}
    counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for original in rows:
        event = original["event_ticker"]
        if event not in mapping:
            continue
        row = dict(original)
        row["stage"], row["block_id"] = mapping[event]
        counts[event] = counts.get(event, 0) + 1
        selected.append(row)
    for row in selected:
        row["event_row_weight"] = _decimal_text(Decimal(1) / Decimal(counts[row["event_ticker"]]))
        if set(row) != set(PREOUTCOME_ROW_FIELDS):
            missing = sorted(set(PREOUTCOME_ROW_FIELDS) - set(row))
            extra = sorted(set(row) - set(PREOUTCOME_ROW_FIELDS))
            _err(f"preoutcome row schema mismatch; missing={missing}, extra={extra}")
        if FORBIDDEN_SOURCE_OUTCOME_FIELDS.intersection(row):
            _err("preoutcome row contains forbidden outcome fields")
    selected.sort(
        key=lambda row: (
            STAGES.index(row["stage"]),
            row["event_close_time_utc"],
            row["event_ticker"],
            -row["ttc_target_minutes"],
            STRUCTURAL_ROLES.index(row["structural_role"]),
        )
    )
    return tuple(selected)


def validate_block_coverage(
    cohort_map: Sequence[Mapping[str, Any]],
    preoutcome_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    event_to_block = {row["event_ticker"]: (row["stage"], row["block_id"]) for row in cohort_map}
    coverage: dict[tuple[str, str], dict[str, set[Any]]] = {}
    for row in preoutcome_rows:
        key = event_to_block.get(row["event_ticker"])
        if key is None:
            _err("preoutcome row event absent from cohort map")
        bucket = coverage.setdefault(key, {"roles": set(), "ttc": set()})
        bucket["roles"].add(row["structural_role"])
        bucket["ttc"].add(int(row["ttc_target_minutes"]))

    required_keys: set[tuple[str, str]] = set()
    for stage in STAGES:
        for i in range(BLOCK_COUNTS[stage]):
            if stage == "H1" and i < 2:
                # 19E structural advancement gate applies to H1 score blocks B2-B6.
                continue
            required_keys.add((stage, f"B{i}"))
    missing: list[str] = []
    for key in sorted(required_keys):
        bucket = coverage.get(key, {"roles": set(), "ttc": set()})
        if bucket["roles"] != set(STRUCTURAL_ROLES):
            missing.append(f"{key[0]}:{key[1]} missing structural roles")
        if bucket["ttc"] != set(TTC_TARGET_MINUTES):
            missing.append(f"{key[0]}:{key[1]} missing TTC targets")
    if missing:
        _err("block structural coverage failed: " + "; ".join(missing))
    return {
        f"{stage}:{block}": {
            "structural_roles": sorted(bucket["roles"]),
            "ttc_targets": sorted(bucket["ttc"], reverse=True),
        }
        for (stage, block), bucket in sorted(coverage.items())
    }


def final_freeze_fingerprints(
    *,
    cohort_map: Sequence[Mapping[str, Any]],
    preoutcome_rows: Sequence[Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    return {
        "cohort_map_fingerprint": canonical_rows_fingerprint(cohort_map),
        "row_universe_fingerprint": canonical_rows_fingerprint(preoutcome_rows),
        "exclusion_fingerprint": canonical_rows_fingerprint(exclusions),
    }


validate_contract(verify_parents=False)

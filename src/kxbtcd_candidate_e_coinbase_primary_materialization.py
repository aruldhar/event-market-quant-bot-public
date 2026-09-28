"""Checkpoint-19H-B Coinbase-primary Candidate-E pre-outcome helpers.

This module layers a pre-outcome source-policy amendment on top of the frozen
Checkpoint-19G historical materialization contract. Candidate-E features remain
unchanged and Coinbase remains the feature source. Kraken is no longer required
for historical row or anchor eligibility and is not part of this canonical
materialization path.

The module is network-free. It never loads outcomes, fits Candidate E, or performs
execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_historical_materialization import (
    ANCHOR_SCHEMA_VERSION as PARENT_ANCHOR_SCHEMA_VERSION,
    COHORT_MAP_FIELDS as PARENT_COHORT_MAP_FIELDS,
    EVENT_SCHEMA_VERSION as PARENT_EVENT_SCHEMA_VERSION,
    EXCLUSION_FIELDS as PARENT_EXCLUSION_FIELDS,
    FROZEN_CONTRACT_FINGERPRINT,
    MINIMUM_ELIGIBLE_ANCHORS,
    PREOUTCOME_ROW_FIELDS as PARENT_PREOUTCOME_ROW_FIELDS,
    RAW_QUEUE_CONSUMPTION_LIMIT,
    STAGE_TARGETS,
    TTC_TARGET_MINUTES,
    CandidateEHistoricalMaterializationError,
    assign_cohorts as parent_assign_cohorts,
    attach_stage_block_and_weights as parent_attach_stage_block_and_weights,
    build_common_candidate_row,
    canonical_rows_fingerprint,
    event_is_eligible,
    final_freeze_fingerprints as parent_final_freeze_fingerprints,
    load_frozen_untouched_queue,
    validate_block_coverage,
    validate_contract,
)

DEFAULT_AMENDMENT_PATH = Path("configs/kxbtcd_candidate_e_coinbase_primary_amendment.json")
AMENDMENT_SCHEMA_VERSION = "kxbtcd_candidate_e_coinbase_primary_amendment.v1"
FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT = "b08da00a8f66817d9e3b600ccf091c8a4fc1ee92a0bed1c821d23bc321d9faba"

ROW_SCHEMA_VERSION = "kxbtcd_candidate_e_coinbase_primary_preoutcome_row.v1"
EVENT_SCHEMA_VERSION = "kxbtcd_candidate_e_coinbase_primary_event_materialization.v1"
ANCHOR_SCHEMA_VERSION = "kxbtcd_candidate_e_coinbase_primary_anchor_materialization.v1"
COHORT_MAP_SCHEMA_VERSION = "kxbtcd_candidate_e_coinbase_primary_cohort_map.v1"
EXCLUSION_SCHEMA_VERSION = "kxbtcd_candidate_e_coinbase_primary_event_exclusion.v1"

# Preserve the familiar Candidate-E row surface while adding an explicit amendment
# identity. Kraken diagnostic columns remain for downstream compatibility, but this
# materialization intentionally stores them blank because Kraken is not on the
# canonical Candidate-E source path.
PREOUTCOME_ROW_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "source_amendment_fingerprint",
    *tuple(field for field in PARENT_PREOUTCOME_ROW_FIELDS if field not in {"schema_version", "contract_fingerprint"}),
)

COHORT_MAP_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "source_amendment_fingerprint",
    *tuple(field for field in PARENT_COHORT_MAP_FIELDS if field not in {"schema_version", "contract_fingerprint"}),
)

EXCLUSION_FIELDS = (
    "schema_version",
    "contract_fingerprint",
    "source_amendment_fingerprint",
    *tuple(field for field in PARENT_EXCLUSION_FIELDS if field not in {"schema_version", "contract_fingerprint"}),
)


@dataclass(frozen=True)
class HistoricalCoinbaseStateDecision:
    eligible: bool
    exclusion_reasons: tuple[str, ...]


def _canonical_amendment_fingerprint(document: Mapping[str, Any]) -> str:
    payload = {k: v for k, v in document.items() if k != "amendment_fingerprint"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_coinbase_primary_amendment(
    path: str | Path = DEFAULT_AMENDMENT_PATH,
    *,
    verify_parent: bool = True,
) -> str:
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEHistoricalMaterializationError(f"could not read Coinbase-primary amendment {p}: {exc}") from exc
    if not isinstance(doc, dict):
        raise CandidateEHistoricalMaterializationError("Coinbase-primary amendment root must be object")
    if doc.get("schema_version") != AMENDMENT_SCHEMA_VERSION:
        raise CandidateEHistoricalMaterializationError("Coinbase-primary amendment schema changed")
    if doc.get("checkpoint_id") != "19H-B":
        raise CandidateEHistoricalMaterializationError("Coinbase-primary amendment checkpoint changed")
    if doc.get("parent_contract_fingerprint") != FROZEN_CONTRACT_FINGERPRINT:
        raise CandidateEHistoricalMaterializationError("Coinbase-primary amendment parent contract changed")
    if doc.get("amendment_fingerprint") != FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT:
        raise CandidateEHistoricalMaterializationError("Coinbase-primary amendment fingerprint field changed")
    if _canonical_amendment_fingerprint(doc) != FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT:
        raise CandidateEHistoricalMaterializationError("Coinbase-primary amendment canonical fingerprint mismatch")

    source = doc.get("source_policy")
    if not isinstance(source, Mapping):
        raise CandidateEHistoricalMaterializationError("Coinbase-primary source policy missing")
    if source.get("historical_required_primary_source") != "coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1":
        raise CandidateEHistoricalMaterializationError("Coinbase primary source changed")
    if source.get("cross_source_disagreement_veto_enabled") is not False:
        raise CandidateEHistoricalMaterializationError("cross-source veto was re-enabled")
    if source.get("missing_kraken_may_reject_anchor") is not False:
        raise CandidateEHistoricalMaterializationError("Kraken became blocking again")
    if source.get("kraken_role") != "optional diagnostic only; not required for Candidate-E row or anchor eligibility":
        raise CandidateEHistoricalMaterializationError("Kraken role changed")
    for key in (
        "future_interpolation_allowed",
        "nearest_sampling_allowed",
        "carry_forward_allowed",
        "source_substitution_allowed",
    ):
        if source.get(key) is not False:
            raise CandidateEHistoricalMaterializationError(f"Coinbase historical source rule changed: {key}")

    event = doc.get("event_eligibility")
    if not isinstance(event, Mapping):
        raise CandidateEHistoricalMaterializationError("Coinbase-primary event eligibility missing")
    if (event.get("scheduled_anchor_count"), event.get("minimum_eligible_anchor_count")) != (6, 4):
        raise CandidateEHistoricalMaterializationError("4-of-6 event gate changed")
    if event.get("kraken_required") is not False:
        raise CandidateEHistoricalMaterializationError("Kraken became required")

    partitions = doc.get("partitions")
    if not isinstance(partitions, Mapping):
        raise CandidateEHistoricalMaterializationError("Coinbase-primary partitions missing")
    observed = (
        partitions.get("H1_train_events"),
        partitions.get("H2_validation_events"),
        partitions.get("H3_locked_test_events"),
    )
    if observed != (1500, 750, 750):
        raise CandidateEHistoricalMaterializationError("H1/H2/H3 counts changed")
    if partitions.get("raw_queue_consumption_limit") != RAW_QUEUE_CONSUMPTION_LIMIT:
        raise CandidateEHistoricalMaterializationError("queue consumption limit changed")
    if partitions.get("minimum_unallocated_tail_events") != 5000:
        raise CandidateEHistoricalMaterializationError("protected reserve floor changed")

    safety = doc.get("safety")
    if not isinstance(safety, Mapping):
        raise CandidateEHistoricalMaterializationError("Coinbase-primary safety section missing")
    if safety.get("new_candidate_e_outcome_access_authorized") is not False:
        raise CandidateEHistoricalMaterializationError("new Candidate-E outcome access became authorized")
    if safety.get("candidate_e_fitting_authorized") is not False:
        raise CandidateEHistoricalMaterializationError("Candidate-E fitting became authorized")
    if safety.get("orders_placed") != 0:
        raise CandidateEHistoricalMaterializationError("amendment reports orders")

    if verify_parent:
        if validate_contract() != FROZEN_CONTRACT_FINGERPRINT:
            raise CandidateEHistoricalMaterializationError("parent 19G contract failed validation")
    return FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT


def evaluate_historical_coinbase_state(
    *,
    coinbase_current_price: Any | None,
    coinbase_lookback_price: Any | None,
) -> HistoricalCoinbaseStateDecision:
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

    positive(coinbase_current_price, "missing_coinbase_current")
    positive(coinbase_lookback_price, "missing_coinbase_lookback")
    return HistoricalCoinbaseStateDecision(eligible=not reasons, exclusion_reasons=tuple(reasons))


def build_coinbase_primary_candidate_row(
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
    coinbase_lookback_minute_start_utc: str,
    coinbase_lookback_price: Any,
    raw_observation_refs: Sequence[str],
) -> dict[str, Any]:
    # The parent builder computes Candidate-E d_BTC/r_5m from Coinbase. Supplying
    # Coinbase again in its legacy Kraken slots changes no feature value; those
    # diagnostic fields are then blanked before the v2 row is returned.
    parent = build_common_candidate_row(
        event_ticker=event_ticker,
        event_close_time_utc=event_close_time_utc,
        queue_index_zero_based=queue_index_zero_based,
        structural_role=structural_role,
        market_ticker=market_ticker,
        strike_dollars=strike_dollars,
        ttc_target_minutes=ttc_target_minutes,
        decision_target=decision_target,
        kalshi_anchor=kalshi_anchor,
        coinbase_current_minute_start_utc=coinbase_current_minute_start_utc,
        coinbase_current_price=coinbase_current_price,
        kraken_current_price=coinbase_current_price,
        current_disagreement_bps=0.0,
        coinbase_lookback_minute_start_utc=coinbase_lookback_minute_start_utc,
        coinbase_lookback_price=coinbase_lookback_price,
        kraken_lookback_price=coinbase_lookback_price,
        lookback_disagreement_bps=0.0,
        raw_observation_refs=raw_observation_refs,
    )
    parent["schema_version"] = ROW_SCHEMA_VERSION
    parent["source_amendment_fingerprint"] = FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT
    parent["kraken_current_price"] = ""
    parent["current_disagreement_bps"] = ""
    parent["kraken_lookback_price"] = ""
    parent["lookback_disagreement_bps"] = ""
    ordered = {field: parent[field] for field in PREOUTCOME_ROW_FIELDS}
    return ordered


def assign_cohorts(
    event_rows: Sequence[Mapping[str, Any]],
    *,
    require_complete: bool = True,
):
    stripped = []
    for original in event_rows:
        row = dict(original)
        if row.get("source_amendment_fingerprint") != FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT:
            raise CandidateEHistoricalMaterializationError("event row amendment fingerprint mismatch")
        row.pop("source_amendment_fingerprint", None)
        row["schema_version"] = PARENT_EVENT_SCHEMA_VERSION
        stripped.append(row)
    cohort, exclusions, summary = parent_assign_cohorts(stripped, require_complete=require_complete)

    cohort_v2 = []
    for original in cohort:
        row = dict(original)
        row["schema_version"] = COHORT_MAP_SCHEMA_VERSION
        row["source_amendment_fingerprint"] = FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT
        cohort_v2.append({field: row[field] for field in COHORT_MAP_FIELDS})

    exclusions_v2 = []
    for original in exclusions:
        row = dict(original)
        row["schema_version"] = EXCLUSION_SCHEMA_VERSION
        row["source_amendment_fingerprint"] = FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT
        exclusions_v2.append({field: row[field] for field in EXCLUSION_FIELDS})
    return tuple(cohort_v2), tuple(exclusions_v2), summary


def attach_stage_block_and_weights(
    rows: Sequence[Mapping[str, Any]],
    cohort_map: Sequence[Mapping[str, Any]],
):
    stripped_rows = []
    for original in rows:
        row = dict(original)
        if row.get("source_amendment_fingerprint") != FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT:
            raise CandidateEHistoricalMaterializationError("preoutcome row amendment fingerprint mismatch")
        row.pop("source_amendment_fingerprint", None)
        row["schema_version"] = "kxbtcd_candidate_e_historical_preoutcome_row.v1"
        stripped_rows.append(row)

    stripped_cohort = []
    for original in cohort_map:
        row = dict(original)
        row.pop("source_amendment_fingerprint", None)
        row["schema_version"] = "kxbtcd_candidate_e_historical_cohort_map.v1"
        stripped_cohort.append(row)

    parent_rows = parent_attach_stage_block_and_weights(stripped_rows, stripped_cohort)
    result = []
    for original in parent_rows:
        row = dict(original)
        row["schema_version"] = ROW_SCHEMA_VERSION
        row["source_amendment_fingerprint"] = FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT
        result.append({field: row[field] for field in PREOUTCOME_ROW_FIELDS})
    return tuple(result)


def final_freeze_fingerprints(*, cohort_map, preoutcome_rows, exclusions):
    return {
        "cohort_map_fingerprint": canonical_rows_fingerprint(cohort_map),
        "row_universe_fingerprint": canonical_rows_fingerprint(preoutcome_rows),
        "exclusion_fingerprint": canonical_rows_fingerprint(exclusions),
    }


__all__ = [
    "ANCHOR_SCHEMA_VERSION",
    "COHORT_MAP_FIELDS",
    "COHORT_MAP_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "EXCLUSION_FIELDS",
    "EXCLUSION_SCHEMA_VERSION",
    "FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT",
    "FROZEN_CONTRACT_FINGERPRINT",
    "MINIMUM_ELIGIBLE_ANCHORS",
    "PREOUTCOME_ROW_FIELDS",
    "RAW_QUEUE_CONSUMPTION_LIMIT",
    "ROW_SCHEMA_VERSION",
    "STAGE_TARGETS",
    "TTC_TARGET_MINUTES",
    "assign_cohorts",
    "attach_stage_block_and_weights",
    "build_coinbase_primary_candidate_row",
    "evaluate_historical_coinbase_state",
    "event_is_eligible",
    "final_freeze_fingerprints",
    "load_frozen_untouched_queue",
    "validate_block_coverage",
    "validate_coinbase_primary_amendment",
]

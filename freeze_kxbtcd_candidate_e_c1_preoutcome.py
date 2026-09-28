"""Offline C1 freezer. Reads only completed outcome-blind C1 chunks."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from collect_kxbtcd_candidate_e_c1_materialization_chunk import validated_prior_progress
from src.kxbtcd_candidate_e_c1_preparation import (
    C1_CHUNK_ROOT,
    C1_ELIGIBLE_EVENT_TARGET,
    C1_FROZEN_ROOT,
    C1_SUBBLOCK_COUNT,
    C1_VALIDATION_FREEZE_PATH,
    DISTANCE_CANDIDATE_ID,
    MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
    PARENT_21A_PROTOCOL_FINGERPRINT,
    PARENT_H3_RESULT_FINGERPRINT,
    R0_MODEL_PATH,
    STRICT_TAIL_START_INDEX,
    UNTOUCHED_QUEUE_EVENT_COUNT,
    CandidateEC1PreparationError,
    _canonical_sha256,
    _read_json,
    _write_json_atomic,
    assert_runtime_checkout_is_frozen_21b_a,
    load_and_validate_r0_model,
    c1_subblock_for_eligible_rank,
    strict_tail_remaining_after_end_index,
)

COHORT_FIELDS = (
    "schema_version",
    "stage",
    "block_id",
    "event_rank_zero_based",
    "event_ticker",
    "event_close_time_utc",
    "queue_index_zero_based",
)
ROW_EXTRA_FIELDS = ("stage", "block_id", "c1_event_rank_zero_based")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def main() -> int:
    repo = Path(".").resolve()
    _, implementation_freeze = assert_runtime_checkout_is_frozen_21b_a(repo)
    processed, eligible, _ = validated_prior_progress(repo)
    if eligible < C1_ELIGIBLE_EVENT_TARGET:
        print(f"C1 freeze readiness: NOT READY ({eligible}/{C1_ELIGIBLE_EVENT_TARGET} eligible)")
        return 10
    if eligible != C1_ELIGIBLE_EVENT_TARGET:
        raise CandidateEC1PreparationError("C1 materialization exceeded exact eligible target")

    end_index = STRICT_TAIL_START_INDEX + processed
    remaining = strict_tail_remaining_after_end_index(end_index)
    if remaining < MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION:
        raise CandidateEC1PreparationError("C1 materialization violated the 21A strict-tail floor")

    event_files = sorted((repo / C1_CHUNK_ROOT).glob("*_events.csv"))
    all_events: list[dict[str, str]] = []
    all_rows: list[dict[str, str]] = []
    for event_path in event_files:
        run_id = event_path.name[: -len("_events.csv")]
        all_events.extend(_read_csv(event_path))
        row_path = event_path.with_name(f"{run_id}_rows.csv")
        if not row_path.is_file():
            raise CandidateEC1PreparationError(f"missing C1 row artifact {row_path}")
        all_rows.extend(_read_csv(row_path))
    all_events.sort(key=lambda row: int(row["queue_index_zero_based"]))
    eligible_events = [row for row in all_events if row["eligible_event"].lower() == "true"]
    if len(eligible_events) != C1_ELIGIBLE_EVENT_TARGET:
        raise CandidateEC1PreparationError("C1 eligible event count changed during freeze")

    rank_by_event: dict[str, int] = {}
    cohort_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(eligible_events):
        event = row["event_ticker"]
        if event in rank_by_event:
            raise CandidateEC1PreparationError(f"duplicate C1 event {event}")
        rank_by_event[event] = rank
        cohort_rows.append(
            {
                "schema_version": "kxbtcd_candidate_e_c1_cohort.v1",
                "stage": "C1",
                "block_id": c1_subblock_for_eligible_rank(rank),
                "event_rank_zero_based": rank,
                "event_ticker": event,
                "event_close_time_utc": row["event_close_time_utc"],
                "queue_index_zero_based": int(row["queue_index_zero_based"]),
            }
        )

    if not all_rows:
        raise CandidateEC1PreparationError("C1 freeze has no preoutcome rows")
    source_fields = tuple(all_rows[0].keys())
    frozen_rows: list[dict[str, Any]] = []
    block_roles: dict[str, set[str]] = {f"B{i}": set() for i in range(C1_SUBBLOCK_COUNT)}
    block_ttc: dict[str, set[int]] = {f"B{i}": set() for i in range(C1_SUBBLOCK_COUNT)}
    markets: dict[str, str] = {}
    for index, row in enumerate(all_rows):
        event = row["event_ticker"]
        rank = rank_by_event.get(event)
        if rank is None:
            raise CandidateEC1PreparationError(f"C1 row {index} belongs to ineligible/unselected event")
        block = c1_subblock_for_eligible_rank(rank)
        role = row["structural_role"]
        ttc = int(row["ttc_target_minutes"])
        block_roles[block].add(role)
        block_ttc[block].add(ttc)
        market = row["market_ticker"]
        previous = markets.setdefault(market, event)
        if previous != event:
            raise CandidateEC1PreparationError(f"C1 market {market} maps to multiple events")
        frozen_rows.append(
            {
                **row,
                "stage": "C1",
                "block_id": block,
                "c1_event_rank_zero_based": rank,
            }
        )

    expected_roles = {"q10", "q30", "q50", "q70", "q90"}
    expected_ttc = {55, 50, 45, 40, 35, 30}
    for block in sorted(block_roles):
        if block_roles[block] != expected_roles:
            raise CandidateEC1PreparationError(
                f"C1 {block} structural-role coverage changed: {sorted(block_roles[block])}"
            )
        if block_ttc[block] != expected_ttc:
            raise CandidateEC1PreparationError(
                f"C1 {block} TTC coverage changed: {sorted(block_ttc[block])}"
            )

    r0 = load_and_validate_r0_model(repo)
    r0_fingerprint = str(r0["champion_r0_fingerprint"])
    protocol = _read_json(repo / "configs/kxbtcd_post_h3_champion_lifecycle.v1.json")
    gate = protocol["confirmation"]["gate"]

    cohort_fingerprint = _canonical_sha256(cohort_rows)
    row_fingerprint = _canonical_sha256(frozen_rows)
    request_plan = [
        {"event_ticker": event, "market_ticker": market}
        for market, event in sorted(markets.items(), key=lambda item: (item[1], item[0]))
    ]
    payload = {
        "schema_version": "kxbtcd_candidate_e_c1_validation_freeze.v1",
        "checkpoint_id": "21B-B",
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "implementation_freeze_fingerprint": implementation_freeze["implementation_freeze_fingerprint"],
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "champion_r0_fingerprint": r0_fingerprint,
        "C1_event_count": C1_ELIGIBLE_EVENT_TARGET,
        "C1_subblocks": [f"B{i}" for i in range(C1_SUBBLOCK_COUNT)],
        "C1_events_per_subblock": 100,
        "strict_tail_start_index": STRICT_TAIL_START_INDEX,
        "strict_tail_end_index_exclusive_after_C1": end_index,
        "candidate_identities_materialized_for_C1": processed,
        "strict_untouched_tail_remaining_after_C1": remaining,
        "minimum_strict_untouched_tail_after_all_confirmation": MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
        "c1_cohort_fingerprint": cohort_fingerprint,
        "c1_preoutcome_row_fingerprint": row_fingerprint,
        "c1_preoutcome_row_count": len(frozen_rows),
        "c1_unique_market_count": len(request_plan),
        "c1_outcome_request_plan": request_plan,
        "gate": gate,
        "C1_outcomes_opened": False,
        "C2_C3_materialized": False,
        "candidate_selection_performed": False,
        "feature_or_hyperparameter_change_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["c1_validation_fingerprint"] = _canonical_sha256(payload)

    C1_FROZEN_ROOT.mkdir(parents=True, exist_ok=True)
    cohort_path = C1_FROZEN_ROOT / "c1_cohort_map.csv"
    rows_path = C1_FROZEN_ROOT / "c1_preoutcome_rows.csv"
    summary_path = C1_FROZEN_ROOT / "c1_preoutcome_freeze_summary.json"
    _write_csv(cohort_path, COHORT_FIELDS, cohort_rows)
    _write_csv(rows_path, source_fields + ROW_EXTRA_FIELDS, frozen_rows)
    _write_json_atomic(summary_path, document)
    _write_json_atomic(repo / C1_VALIDATION_FREEZE_PATH, document)

    print("Checkpoint 21B-B C1 pre-outcome freeze: PASS")
    print(f"C1 validation fingerprint: {document['c1_validation_fingerprint']}")
    print(f"C1 events: {C1_ELIGIBLE_EVENT_TARGET} (5 x 100)")
    print(f"C1 preoutcome rows: {len(frozen_rows)}")
    print(f"Candidate identities materialized: {processed}")
    print(f"Strict untouched tail remaining: {remaining}")
    print("C1 outcomes opened: 0")
    print("C2/C3 materialized: 0")
    print("Orders placed: 0")
    print(f"Validation freeze: {repo / C1_VALIDATION_FREEZE_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidateEC1PreparationError as exc:
        raise SystemExit(f"C1 pre-outcome freeze error: {exc}") from exc

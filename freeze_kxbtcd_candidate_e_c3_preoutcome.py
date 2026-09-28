"""Offline C3 freezer. Reads only completed outcome-blind C3 chunks."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from collect_kxbtcd_candidate_e_c3_materialization_chunk import (
    validated_prior_progress,
)
from src.kxbtcd_candidate_e_c3_preparation import (
    C1_RESULT_FINGERPRINT,
    C2_RESULT_FINGERPRINT,
    C3_CHUNK_ROOT,
    C3_ELIGIBLE_EVENT_TARGET,
    C3_FROZEN_ROOT,
    C3_STRICT_TAIL_START_INDEX,
    C3_SUBBLOCK_COUNT,
    C3_VALIDATION_FREEZE_PATH,
    DISTANCE_CANDIDATE_ID,
    MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
    PARENT_21A_PROTOCOL_FINGERPRINT,
    PARENT_H3_RESULT_FINGERPRINT,
    CandidateEC3PreparationError,
    _canonical_sha256,
    _read_json,
    _write_json_atomic,
    assert_runtime_checkout_is_frozen_21g_a,
    c3_subblock_for_eligible_rank,
    load_and_validate_r2_model,
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
ROW_EXTRA_FIELDS = (
    "stage",
    "block_id",
    "c3_event_rank_zero_based",
)


def _read_csv(
    path: Path,
) -> list[dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(
                handle
            )
        )


def _write_csv(
    path: Path,
    fields,
    rows,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: row[field]
                    for field
                    in fields
                }
            )


def main() -> int:
    repo = Path(".").resolve()
    (
        _,
        implementation_freeze,
    ) = (
        assert_runtime_checkout_is_frozen_21g_a(
            repo
        )
    )
    (
        processed,
        eligible,
        _,
    ) = validated_prior_progress(
        repo
    )

    if (
        eligible
        < C3_ELIGIBLE_EVENT_TARGET
    ):
        print(
            "C3 freeze readiness: "
            "NOT READY "
            f"({eligible}/"
            f"{C3_ELIGIBLE_EVENT_TARGET} "
            "eligible)"
        )
        return 10

    if (
        eligible
        != C3_ELIGIBLE_EVENT_TARGET
    ):
        raise CandidateEC3PreparationError(
            "C3 materialization exceeded "
            "exact eligible target"
        )

    end_index = (
        C3_STRICT_TAIL_START_INDEX
        + processed
    )
    remaining = (
        strict_tail_remaining_after_end_index(
            end_index
        )
    )
    if (
        remaining
        < MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
    ):
        raise CandidateEC3PreparationError(
            "C3 materialization violated "
            "the 21A strict-tail floor"
        )

    event_files = sorted(
        (
            repo
            / C3_CHUNK_ROOT
        ).glob(
            "*_events.csv"
        )
    )
    all_events: list[
        dict[str, str]
    ] = []
    all_rows: list[
        dict[str, str]
    ] = []

    for event_path in event_files:
        run_id = event_path.name[
            : -len("_events.csv")
        ]
        all_events.extend(
            _read_csv(
                event_path
            )
        )
        row_path = (
            event_path.with_name(
                f"{run_id}_rows.csv"
            )
        )
        if not row_path.is_file():
            raise CandidateEC3PreparationError(
                "missing C3 row artifact "
                f"{row_path}"
            )
        all_rows.extend(
            _read_csv(
                row_path
            )
        )

    all_events.sort(
        key=lambda row: int(
            row[
                "queue_index_zero_based"
            ]
        )
    )
    eligible_events = [
        row
        for row
        in all_events
        if row[
            "eligible_event"
        ].lower()
        == "true"
    ]
    if (
        len(eligible_events)
        != C3_ELIGIBLE_EVENT_TARGET
    ):
        raise CandidateEC3PreparationError(
            "C3 eligible event count "
            "changed during freeze"
        )

    rank_by_event: dict[
        str,
        int,
    ] = {}
    cohort_rows: list[
        dict[str, Any]
    ] = []

    for rank, row in enumerate(
        eligible_events
    ):
        event = row[
            "event_ticker"
        ]
        if event in rank_by_event:
            raise CandidateEC3PreparationError(
                f"duplicate C3 event {event}"
            )
        rank_by_event[
            event
        ] = rank
        cohort_rows.append(
            {
                "schema_version": (
                    "kxbtcd_candidate_e_c3_cohort.v1"
                ),
                "stage": "C3",
                "block_id": (
                    c3_subblock_for_eligible_rank(
                        rank
                    )
                ),
                "event_rank_zero_based": rank,
                "event_ticker": event,
                "event_close_time_utc": (
                    row[
                        "event_close_time_utc"
                    ]
                ),
                "queue_index_zero_based": int(
                    row[
                        "queue_index_zero_based"
                    ]
                ),
            }
        )

    if not all_rows:
        raise CandidateEC3PreparationError(
            "C3 freeze has no preoutcome rows"
        )

    source_fields = tuple(
        all_rows[0].keys()
    )
    frozen_rows: list[
        dict[str, Any]
    ] = []
    block_roles: dict[
        str,
        set[str],
    ] = {
        f"B{i}": set()
        for i
        in range(
            C3_SUBBLOCK_COUNT
        )
    }
    block_ttc: dict[
        str,
        set[int],
    ] = {
        f"B{i}": set()
        for i
        in range(
            C3_SUBBLOCK_COUNT
        )
    }
    markets: dict[
        str,
        str,
    ] = {}

    for index, row in enumerate(
        all_rows
    ):
        event = row[
            "event_ticker"
        ]
        rank = rank_by_event.get(
            event
        )
        if rank is None:
            raise CandidateEC3PreparationError(
                f"C3 row {index} belongs "
                "to ineligible/unselected "
                "event"
            )
        block = (
            c3_subblock_for_eligible_rank(
                rank
            )
        )
        role = row[
            "structural_role"
        ]
        ttc = int(
            row[
                "ttc_target_minutes"
            ]
        )
        block_roles[
            block
        ].add(
            role
        )
        block_ttc[
            block
        ].add(
            ttc
        )

        market = row[
            "market_ticker"
        ]
        previous = markets.setdefault(
            market,
            event,
        )
        if previous != event:
            raise CandidateEC3PreparationError(
                f"C3 market {market} "
                "maps to multiple events"
            )

        frozen_rows.append(
            {
                **row,
                "stage": "C3",
                "block_id": block,
                "c3_event_rank_zero_based": rank,
            }
        )

    expected_roles = {
        "q10",
        "q30",
        "q50",
        "q70",
        "q90",
    }
    expected_ttc = {
        55,
        50,
        45,
        40,
        35,
        30,
    }
    for block in sorted(
        block_roles
    ):
        if (
            block_roles[block]
            != expected_roles
        ):
            raise CandidateEC3PreparationError(
                f"C3 {block} structural-role "
                "coverage changed: "
                f"{sorted(block_roles[block])}"
            )
        if (
            block_ttc[block]
            != expected_ttc
        ):
            raise CandidateEC3PreparationError(
                f"C3 {block} TTC coverage "
                "changed: "
                f"{sorted(block_ttc[block])}"
            )

    r2 = load_and_validate_r2_model(
        repo
    )
    r2_fingerprint = str(
        r2[
            "champion_r2_fingerprint"
        ]
    )
    protocol = _read_json(
        repo
        / (
            "configs/"
            "kxbtcd_post_h3_champion_lifecycle.v1.json"
        )
    )
    gate = protocol[
        "confirmation"
    ][
        "gate"
    ]

    cohort_fingerprint = (
        _canonical_sha256(
            cohort_rows
        )
    )
    row_fingerprint = (
        _canonical_sha256(
            frozen_rows
        )
    )
    request_plan = [
        {
            "event_ticker": event,
            "market_ticker": market,
        }
        for market, event
        in sorted(
            markets.items(),
            key=lambda item: (
                item[1],
                item[0],
            ),
        )
    ]

    payload = {
        "schema_version": (
            "kxbtcd_candidate_e_c3_validation_freeze.v1"
        ),
        "checkpoint_id": "21G-C",
        "parent_21a_protocol_fingerprint": (
            PARENT_21A_PROTOCOL_FINGERPRINT
        ),
        "parent_h3_result_fingerprint": (
            PARENT_H3_RESULT_FINGERPRINT
        ),
        "parent_c1_result_fingerprint": (
            C1_RESULT_FINGERPRINT
        ),
        "parent_c2_result_fingerprint": (
            C2_RESULT_FINGERPRINT
        ),
        "implementation_freeze_fingerprint": (
            implementation_freeze[
                "implementation_freeze_fingerprint"
            ]
        ),
        "candidate_id": (
            DISTANCE_CANDIDATE_ID
        ),
        "champion_r2_fingerprint": (
            r2_fingerprint
        ),
        "C3_event_count": (
            C3_ELIGIBLE_EVENT_TARGET
        ),
        "C3_subblocks": [
            f"B{i}"
            for i
            in range(
                C3_SUBBLOCK_COUNT
            )
        ],
        "C3_events_per_subblock": 100,
        "strict_tail_start_index": (
            C3_STRICT_TAIL_START_INDEX
        ),
        "strict_tail_end_index_exclusive_after_C3": (
            end_index
        ),
        "candidate_identities_materialized_for_C3": (
            processed
        ),
        "strict_untouched_tail_remaining_after_C3": (
            remaining
        ),
        "minimum_strict_untouched_tail_after_all_confirmation": (
            MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
        ),
        "c3_cohort_fingerprint": (
            cohort_fingerprint
        ),
        "c3_preoutcome_row_fingerprint": (
            row_fingerprint
        ),
        "c3_preoutcome_row_count": (
            len(frozen_rows)
        ),
        "c3_unique_market_count": (
            len(request_plan)
        ),
        "c3_outcome_request_plan": (
            request_plan
        ),
        "gate": gate,
        "C3_outcomes_opened": False,
        "candidate_selection_performed": False,
        "feature_or_hyperparameter_change_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }

    document = dict(payload)
    document[
        "c3_validation_fingerprint"
    ] = _canonical_sha256(
        payload
    )

    C3_FROZEN_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )
    cohort_path = (
        C3_FROZEN_ROOT
        / "c3_cohort_map.csv"
    )
    rows_path = (
        C3_FROZEN_ROOT
        / "c3_preoutcome_rows.csv"
    )
    summary_path = (
        C3_FROZEN_ROOT
        / "c3_preoutcome_freeze_summary.json"
    )

    _write_csv(
        cohort_path,
        COHORT_FIELDS,
        cohort_rows,
    )
    _write_csv(
        rows_path,
        source_fields
        + ROW_EXTRA_FIELDS,
        frozen_rows,
    )
    _write_json_atomic(
        summary_path,
        document,
    )
    _write_json_atomic(
        repo
        / C3_VALIDATION_FREEZE_PATH,
        document,
    )

    print(
        "Checkpoint 21G-C C3 "
        "pre-outcome freeze: PASS"
    )
    print(
        "C3 validation fingerprint: "
        f"{document['c3_validation_fingerprint']}"
    )
    print(
        "C3 events: "
        f"{C3_ELIGIBLE_EVENT_TARGET} "
        "(5 x 100)"
    )
    print(
        "C3 preoutcome rows: "
        f"{len(frozen_rows)}"
    )
    print(
        "Candidate identities materialized: "
        f"{processed}"
    )
    print(
        "Strict untouched tail remaining: "
        f"{remaining}"
    )
    print("C3 outcomes opened: 0")
    print("Orders placed: 0")
    print(
        "Validation freeze: "
        f"{repo / C3_VALIDATION_FREEZE_PATH}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except CandidateEC3PreparationError as exc:
        raise SystemExit(
            f"C3 pre-outcome freeze error: {exc}"
        ) from exc

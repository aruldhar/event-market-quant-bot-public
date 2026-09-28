from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_c3_preparation import (
    C2_RESULT_CLOSEOUT_FINGERPRINT,
    C3_ELIGIBLE_EVENT_TARGET,
    C3_STRICT_TAIL_EVENT_COUNT_ENTERING,
    C3_STRICT_TAIL_START_INDEX,
    C3_SUBBLOCK_COUNT,
    MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3,
    MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
    R2_EVENT_COUNT,
    R2_ROW_COUNT,
    STRICT_TAIL_MAX_END_EXCLUSIVE,
    UNTOUCHED_QUEUE_EVENT_COUNT,
    CandidateEC3PreparationError,
    _canonical_sha256,
    c3_subblock_for_eligible_rank,
    strict_tail_remaining_after_end_index,
    validate_candidate_end_index,
    validate_parent_21f_b_result_closeout,
)


def test_c3_strict_tail_arithmetic() -> None:
    assert C3_STRICT_TAIL_START_INDEX == 4222
    assert C3_STRICT_TAIL_EVENT_COUNT_ENTERING == 5209
    assert STRICT_TAIL_MAX_END_EXCLUSIVE == 4931
    assert MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3 == 709
    assert (
        strict_tail_remaining_after_end_index(
            C3_STRICT_TAIL_START_INDEX
        )
        == 5209
    )
    assert (
        strict_tail_remaining_after_end_index(
            STRICT_TAIL_MAX_END_EXCLUSIVE
        )
        == 4500
    )
    assert (
        UNTOUCHED_QUEUE_EVENT_COUNT
        - STRICT_TAIL_MAX_END_EXCLUSIVE
        == MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
    )


def test_c3_r2_fit_scope_exact() -> None:
    assert R2_EVENT_COUNT == 4000
    assert R2_ROW_COUNT == 109971


def test_c3_subblock_mapping_exact() -> None:
    assert C3_ELIGIBLE_EVENT_TARGET == 500
    assert C3_SUBBLOCK_COUNT == 5

    for rank in range(500):
        assert (
            c3_subblock_for_eligible_rank(
                rank
            )
            == f"B{rank // 100}"
        )

    with pytest.raises(
        CandidateEC3PreparationError
    ):
        c3_subblock_for_eligible_rank(
            -1
        )

    with pytest.raises(
        CandidateEC3PreparationError
    ):
        c3_subblock_for_eligible_rank(
            500
        )


def test_c3_absolute_floor_fails_closed() -> None:
    validate_candidate_end_index(
        4931
    )
    with pytest.raises(
        CandidateEC3PreparationError
    ):
        validate_candidate_end_index(
            4932
        )


def test_parent_c2_closeout_canonical_fingerprint_without_lineage_files(
    tmp_path: Path,
) -> None:
    source = Path(
        "configs/kxbtcd_candidate_e_c2_result_closeout.json"
    )
    document = json.loads(
        source.read_text(
            encoding="utf-8"
        )
    )
    payload = {
        key: document[key]
        for key in document
        if key
        != "c2_result_closeout_fingerprint"
    }
    assert (
        _canonical_sha256(
            payload
        )
        == C2_RESULT_CLOSEOUT_FINGERPRINT
    )

    target = (
        tmp_path
        / "configs"
    )
    target.mkdir(
        parents=True
    )
    (
        target
        / source.name
    ).write_text(
        json.dumps(
            document,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    validated = (
        validate_parent_21f_b_result_closeout(
            tmp_path,
            verify_lineage_files=False,
        )
    )
    assert (
        validated[
            "C2_validation_passed"
        ]
        is True
    )

    document[
        "orders_placed"
    ] = 1
    (
        target
        / source.name
    ).write_text(
        json.dumps(
            document
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        CandidateEC3PreparationError
    ):
        validate_parent_21f_b_result_closeout(
            tmp_path,
            verify_lineage_files=False,
        )


def test_c3_budget_is_not_reset() -> None:
    assert (
        MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3
        == 4931 - 4222
    )
    assert (
        MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3
        == 709
    )
    assert (
        MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3
        < 1000
    )

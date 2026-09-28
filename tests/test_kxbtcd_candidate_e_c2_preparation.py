from __future__ import annotations

from pathlib import Path
import json

import pytest

from src.kxbtcd_candidate_e_c2_preparation import (
    C1_RESULT_CLOSEOUT_FINGERPRINT,
    C2_ELIGIBLE_EVENT_TARGET,
    C2_STRICT_TAIL_EVENT_COUNT_ENTERING,
    C2_STRICT_TAIL_START_INDEX,
    C2_SUBBLOCK_COUNT,
    MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3,
    MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
    STRICT_TAIL_MAX_END_EXCLUSIVE,
    UNTOUCHED_QUEUE_EVENT_COUNT,
    CandidateEC2PreparationError,
    _canonical_sha256,
    c2_subblock_for_eligible_rank,
    strict_tail_remaining_after_end_index,
    validate_candidate_end_index,
    validate_parent_21d_result_closeout,
)


def test_c2_strict_tail_arithmetic() -> None:
    assert C2_STRICT_TAIL_START_INDEX == 3706
    assert C2_STRICT_TAIL_EVENT_COUNT_ENTERING == 5725
    assert STRICT_TAIL_MAX_END_EXCLUSIVE == 4931
    assert MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3 == 1225
    assert strict_tail_remaining_after_end_index(C2_STRICT_TAIL_START_INDEX) == 5725
    assert strict_tail_remaining_after_end_index(STRICT_TAIL_MAX_END_EXCLUSIVE) == 4500
    assert (
        UNTOUCHED_QUEUE_EVENT_COUNT - STRICT_TAIL_MAX_END_EXCLUSIVE
        == MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
    )


def test_c2_subblock_mapping_exact() -> None:
    assert C2_ELIGIBLE_EVENT_TARGET == 500
    assert C2_SUBBLOCK_COUNT == 5
    for rank in range(500):
        assert c2_subblock_for_eligible_rank(rank) == f"B{rank // 100}"
    with pytest.raises(CandidateEC2PreparationError):
        c2_subblock_for_eligible_rank(-1)
    with pytest.raises(CandidateEC2PreparationError):
        c2_subblock_for_eligible_rank(500)


def test_c2_absolute_floor_fails_closed() -> None:
    validate_candidate_end_index(4931)
    with pytest.raises(CandidateEC2PreparationError):
        validate_candidate_end_index(4932)


def test_parent_c1_closeout_canonical_fingerprint_without_lineage_files(
    tmp_path: Path,
) -> None:
    source = Path("configs/kxbtcd_candidate_e_c1_result_closeout.json")
    document = json.loads(source.read_text(encoding="utf-8"))
    payload = {
        key: document[key]
        for key in document
        if key != "c1_result_closeout_fingerprint"
    }
    assert _canonical_sha256(payload) == C1_RESULT_CLOSEOUT_FINGERPRINT

    target = tmp_path / "configs"
    target.mkdir(parents=True)
    (target / source.name).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validated = validate_parent_21d_result_closeout(
        tmp_path,
        verify_lineage_files=False,
    )
    assert validated["C1_validation_passed"] is True

    document["orders_placed"] = 1
    (target / source.name).write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CandidateEC2PreparationError):
        validate_parent_21d_result_closeout(
            tmp_path,
            verify_lineage_files=False,
        )


def test_c2_reserve_budget_is_shared_with_c3() -> None:
    # This explicitly prevents accidentally resetting a fresh 1,731-event
    # budget after C1. C2+C3 have only the remaining 1,225 identities.
    assert MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3 == 4931 - 3706
    assert MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3 < 1500

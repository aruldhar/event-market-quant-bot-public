from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import kxbtcd_candidate_e_c1_preparation as c1


def test_strict_tail_arithmetic() -> None:
    assert c1.STRICT_TAIL_START_INDEX == 3200
    assert c1.STRICT_TAIL_EVENT_COUNT == 6231
    assert c1.UNTOUCHED_QUEUE_EVENT_COUNT == 9431
    assert c1.MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C1_C2_C3 == 1731
    assert c1.STRICT_TAIL_MAX_END_EXCLUSIVE == 4931
    assert c1.strict_tail_remaining_after_end_index(4931) == 4500


def test_c1_subblock_assignment_is_exact_5_by_100() -> None:
    assert c1.c1_subblock_for_eligible_rank(0) == "B0"
    assert c1.c1_subblock_for_eligible_rank(99) == "B0"
    assert c1.c1_subblock_for_eligible_rank(100) == "B1"
    assert c1.c1_subblock_for_eligible_rank(399) == "B3"
    assert c1.c1_subblock_for_eligible_rank(400) == "B4"
    assert c1.c1_subblock_for_eligible_rank(499) == "B4"
    with pytest.raises(c1.CandidateEC1PreparationError):
        c1.c1_subblock_for_eligible_rank(500)


def test_hard_floor_fails_closed() -> None:
    c1.validate_candidate_end_index(4931)
    with pytest.raises(c1.CandidateEC1PreparationError):
        c1.validate_candidate_end_index(4932)


def test_parent_protocol_fingerprint_is_canonical(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True)
    source = Path("configs/kxbtcd_post_h3_champion_lifecycle.v1.json")
    document = json.loads(source.read_text(encoding="utf-8"))
    (config_dir / source.name).write_text(json.dumps(document, indent=7) + "\n", encoding="utf-8")
    validated = c1.validate_parent_21a_protocol(tmp_path)
    assert validated["confirmation"]["eligible_events_per_block"] == 500
    assert validated["confirmation"]["minimum_strict_untouched_tail_after_all_confirmation"] == 4500


def test_implementation_freeze_fingerprint_detects_change(monkeypatch, tmp_path: Path) -> None:
    files = {}
    for relative in c1.IMPLEMENTATION_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
        files[relative] = c1._sha256_file(path)
    monkeypatch.setattr(c1, "validate_parent_21a_protocol", lambda _repo: {})
    document = c1.build_implementation_freeze_document(
        repository_root=tmp_path,
        source_baseline_commit=c1.PARENT_21A_RECEIPT_COMMIT,
    )
    c1.validate_implementation_freeze_document(document, repository_root=tmp_path)
    tampered = dict(document)
    tampered["orders_placed"] = 1
    with pytest.raises(c1.CandidateEC1PreparationError):
        c1.validate_implementation_freeze_document(tampered)

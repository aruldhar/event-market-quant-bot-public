from __future__ import annotations

import json
from pathlib import Path

from src.kxbtcd_candidate_e_july10_outcome_blind_binding_freeze import (
    FREEZE_PATH,
    canonical_fingerprint,
    validate_freeze,
)


def test_21n_s_a_implementation_freeze_validates() -> None:
    document = validate_freeze(".")
    assert document["checkpoint_id"] == "21N-S-A"
    assert document["implementation_fingerprint"] == "3a20d5ae9deec2e3563362bbafb9d9ac35f1965e126d07840caa0a4de28ef008"


def test_21n_s_a_freeze_keeps_real_materialization_and_outcomes_closed() -> None:
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    safety = document["evidence_and_safety"]
    assert safety["july10_real_signal_or_path_materialization_run_by_21n_s_a"] is False
    assert safety["july10_outcomes_accessed"] is False
    assert safety["strategy_pnl_calculated"] is False
    assert safety["orders_submitted"] == 0
    assert document["next_checkpoint"]["id"] == "21N-S-B"


def test_21n_s_a_freeze_pins_all_three_local_source_hashes() -> None:
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    sources = document["frozen_local_source_contract"]
    assert sources["btc_materialization_sha256"] == "022f6c6ce1b697bc67f7137f73e3f18cc0fe0198b347e5154a3063107299fb12"
    assert sources["paid_predexon_tick_shard_sha256"] == "43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509"
    assert sources["full_ladder_replay_summary_sha256"] == "b37ba7132baf086887e4b33e7c11e9de59decc5f0b387d7e6e5352a2570ebb48"


def test_freeze_fingerprint_changes_on_mutation() -> None:
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    original = canonical_fingerprint(document)
    mutated = dict(document)
    mutated["next_checkpoint"] = dict(document["next_checkpoint"])
    mutated["next_checkpoint"]["pnl_must_remain_unrun"] = False
    assert canonical_fingerprint(mutated) != original

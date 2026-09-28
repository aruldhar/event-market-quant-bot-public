from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_materialization import (
    ConditionalAlphaMaterializationError,
    J_A_REQUIRED_COMMITTED_PATHS,
    materialize_conditional_alpha_rows,
    validate_j_a_closeout_receipt,
)


def parent_row(*, state: str, event: str = "E", market: str = "M", ttc: int = 55, spread: str = "0.10"):
    return {
        "schema_version": "kxbtcd_candidate_e_entry_model_v1_feature_row.v1",
        "model_id": "kxbtcd_candidate_e_entry_residual_logistic.v1",
        "stage": "H1_OOF",
        "state_id": state,
        "event_ticker": event,
        "event_close_time_utc": "2026-01-01T01:00:00Z",
        "market_ticker": market,
        "structural_role": "q50",
        "ttc_target_minutes": str(ttc),
        "decision_time_utc": "2026-01-01T00:05:00Z",
        "candidate_probability": "0.70",
        "r_5m": "-12.5",
        "spread_t": spread,
    }


def preoutcome_row(*, event: str = "E", market: str = "M", ttc: int = 55):
    return {
        "stage": "H1",
        "event_ticker": event,
        "market_ticker": market,
        "structural_role": "q50",
        "ttc_target_minutes": str(ttc),
        "yes_bid": "0.40",
        "yes_ask": "0.50",
    }


def test_projection_reuses_parent_candidate_and_r5_and_adds_only_frozen_derived_features():
    state = "E|M|TTC55|q50"
    rows = materialize_conditional_alpha_rows(
        parent_feature_rows=[parent_row(state=state)],
        preoutcome_rows=[preoutcome_row()],
        enforce_frozen_counts=False,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["candidate_probability"] == "0.70"
    assert float(row["market_midpoint_yes_probability"]) == pytest.approx(.45)
    assert float(row["abs_candidate_market_disagreement"]) == pytest.approx(.25)
    assert float(row["spread_t"]) == pytest.approx(.10)
    assert float(row["abs_r_5m"]) == pytest.approx(12.5)
    assert float(row["ttc_minutes"]) == 55.0
    assert "outcome" not in row
    assert "realized_pnl" not in row


def test_projection_fails_if_parent_frozen_spread_disagrees_with_exact_preoutcome_quote():
    state = "E|M|TTC55|q50"
    with pytest.raises(ConditionalAlphaMaterializationError, match="frozen spread"):
        materialize_conditional_alpha_rows(
            parent_feature_rows=[parent_row(state=state, spread="0.11")],
            preoutcome_rows=[preoutcome_row()],
            enforce_frozen_counts=False,
        )


def test_j_b_gate_requires_a_safely_closed_j_a_receipt(tmp_path: Path):
    receipt = {
        "schema": "checkpoint_closeout_receipt.v1",
        "checkpoint_message": "Checkpoint 21N-J-A — freeze conditional-alpha reliability v1 implementation",
        "committed_paths": sorted(J_A_REQUIRED_COMMITTED_PATHS),
        "safety": {
            "blocked_path_check": "PASS",
            "staged_path_exact_match": "PASS",
            "staged_diff_check": "PASS",
            "high_confidence_secret_scan": "PASS",
            "remote_synchronized_before_commit": True,
            "worktree_clean_after_checkpoint_commit": True,
        },
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert validate_j_a_closeout_receipt(path)["checkpoint_message"].startswith("Checkpoint 21N-J-A")

    receipt["checkpoint_message"] = "Checkpoint 21N-I — old checkpoint"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ConditionalAlphaMaterializationError, match="not a Checkpoint 21N-J-A"):
        validate_j_a_closeout_receipt(path)

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.kxbtcd_candidate_b_evaluation import FrozenPreoutcomeDataset
from src.kxbtcd_candidate_c_terminal_evaluation import (
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_FINAL_MODEL_FINGERPRINT,
    FROZEN_SPLIT_FINGERPRINT,
    KxbtcdCandidateCTerminalEvaluationError,
    TERMINAL_FREEZE_SCHEMA_VERSION,
    TERMINAL_OUTCOME_SCHEMA_VERSION,
    build_locked_test_request_plan_from_rows,
    score_terminal_locked_test,
    terminal_result_fingerprint,
)


def _row(
    *,
    state_id: str,
    event: str,
    market: str,
    q: str,
    spread: str,
) -> dict[str, str]:
    return {
        "partition": "locked_test",
        "state_id": state_id,
        "event_ticker": event,
        "market_ticker": market,
        "utc_week_start": "2026-01-05T00:00:00Z",
        "q_market": q,
        "spread": spread,
    }


def _frozen(rows: tuple[dict[str, str], ...]) -> FrozenPreoutcomeDataset:
    return FrozenPreoutcomeDataset(
        repository_root=Path("."),
        manifest_path=Path("manifest.json"),
        manifest={},
        dataset_path=Path("dataset.csv"),
        exclusions_path=Path("exclusions.csv"),
        selected_events_path=Path("events.csv"),
        selected_markets_path=Path("markets.csv"),
        rows=rows,
        locked_test_market_tickers=frozenset(row["market_ticker"] for row in rows),
        request_plan=(),
        structural_role_by_market={},
    )


def _terminal_freeze(rows: tuple[dict[str, str], ...]) -> dict:
    plan = build_locked_test_request_plan_from_rows(rows, enforce_canonical_counts=False)
    return {
        "schema_version": TERMINAL_FREEZE_SCHEMA_VERSION,
        "candidate_id": "kxbtcd_market_spread_interaction_logistic.v1",
        "full_development_freeze_fingerprint": (
            "d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3"
        ),
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "frozen_preoutcome_run_id": (
            "collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d"
        ),
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "partition": "locked_test",
        "locked_test_event_count": 2,
        "locked_test_row_count": len(rows),
        "locked_test_market_request_count": len(plan),
        "request_plan": [
            {"event_ticker": item.event_ticker, "market_ticker": item.market_ticker}
            for item in plan
        ],
        "outcome_source": {},
        "inference": {},
        "metrics": {},
        "primary_gate": {},
        "exposure_policy": {},
        "source_baseline_commit": "abc",
        "procedure_derivation_outcomes_used": False,
        "locked_test_feature_density_used_for_design": False,
        "locked_test_outcomes_opened_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        # Synthetic tests call score with this document only; its full procedure
        # validation is covered by production derivation/validator integration.
        "terminal_evaluation_fingerprint": "synthetic-procedure",
    }


def _outcomes(rows: tuple[dict[str, str], ...], labels: dict[str, str]) -> tuple[dict[str, str], ...]:
    freeze = _terminal_freeze(rows)
    pairs = {
        (row["event_ticker"], row["market_ticker"])
        for row in rows
    }
    result = []
    for event, market in sorted(pairs):
        outcome = labels[market]
        result.append(
            {
                "schema_version": TERMINAL_OUTCOME_SCHEMA_VERSION,
                "candidate_id": "kxbtcd_market_spread_interaction_logistic.v1",
                "terminal_evaluation_fingerprint": "synthetic-procedure",
                "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
                "preoutcome_run_id": (
                    "collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d"
                ),
                "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                "partition": "locked_test",
                "event_ticker": event,
                "market_ticker": market,
                "raw_source": "test",
                "raw_session_id": "session",
                "raw_request_id": f"request-{market}",
                "market_status": "finalized",
                "result_text": "yes" if outcome == "1" else "no",
                "outcome": outcome,
            }
        )
    return tuple(result)


def test_request_plan_uses_identifiers_only_and_is_sorted() -> None:
    rows = (
        _row(state_id="s2", event="E2", market="M2", q="0.9", spread="0.20"),
        _row(state_id="s1", event="E1", market="M1", q="0.1", spread="0.01"),
        _row(state_id="s3", event="E1", market="M1", q="0.8", spread="0.40"),
    )
    plan = build_locked_test_request_plan_from_rows(rows, enforce_canonical_counts=False)
    assert [(x.event_ticker, x.market_ticker) for x in plan] == [("E1", "M1"), ("E2", "M2")]


def test_request_plan_rejects_non_locked_partition() -> None:
    row = _row(state_id="s1", event="E1", market="M1", q="0.5", spread="0.02")
    row["partition"] = "validation"
    with pytest.raises(KxbtcdCandidateCTerminalEvaluationError):
        build_locked_test_request_plan_from_rows((row,), enforce_canonical_counts=False)


def test_terminal_scoring_equal_weights_events_not_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = (
        _row(state_id="a1", event="E1", market="M1", q="0.9", spread="0.01"),
        _row(state_id="a2", event="E1", market="M1", q="0.9", spread="0.01"),
        _row(state_id="a3", event="E1", market="M1", q="0.9", spread="0.01"),
        _row(state_id="b1", event="E2", market="M2", q="0.1", spread="0.01"),
    )
    frozen = _frozen(rows)
    freeze = _terminal_freeze(rows)
    outcomes = _outcomes(rows, {"M1": "1", "M2": "0"})

    # Bypass full production procedure-schema validation in this synthetic unit
    # test while preserving outcome-plan validation and the real metric function.
    import src.kxbtcd_candidate_c_terminal_evaluation as terminal
    monkeypatch.setattr(
        terminal,
        "validate_terminal_evaluation_freeze_document",
        lambda document, frozen=None: build_locked_test_request_plan_from_rows(
            rows, enforce_canonical_counts=False
        ),
    )

    score = score_terminal_locked_test(
        frozen=frozen,
        terminal_freeze=freeze,
        final_model={},
        outcomes=outcomes,
        predictor=lambda q, spread, model: q,
        enforce_canonical_counts=False,
    )
    assert score.summary["raw_midpoint_event_weighted_log_loss"] == score.summary[
        "candidate_c_event_weighted_log_loss"
    ]
    # Exact tie must fail.
    assert score.gate_passed is False


def test_terminal_gate_passes_only_strict_improvement(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = (
        _row(state_id="a", event="E1", market="M1", q="0.6", spread="0.01"),
        _row(state_id="b", event="E2", market="M2", q="0.4", spread="0.01"),
    )
    frozen = _frozen(rows)
    freeze = _terminal_freeze(rows)
    outcomes = _outcomes(rows, {"M1": "1", "M2": "0"})
    import src.kxbtcd_candidate_c_terminal_evaluation as terminal
    monkeypatch.setattr(
        terminal,
        "validate_terminal_evaluation_freeze_document",
        lambda document, frozen=None: build_locked_test_request_plan_from_rows(
            rows, enforce_canonical_counts=False
        ),
    )
    score = score_terminal_locked_test(
        frozen=frozen,
        terminal_freeze=freeze,
        final_model={},
        outcomes=outcomes,
        predictor=lambda q, spread, model: 0.8 if q > 0.5 else 0.2,
        enforce_canonical_counts=False,
    )
    assert score.gate_passed is True
    assert float(score.summary["delta_log_loss_raw_minus_candidate_c"]) > 0


def test_terminal_result_fingerprint_changes_with_metric() -> None:
    fields = {
        "schema_version": "kxbtcd_candidate_c_terminal_summary.v1",
        "candidate_id": "kxbtcd_market_spread_interaction_logistic.v1",
        "terminal_evaluation_fingerprint": "p",
        "full_development_freeze_fingerprint": "f",
        "final_model_fingerprint": "m",
        "dataset_fingerprint": "d",
        "split_fingerprint": "s",
        "locked_test_event_count": "64",
        "locked_test_row_count": "1014",
        "locked_test_market_label_count": "320",
        "raw_midpoint_event_weighted_log_loss": "0.2",
        "candidate_c_event_weighted_log_loss": "0.1",
        "delta_log_loss_raw_minus_candidate_c": "0.1",
        "raw_midpoint_event_weighted_brier": "0.05",
        "candidate_c_event_weighted_brier": "0.03",
        "delta_brier_raw_minus_candidate_c": "0.02",
        "primary_rule": (
            "candidate_c_event_weighted_log_loss_strictly_less_than_"
            "raw_midpoint_event_weighted_log_loss"
        ),
        "tie_rule": "fail",
        "terminal_gate_passed": "true",
        "locked_test_permanently_exposed": "true",
        "model_refit_performed": "false",
        "model_retuned": "false",
        "model_recalibrated": "false",
        "execution_enabled": "false",
        "orders_placed": "0",
    }
    first = terminal_result_fingerprint(fields)
    changed = dict(fields)
    changed["candidate_c_event_weighted_log_loss"] = "0.11"
    second = terminal_result_fingerprint(changed)
    assert first != second

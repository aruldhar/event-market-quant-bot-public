from __future__ import annotations

from decimal import Decimal
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.kxbtcd_candidate_b_evaluation as module
from src.kxbtcd_candidate_b_evaluation import (
    FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
    FROZEN_DATASET_DESIGN_FINGERPRINT,
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_MATERIALIZATION_FINGERPRINT,
    FROZEN_PREOUTCOME_RUN_ID,
    FROZEN_SPLIT_FINGERPRINT,
    KxbtcdCandidateBEvaluationError,
    LabeledObservation,
    OutcomeRequest,
    FrozenPreoutcomeDataset,
    collect_train_validation_outcomes,
    event_weighted_metrics,
    fit_candidate_b,
)
from src.kxbtcd_preoutcome_dataset import (
    CANDIDATE_B_MODEL_ID,
    candidate_b_spec_fingerprint,
    candidate_b_validation_gate,
    dataset_design_fingerprint,
)
from src.kxbtcd_preoutcome_materialization import materialization_fingerprint


def _observation(
    *,
    event: str,
    state: str,
    weight: float,
    y: int,
    market_logit: float = 0.0,
    strike: float = 0.0,
    time_feature: float = 0.0,
    q_market: float = 0.5,
    partition: str = "train",
) -> LabeledObservation:
    return LabeledObservation(
        partition=partition,
        state_id=state,
        event_ticker=event,
        market_ticker=f"M-{state}",
        utc_week_start="2026-01-05T00:00:00Z",
        event_close_time_utc="2026-01-05T12:00:00Z",
        time_to_close_seconds=1800.0,
        strike_dollars=100000.0,
        event_row_weight=weight,
        outcome=y,
        q_market=q_market,
        market_logit=market_logit,
        strike_log_ratio=strike,
        time_log1p_hours=time_feature,
    )


def _minimal_frozen() -> FrozenPreoutcomeDataset:
    return FrozenPreoutcomeDataset(
        repository_root=Path("."),
        manifest_path=Path("frozen.json"),
        manifest={},
        dataset_path=Path("dataset.csv"),
        exclusions_path=Path("exclusions.csv"),
        selected_events_path=Path("selected_events.csv"),
        selected_markets_path=Path("selected_markets.csv"),
        rows=(),
        locked_test_market_tickers=frozenset({"LOCKED-MARKET"}),
        request_plan=(
            OutcomeRequest(
                partition="train",
                event_ticker="TRAIN-EVENT",
                market_ticker="TRAIN-MARKET",
            ),
            OutcomeRequest(
                partition="validation",
                event_ticker="VAL-EVENT",
                market_ticker="VAL-MARKET",
            ),
        ),
        structural_role_by_market={},
    )


def _outcome_row(*, partition: str, event: str, market: str, result: str) -> dict[str, str]:
    return {
        "schema_version": module.OUTCOME_SCHEMA_VERSION,
        "model_id": CANDIDATE_B_MODEL_ID,
        "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
        "partition": partition,
        "event_ticker": event,
        "market_ticker": market,
        "raw_source": "kalshi_public_rest",
        "raw_session_id": "session",
        "raw_request_id": f"req-{market}",
        "market_status": "finalized",
        "result_text": result,
        "outcome": "1" if result == "yes" else "0",
    }


def test_frozen_fingerprints_match_checkpoint12_contracts() -> None:
    assert candidate_b_spec_fingerprint() == FROZEN_CANDIDATE_B_SPEC_FINGERPRINT
    assert dataset_design_fingerprint() == FROZEN_DATASET_DESIGN_FINGERPRINT
    assert materialization_fingerprint() == FROZEN_MATERIALIZATION_FINGERPRINT


def test_event_weighting_equalizes_events_not_rows() -> None:
    rows = [
        _observation(event="A", state="A1", weight=0.5, y=1, q_market=0.8),
        _observation(event="A", state="A2", weight=0.5, y=0, q_market=0.4),
        _observation(event="B", state="B1", weight=1.0, y=1, q_market=0.6),
    ]
    probabilities = [0.8, 0.4, 0.6]
    metrics = event_weighted_metrics(rows, probabilities)
    event_a = (-math.log(0.8) - math.log(0.6)) / 2.0
    event_b = -math.log(0.6)
    expected = (event_a + event_b) / 2.0
    assert metrics.log_loss == pytest.approx(expected)


def test_validation_gate_is_strict_and_tie_fails() -> None:
    assert candidate_b_validation_gate(
        raw_midpoint_event_weighted_log_loss="0.5",
        candidate_b_event_weighted_log_loss="0.499999",
    )
    assert not candidate_b_validation_gate(
        raw_midpoint_event_weighted_log_loss="0.5",
        candidate_b_event_weighted_log_loss="0.5",
    )


def test_collect_outcomes_requests_only_allow_list_and_never_locked() -> None:
    frozen = _minimal_frozen()
    requested: list[str] = []

    class FakeClient:
        def get_json(self, path: str, *, params=None):
            requested.append(path)
            ticker = path.rsplit("/", 1)[-1]
            if ticker == "TRAIN-MARKET":
                event = "TRAIN-EVENT"
                result = "yes"
            elif ticker == "VAL-MARKET":
                event = "VAL-EVENT"
                result = "no"
            else:  # pragma: no cover - would be a safety regression
                raise AssertionError(f"unexpected request {ticker}")
            return SimpleNamespace(
                payload={
                    "market": {
                        "ticker": ticker,
                        "event_ticker": event,
                        "status": "finalized",
                        "result": result,
                    }
                },
                raw_record=SimpleNamespace(
                    source="kalshi_public_rest",
                    session_id="session",
                    request_id=f"req-{ticker}",
                ),
            )

    outcomes = collect_train_validation_outcomes(FakeClient(), frozen=frozen)
    assert len(outcomes) == 2
    assert requested == [
        "/historical/markets/TRAIN-MARKET",
        "/historical/markets/VAL-MARKET",
    ]
    assert all("LOCKED" not in path for path in requested)


def test_existing_outcome_is_not_re_requested_on_resume() -> None:
    frozen = _minimal_frozen()
    requested: list[str] = []
    existing = [
        _outcome_row(
            partition="train", event="TRAIN-EVENT", market="TRAIN-MARKET", result="yes"
        )
    ]

    class FakeClient:
        def get_json(self, path: str, *, params=None):
            requested.append(path)
            assert path.endswith("VAL-MARKET")
            return SimpleNamespace(
                payload={
                    "market": {
                        "ticker": "VAL-MARKET",
                        "event_ticker": "VAL-EVENT",
                        "status": "finalized",
                        "result": "no",
                    }
                },
                raw_record=SimpleNamespace(
                    source="kalshi_public_rest",
                    session_id="new-session",
                    request_id="new-request",
                ),
            )

    outcomes = collect_train_validation_outcomes(
        FakeClient(), frozen=frozen, existing_outcomes=existing
    )
    assert len(outcomes) == 2
    assert requested == ["/historical/markets/VAL-MARKET"]


def test_locked_test_outcome_is_rejected_even_if_supplied_as_existing() -> None:
    frozen = _minimal_frozen()
    leaked = _outcome_row(
        partition="locked_test",
        event="LOCKED-EVENT",
        market="LOCKED-MARKET",
        result="yes",
    )

    class NoCallClient:
        def get_json(self, path: str, *, params=None):  # pragma: no cover
            raise AssertionError("network call must not happen")

    with pytest.raises(KxbtcdCandidateBEvaluationError, match="locked-test outcome"):
        collect_train_validation_outcomes(
            NoCallClient(), frozen=frozen, existing_outcomes=[leaked]
        )


def test_response_identity_mismatch_fails_closed() -> None:
    frozen = _minimal_frozen()

    class BadClient:
        def get_json(self, path: str, *, params=None):
            ticker = path.rsplit("/", 1)[-1]
            return SimpleNamespace(
                payload={
                    "market": {
                        "ticker": ticker,
                        "event_ticker": "WRONG-EVENT",
                        "status": "finalized",
                        "result": "yes",
                    }
                },
                raw_record=SimpleNamespace(
                    source="kalshi_public_rest",
                    session_id="session",
                    request_id="request",
                ),
            )

    with pytest.raises(KxbtcdCandidateBEvaluationError, match="event mismatch"):
        collect_train_validation_outcomes(BadClient(), frozen=frozen)


def test_nonfinalized_result_fails_closed() -> None:
    frozen = _minimal_frozen()

    class BadClient:
        def get_json(self, path: str, *, params=None):
            ticker = path.rsplit("/", 1)[-1]
            event = "TRAIN-EVENT" if ticker == "TRAIN-MARKET" else "VAL-EVENT"
            return SimpleNamespace(
                payload={
                    "market": {
                        "ticker": ticker,
                        "event_ticker": event,
                        "status": "open",
                        "result": "",
                    }
                },
                raw_record=SimpleNamespace(
                    source="kalshi_public_rest",
                    session_id="session",
                    request_id="request",
                ),
            )

    with pytest.raises(KxbtcdCandidateBEvaluationError, match="not finalized"):
        collect_train_validation_outcomes(BadClient(), frozen=frozen)


def test_optimizer_leaves_intercept_unpenalized(monkeypatch: pytest.MonkeyPatch) -> None:
    # Build the exact frozen train cardinalities so the fitter exercises its
    # production guardrails. All slope features are zero, so only beta0 can move.
    rows: list[LabeledObservation] = []
    state_number = 0
    for event_index in range(module.EXPECTED_PARTITION_EVENT_COUNTS["train"]):
        count = 27 if event_index < 95 else 26
        weight = 1.0 / count
        for within in range(count):
            rows.append(
                _observation(
                    event=f"E{event_index:03d}",
                    state=f"S{state_number:05d}",
                    weight=weight,
                    y=(within + event_index) % 2,
                )
            )
            state_number += 1
    assert len(rows) == module.EXPECTED_PARTITION_ROW_COUNTS["train"]

    weak = fit_candidate_b(rows, lambda_value=Decimal("0.01"))
    strong = fit_candidate_b(rows, lambda_value=Decimal("10"))
    assert weak.converged and strong.converged
    assert weak.coefficients[0] == pytest.approx(strong.coefficients[0], abs=1e-10)
    assert weak.coefficients[1:] == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    assert strong.coefficients[1:] == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)


def test_lambda_grid_tie_break_prefers_larger_lambda() -> None:
    selected = module.select_candidate_b_lambda(
        {
            Decimal("0.01"): "0.51",
            Decimal("0.1"): "0.50",
            Decimal("1"): "0.50",
            Decimal("10"): "0.52",
        }
    )
    assert selected == Decimal("1")


def test_training_objective_uses_lambda_over_two_and_excludes_intercept() -> None:
    rows = [
        _observation(
            event="E",
            state="S1",
            weight=0.5,
            y=1,
            market_logit=1.0,
            strike=0.5,
            time_feature=0.25,
        ),
        _observation(
            event="E",
            state="S2",
            weight=0.5,
            y=0,
            market_logit=-1.0,
            strike=-0.5,
            time_feature=0.5,
        ),
    ]
    beta = [7.0, 2.0, 3.0, 4.0]
    lam = 0.1
    objective, _, _ = module._objective_gradient_hessian(rows, beta, lam)
    unpenalized, _, _ = module._objective_gradient_hessian(rows, beta, 0.0)
    expected_penalty = lam / 2.0 * (2.0**2 + 3.0**2 + 4.0**2)
    assert objective - unpenalized == pytest.approx(expected_penalty)


def test_stronger_lambda_shrinks_nonintercept_signal() -> None:
    rows: list[LabeledObservation] = []
    state_number = 0
    for event_index in range(module.EXPECTED_PARTITION_EVENT_COUNTS["train"]):
        count = 27 if event_index < 95 else 26
        weight = 1.0 / count
        for within in range(count):
            x = -1.0 if within % 2 == 0 else 1.0
            # Mostly, but not perfectly, align the label with x so the optimum
            # is finite and the regularization effect is observable.
            aligned = (x > 0)
            if (within + event_index) % 7 == 0:
                aligned = not aligned
            rows.append(
                _observation(
                    event=f"E{event_index:03d}",
                    state=f"R{state_number:05d}",
                    weight=weight,
                    y=1 if aligned else 0,
                    market_logit=x,
                )
            )
            state_number += 1
    weak = fit_candidate_b(rows, lambda_value=Decimal("0.01"))
    strong = fit_candidate_b(rows, lambda_value=Decimal("10"))
    assert abs(strong.coefficients[1]) < abs(weak.coefficients[1])


def test_artifact_lookup_accepts_structured_manifest_path(tmp_path: Path) -> None:
    artifact = tmp_path / "data" / "derived" / "frozen.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("a\n1\n", encoding="utf-8")
    manifest = {
        "files": [
            {
                "role": "derived_csv",
                "path": {
                    "kind": "repository_relative",
                    "value": "data/derived/frozen.csv",
                },
            }
        ]
    }

    resolved = module._artifact_from_manifest(
        repo=tmp_path,
        manifest=manifest,
        filename="frozen.csv",
        required=True,
    )

    assert resolved == artifact.resolve()


def test_raw_recovery_accepts_structured_manifest_path(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw" / "kalshi_rest" / "session.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text("{}\n", encoding="utf-8")
    manifest = {
        "files": [
            {
                "role": "raw_api_archive",
                "path": {
                    "kind": "repository_relative",
                    "value": "data/raw/kalshi_rest/session.jsonl",
                },
            }
        ],
        "source_sessions": [],
    }

    resolved = module._raw_paths_for_manifest(
        manifest=manifest,
        repository_root=tmp_path,
    )

    assert resolved == (raw.resolve(),)

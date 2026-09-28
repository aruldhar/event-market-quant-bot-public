import math

import pytest

import src.kxbtcd_candidate_e_conditional_alpha_reliability_v2_development as dev
from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import EventEqualScaler
from src.kxbtcd_candidate_e_conditional_alpha_reliability_v2 import (
    ConditionalAlphaV2Error,
    ReliabilityFitV2,
)


def _stage_rows(stage, start, n):
    rows = []
    ttcs = [55, 50, 45, 40, 35, 30]
    for i in range(n):
        idx = start + i
        q = 0.15 + 0.035 * (idx % 20)
        shift = 0.05 + 0.01 * (idx % 5)
        p_e = max(0.03, min(0.97, q + (shift if idx % 2 == 0 else -shift)))
        outcome = 1 if (0.55 * p_e + 0.45 * q) >= 0.5 else 0

        # Deliberately vary the synthetic quote spread. The frozen scaler is
        # supposed to reject zero-variance fit features, so the fixture itself
        # must not accidentally make spread_t constant.
        spread = 0.012 + 0.002 * (idx % 5)
        yes_bid = max(0.0, q - spread / 2.0)
        yes_ask = min(1.0, q + spread / 2.0)
        actual_spread = yes_ask - yes_bid
        midpoint = 0.5 * (yes_bid + yes_ask)

        rows.append({
            "stage": stage,
            "state_id": f"{stage}-s{i}",
            "event_ticker": f"{stage}-e{i}",
            "event_close_time_utc": f"2026-01-{1 + (idx % 20):02d}T12:00:00Z",
            "market_ticker": f"{stage}-m{i}",
            "structural_role": "q50",
            "ttc_target_minutes": ttcs[idx % 6],
            "decision_time_utc": f"2026-01-{1 + (idx % 20):02d}T11:00:00Z",
            "outcome": outcome,
            "candidate_probability": p_e,
            "market_midpoint_yes_probability": midpoint,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "abs_candidate_market_disagreement": abs(p_e - midpoint),
            "spread_t": actual_spread,
            "abs_r_5m": 1.0 + (idx % 7),
            "ttc_minutes": float(ttcs[idx % 6]),
        })
    return rows


def synthetic_labeled_rows():
    return (
        _stage_rows("H1_OOF", 0, 18)
        + _stage_rows("H2", 100, 12)
        + _stage_rows("H3", 200, 12)
    )


def test_fit_and_score_fold_uses_v2_candidate_identity_and_newton_fit():
    """Exercise one genuine Newton fold on a synthetic case known to be well behaved."""
    rows = synthetic_labeled_rows()
    fit, scored = dev.fit_and_score_fold(
        rows,
        lambda_value=0.1,
        fold=1,
        fit_stages=("H1_OOF",),
        score_stage="H2",
    )
    assert fit.gradient_l2_norm <= 1e-8
    assert len(scored) == 12
    assert {row["candidate_id"] for row in scored} == {
        "kxbtcd_candidate_e_conditional_alpha_reliability.v2"
    }
    assert all(0.0 < float(row["conditional_alpha"]) < 1.0 for row in scored)


def test_all_five_lambdas_two_folds_are_routed_without_assuming_arbitrary_synthetic_hessian_pd(monkeypatch):
    """Test evaluator orchestration, not an unstated global-convexity guarantee.

    The exact conditional-alpha Hessian is not guaranteed positive definite for
    arbitrary synthetic data. The frozen v2 contract correctly fails closed if
    Cholesky fails. Therefore this test stubs the already-tested Newton fitter and
    verifies only that the evaluator routes every frozen lambda through both
    frozen folds and computes a pooled score for each lambda.
    """
    calls = []
    scaler = EventEqualScaler(
        means=(0.0, 0.0, 0.0, 0.0),
        stds=(1.0, 1.0, 1.0, 1.0),
    )

    def fake_fit_and_score_fold(
        labeled_rows,
        *,
        lambda_value,
        fold,
        fit_stages,
        score_stage,
    ):
        calls.append((
            float(lambda_value),
            int(fold),
            tuple(fit_stages),
            str(score_stage),
        ))
        fit = ReliabilityFitV2(
            lambda_value=float(lambda_value),
            gamma=(0.0, 0.0, 0.0, 0.0, 0.0),
            scaler=scaler,
            iterations=1,
            objective=0.1 + float(lambda_value),
            gradient_l2_norm=1e-9,
            total_backtracks=0,
            minimum_accepted_step=1.0,
        )
        scored = []
        for row in labeled_rows:
            if row["stage"] != score_stage:
                continue
            q = float(row["market_midpoint_yes_probability"])
            p_e = float(row["candidate_probability"])
            p50 = q + 0.5 * (p_e - q)
            scored.append({
                "event_ticker": row["event_ticker"],
                "outcome": row["outcome"],
                "adjusted_yes_probability": p50,
            })
        return fit, tuple(scored)

    monkeypatch.setattr(dev, "fit_and_score_fold", fake_fit_and_score_fold)

    scores, predictions, fits = dev.rolling_origin_lambda_evaluation(
        synthetic_labeled_rows(),
        enforce_frozen_counts=False,
    )

    assert len(calls) == 10
    assert calls == [
        (float(lam), int(fold), tuple(fit_stages), str(score_stage))
        for lam in dev.LAMBDA_GRID
        for fold, fit_stages, score_stage in dev.FOLDS
    ]
    assert len(scores) == 5
    assert set(predictions) == set(dev.LAMBDA_GRID)
    assert all(len(fits[lam]) == 2 for lam in dev.LAMBDA_GRID)
    assert all(
        math.isfinite(float(row["pooled_H2_H3_event_equal_log_loss"]))
        for row in scores
    )


def test_v2_optimizer_failure_is_wrapped_with_frozen_context(monkeypatch):
    def boom(rows, *, lambda_value):
        raise ConditionalAlphaV2Error("synthetic cholesky failure")

    monkeypatch.setattr(dev, "fit_conditional_alpha_v2", boom)
    with pytest.raises(dev.ConditionalAlphaV2FitContractError) as caught:
        dev.fit_and_score_fold(
            synthetic_labeled_rows(),
            lambda_value=0.001,
            fold=2,
            fit_stages=("H1_OOF", "H2"),
            score_stage="H3",
        )
    failure = caught.value
    assert failure.phase == "rolling_origin_lambda_evaluation"
    assert failure.fold == 2
    assert failure.lambda_value == 0.001
    assert "synthetic cholesky failure" in failure.original_message


def test_receipt_gate_rejects_pre_m_c_receipt(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        '{"schema":"checkpoint_closeout_receipt.v1","checkpoint_message":"Checkpoint 21N-M-B — x","committed_paths":[],"safety":{}}',
        encoding="utf-8",
    )
    with pytest.raises(
        dev.ConditionalAlphaV2DevelopmentError,
        match="not Checkpoint 21N-M-C",
    ):
        dev.validate_m_c_closeout_receipt(receipt)

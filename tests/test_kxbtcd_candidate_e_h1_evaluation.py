from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import src.kxbtcd_candidate_e_h1_evaluation as h1


def _obs(*, event: str, d: float, y: int, r: float = 0.0, block: str = "B0") -> h1.CandidateEObservation:
    return h1.CandidateEObservation(
        state_id=f"{event}|M-{event}|55|q50",
        event_ticker=event,
        market_ticker=f"M-{event}",
        block_id=block,
        structural_role="q50",
        ttc_target_minutes=55,
        outcome=y,
        q_market=0.5,
        d_btc=d,
        r_5m=r,
    )


def test_damped_newton_distance_fit_recovers_positive_effect() -> None:
    rows = (
        _obs(event="e1", d=-1.0, y=0),
        _obs(event="e2", d=-1.0, y=0),
        _obs(event="e3", d=-1.0, y=1),
        _obs(event="e4", d=0.0, y=0),
        _obs(event="e5", d=0.0, y=1),
        _obs(event="e6", d=1.0, y=0),
        _obs(event="e7", d=1.0, y=1),
        _obs(event="e8", d=1.0, y=1),
    )
    fit = h1.fit_candidate_e(
        rows,
        candidate_id=h1.DISTANCE_CANDIDATE_ID,
        fold=1,
        fit_blocks=("B0", "B1"),
        score_block="B2",
    )
    assert fit.converged is True
    assert fit.beta_distance > 0.0
    assert fit.beta_momentum is None


def test_damped_newton_rejects_unfrozen_candidate() -> None:
    with pytest.raises(h1.KxbtcdCandidateEH1EvaluationError, match="unfrozen"):
        h1.fit_candidate_e(
            (_obs(event="e1", d=1.0, y=1),),
            candidate_id="candidate_e_posthoc_repair.v99",
            fold=1,
            fit_blocks=("B0", "B1"),
            score_block="B2",
        )


def test_assert_not_sealed_identity_rejects_h2_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h1, "_sealed_identity_sets", lambda universe: ({"H2-E"}, {"H3-M"}))
    universe = h1.FrozenCandidateEUniverse(summary={}, cohort_rows=(), preoutcome_rows=())
    with pytest.raises(h1.KxbtcdCandidateEH1EvaluationError, match="sealed H2/H3 event"):
        h1.assert_not_sealed_identity(
            universe=universe,
            event_ticker="H2-E",
            market_ticker="H1-M",
        )


def test_assert_not_sealed_identity_rejects_h3_market(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h1, "_sealed_identity_sets", lambda universe: ({"H2-E"}, {"H3-M"}))
    universe = h1.FrozenCandidateEUniverse(summary={}, cohort_rows=(), preoutcome_rows=())
    with pytest.raises(h1.KxbtcdCandidateEH1EvaluationError, match="sealed H2/H3 market"):
        h1.assert_not_sealed_identity(
            universe=universe,
            event_ticker="H1-E",
            market_ticker="H3-M",
        )


def test_stage_identity_disjointness_rejects_cross_stage_market(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h1, "_stage_events", lambda universe, stage: (f"{stage}-E",))
    maps = {
        "H1": {"SHARED-M": "H1-E"},
        "H2": {"SHARED-M": "H2-E"},
        "H3": {"H3-M": "H3-E"},
    }
    monkeypatch.setattr(h1, "_stage_market_map", lambda universe, stage: maps[stage])
    universe = h1.FrozenCandidateEUniverse(summary={}, cohort_rows=(), preoutcome_rows=())
    with pytest.raises(h1.KxbtcdCandidateEH1EvaluationError, match="market identity overlap"):
        h1.validate_stage_identity_disjointness(universe)


@dataclass
class _Raw:
    source: str = "kalshi_public_rest"
    session_id: str = "session"
    request_id: str = "request"


@dataclass
class _Response:
    payload: dict
    raw_record: _Raw = field(default_factory=_Raw)


class _Client:
    def __init__(self, payload: dict):
        self.payload = payload
        self.paths: list[str] = []

    def get_json(self, path: str, *, params=None):
        self.paths.append(path)
        return _Response(self.payload)


def test_collect_h1_requests_only_frozen_plan_and_rejects_sealed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    request = h1.OutcomeRequest(event_ticker="H1-E", market_ticker="H1-M")
    monkeypatch.setattr(h1, "_planned_by_market", lambda freeze: {"H1-M": request})
    monkeypatch.setattr(h1, "validate_h1_outcomes", lambda outcomes, **kwargs: tuple(dict(x) for x in outcomes))
    monkeypatch.setattr(h1, "_sealed_identity_sets", lambda universe: ({"H2-E"}, {"H2-M"}))
    universe = h1.FrozenCandidateEUniverse(summary={}, cohort_rows=(), preoutcome_rows=())
    client = _Client(
        {
            "market": {
                "ticker": "H2-M",
                "event_ticker": "H2-E",
                "status": "finalized",
                "result": "yes",
            }
        }
    )
    with pytest.raises(h1.KxbtcdCandidateEH1EvaluationError, match="sealed H2/H3"):
        h1.collect_h1_outcomes(client, freeze={"h1_evaluation_fingerprint": "f" * 64}, universe=universe)
    assert client.paths == ["/historical/markets/H1-M"]


def test_collect_h1_has_no_arbitrary_ticker_argument() -> None:
    # Guard the public collection API itself: caller supplies the frozen procedure,
    # not a partition/ticker selector that could bypass the allow-list.
    import inspect
    parameters = inspect.signature(h1.collect_h1_outcomes).parameters
    assert "ticker" not in parameters
    assert "partition" not in parameters


def test_candidate_probability_nests_raw_at_zero_coefficients() -> None:
    observation = _obs(event="e1", d=125.0, y=1, r=-40.0)
    fit = h1.CandidateEFit(
        candidate_id=h1.MOMENTUM_CANDIDATE_ID,
        fold=1,
        fit_blocks=("B0", "B1"),
        score_block="B2",
        beta_distance=0.0,
        beta_momentum=0.0,
        iterations=0,
        converged=True,
        fit_objective=0.0,
    )
    assert h1.predict_candidate_e(observation, fit) == pytest.approx(0.5)


def test_collector_cli_exposes_no_ticker_or_partition_escape_hatch() -> None:
    from pathlib import Path
    text = Path("collect_kxbtcd_candidate_e_h1.py").read_text(encoding="utf-8")
    assert '"--ticker"' not in text
    assert '"--partition"' not in text
    assert "--resume-from-manifest" in text


def test_checkpoint20_collector_contains_no_execution_api_surface() -> None:
    from pathlib import Path
    text = Path("collect_kxbtcd_candidate_e_h1.py").read_text(encoding="utf-8").lower()
    for forbidden in (
        "create_order",
        "cancel_order",
        "portfolio/",
        "transfer_funds",
        "paper_broker",
        "demo_order",
    ):
        assert forbidden not in text

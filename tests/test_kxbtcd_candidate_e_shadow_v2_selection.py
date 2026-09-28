from decimal import Decimal

from src.kxbtcd_candidate_e_shadow_v2_evaluator import evaluate_causal_v2_market
from src.kxbtcd_candidate_e_shadow_v2_selection import select_frozen_primary_candidates
from tests.test_kxbtcd_candidate_e_shadow_v2_evaluator import ladder, point


def test_selection_uses_frozen_primary_threshold_and_retains_depth_gate():
    evaluation = evaluate_causal_v2_market(event_ladder=ladder(), point=point())
    selected = select_frozen_primary_candidates((evaluation,))
    assert selected == ()

    boosted = evaluation.__class__(
        **{**evaluation.__dict__, "sides": tuple(
            side.__class__(**{**side.__dict__, "net_edge": Decimal("0.02"), "depth_qualifies": True})
            for side in evaluation.sides
        )}
    )
    selected = select_frozen_primary_candidates((boosted,))
    assert [(item.side, item.net_edge_per_contract) for item in selected] == [
        ("YES", Decimal("0.02")), ("NO", Decimal("0.02"))
    ]


def test_selection_does_not_score_unavailable_market_evaluations():
    evaluation = evaluate_causal_v2_market(event_ladder=ladder(), point=point())
    unavailable = evaluation.__class__(**{**evaluation.__dict__, "status": "KALSHI_SOURCE_UNAVAILABLE"})
    assert select_frozen_primary_candidates((unavailable,)) == ()

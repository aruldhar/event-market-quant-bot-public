from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_shadow_v2_evaluator import evaluate_causal_v2_market
from src.kxbtcd_candidate_e_shadow_v2_event_report import (
    ShadowV2EventReportError,
    iter_frozen_v2_event_decisions,
)
from tests.test_kxbtcd_candidate_e_shadow_v2_evaluator import ladder, point


def qualified_evaluation(*, timestamp_ms, net_edge):
    base = evaluate_causal_v2_market(event_ladder=ladder(), point=point())
    sides = tuple(side.__class__(**{
        **side.__dict__, "net_edge": Decimal(net_edge), "depth_qualifies": True
    }) for side in base.sides)
    return base.__class__(**{
        **base.__dict__, "decision_timestamp_ms": timestamp_ms, "sides": sides
    })


def test_event_report_selects_one_frozen_winner_per_timestamp():
    rows = list(iter_frozen_v2_event_decisions((
        qualified_evaluation(timestamp_ms=1, net_edge="0.02"),
        qualified_evaluation(timestamp_ms=2, net_edge="0.01"),
    )))
    assert [row.qualified_candidate_count for row in rows] == [2, 0]
    assert rows[0].selected.side == "YES"
    assert rows[1].selected is None


def test_event_report_rejects_event_time_regression():
    with pytest.raises(ShadowV2EventReportError, match="ordered"):
        list(iter_frozen_v2_event_decisions((
            qualified_evaluation(timestamp_ms=2, net_edge="0.02"),
            qualified_evaluation(timestamp_ms=1, net_edge="0.02"),
        )))

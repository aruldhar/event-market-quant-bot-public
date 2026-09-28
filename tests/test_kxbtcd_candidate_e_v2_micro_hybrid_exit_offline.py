from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import (
    BidLevel,
    HybridExitOfflineError,
    HybridExitPhase,
    ReconciledPosition,
    assess_hybrid_exit,
    full_ladder_proceeds,
    reassess_after_handoff_reconciliation,
)


def d(value: str) -> Decimal:
    return Decimal(value)


def test_full_ladder_uses_all_levels_and_returns_worst_consumed_price():
    gross, worst = full_ladder_proceeds(
        (BidLevel(d("0.70"), d("2")), BidLevel(d("0.62"), d("3"))),
        quantity=d("5"),
    )
    assert gross == d("3.26")
    assert worst == d("0.62")


def test_hybrid_handoff_counts_confirmed_resting_fill_before_remaining_ladder():
    assessment = assess_hybrid_exit(
        position=ReconciledPosition(d("3"), d("1.40")),
        bids=(BidLevel(d("0.62"), d("3")),),
        supplied_exit_fee=d("0.01"),
        required_total_net_proceeds=d("3.20"),
    )
    assert assessment.phase is HybridExitPhase.HANDOFF_REQUIRED
    assert assessment.total_net_proceeds_if_filled == d("3.25")
    assert assessment.worst_price_required == d("0.62")


def test_hybrid_keeps_monitoring_when_full_remaining_exit_misses_original_target():
    assessment = assess_hybrid_exit(
        position=ReconciledPosition(d("3"), d("1.40")),
        bids=(BidLevel(d("0.60"), d("3")),),
        supplied_exit_fee=d("0.01"),
        required_total_net_proceeds=d("3.20"),
    )
    assert assessment.phase is HybridExitPhase.MONITORING_RESTING_EXIT
    assert assessment.total_net_proceeds_if_filled == d("3.19")


def test_hybrid_never_claims_a_full_exit_when_ladder_depth_is_insufficient():
    assessment = assess_hybrid_exit(
        position=ReconciledPosition(d("3"), d("0")),
        bids=(BidLevel(d("0.70"), d("2")),),
        supplied_exit_fee=d("0"),
        required_total_net_proceeds=d("2"),
    )
    assert assessment.phase is HybridExitPhase.MONITORING_RESTING_EXIT
    assert assessment.worst_price_required is None


def test_closed_reconciliation_cannot_request_another_exit():
    assessment = assess_hybrid_exit(
        position=ReconciledPosition(d("0"), d("3.21")),
        bids=(),
        supplied_exit_fee=d("0"),
        required_total_net_proceeds=d("3.20"),
    )
    assert assessment.phase is HybridExitPhase.CLOSED


def test_late_partial_resting_fill_requires_recalculation_before_fok():
    prior = assess_hybrid_exit(
        position=ReconciledPosition(d("5"), d("0")),
        bids=(BidLevel(d("0.70"), d("2")), BidLevel(d("0.62"), d("3"))),
        supplied_exit_fee=d("0.01"),
        required_total_net_proceeds=d("3.20"),
    )
    assert prior.phase is HybridExitPhase.HANDOFF_REQUIRED

    after_cancel = reassess_after_handoff_reconciliation(
        prior=prior,
        reconciled_position=ReconciledPosition(d("3"), d("1.40")),
        bids=(BidLevel(d("0.60"), d("3")),),
        supplied_exit_fee=d("0.01"),
    )
    assert after_cancel.phase is HybridExitPhase.RESTING_EXIT_RECALCULATION_REQUIRED
    assert after_cancel.total_net_proceeds_if_filled == d("3.19")


def test_reconciliation_to_flat_closes_without_another_exit():
    prior = assess_hybrid_exit(
        position=ReconciledPosition(d("1"), d("0")),
        bids=(BidLevel(d("0.70"), d("1")),),
        supplied_exit_fee=d("0"),
        required_total_net_proceeds=d("0.60"),
    )
    after_cancel = reassess_after_handoff_reconciliation(
        prior=prior,
        reconciled_position=ReconciledPosition(d("0"), d("0.70")),
        bids=(),
        supplied_exit_fee=d("0"),
    )
    assert after_cancel.phase is HybridExitPhase.CLOSED


def test_invalid_depth_is_rejected_instead_of_coerced():
    with pytest.raises(HybridExitOfflineError, match="positive"):
        full_ladder_proceeds((BidLevel(d("0.70"), d("0")),), quantity=d("1"))

from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import BidLevel, ReconciledPosition
from src.kxbtcd_candidate_e_v2_micro_hybrid_state_machine_offline import (
    HybridProbeState,
    HybridProbeStateError,
    OfflineHybridProbe,
)


def d(value: str) -> Decimal:
    return Decimal(value)


def test_handoff_requires_cancel_reconciliation_before_fok_evaluation():
    probe = OfflineHybridProbe.new().record_confirmed_entry(
        required_total_net_proceeds=d("3.20")
    )
    handoff = probe.observe_fresh_ladder(
        position=ReconciledPosition(d("5"), d("0")),
        bids=(BidLevel(d("0.70"), d("2")), BidLevel(d("0.62"), d("3"))),
        supplied_exit_fee=d("0.01"),
    )
    assert handoff.state is HybridProbeState.CANCEL_RECONCILIATION_REQUIRED

    with pytest.raises(HybridProbeStateError, match="FOK reconciliation"):
        handoff.record_fok_reconciliation(position=ReconciledPosition(d("0"), d("3.25")))

    reconciled = handoff.record_cancel_reconciliation(
        position=ReconciledPosition(d("3"), d("1.40")),
        bids=(BidLevel(d("0.62"), d("3")),),
        supplied_exit_fee=d("0.01"),
    )
    assert reconciled.state is HybridProbeState.FOK_EVALUATION_ALLOWED


def test_late_partial_fill_that_breaks_target_requires_replacement_not_fok():
    probe = OfflineHybridProbe.new().record_confirmed_entry(
        required_total_net_proceeds=d("3.20")
    ).observe_fresh_ladder(
        position=ReconciledPosition(d("5"), d("0")),
        bids=(BidLevel(d("0.70"), d("2")), BidLevel(d("0.62"), d("3"))),
        supplied_exit_fee=d("0.01"),
    )
    after_cancel = probe.record_cancel_reconciliation(
        position=ReconciledPosition(d("3"), d("1.40")),
        bids=(BidLevel(d("0.60"), d("3")),),
        supplied_exit_fee=d("0.01"),
    )
    assert after_cancel.state is HybridProbeState.RESTING_EXIT_REPLACEMENT_REQUIRED


def test_fok_reconciliation_to_flat_closes_and_prevents_more_entries():
    probe = OfflineHybridProbe.new().record_confirmed_entry(
        required_total_net_proceeds=d("1")
    ).observe_fresh_ladder(
        position=ReconciledPosition(d("1"), d("0")),
        bids=(BidLevel(d("1"), d("1")),),
        supplied_exit_fee=d("0"),
    ).record_cancel_reconciliation(
        position=ReconciledPosition(d("1"), d("0")),
        bids=(BidLevel(d("1"), d("1")),),
        supplied_exit_fee=d("0"),
    ).record_fok_reconciliation(position=ReconciledPosition(d("0"), d("1")))
    assert probe.state is HybridProbeState.CLOSED
    with pytest.raises(HybridProbeStateError, match="confirmed entry requires flat"):
        probe.record_confirmed_entry(required_total_net_proceeds=d("1"))


def test_entry_attempts_are_bounded_while_flat():
    probe = OfflineHybridProbe.new(maximum_entry_attempts=2)
    probe = probe.record_unfilled_entry_attempt().record_unfilled_entry_attempt()
    with pytest.raises(HybridProbeStateError, match="maximum entry attempts"):
        probe.record_unfilled_entry_attempt()

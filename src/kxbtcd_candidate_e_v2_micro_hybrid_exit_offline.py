"""Offline-only evaluator for the Candidate-E V2 micro hybrid exit.

This module has no network client, credentials, order transport, order-intent
outbox, or exchange side effect.  It evaluates archived book ladders and
authoritative reconciliation snapshots so the live decision path can later be
tested without touching a venue.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable


ZERO = Decimal("0")


class HybridExitPhase(str, Enum):
    MONITORING_RESTING_EXIT = "MONITORING_RESTING_EXIT"
    HANDOFF_REQUIRED = "HANDOFF_REQUIRED"
    CLOSED = "CLOSED"
    RESTING_EXIT_RECALCULATION_REQUIRED = "RESTING_EXIT_RECALCULATION_REQUIRED"


class HybridExitOfflineError(ValueError):
    pass


@dataclass(frozen=True)
class BidLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class ReconciledPosition:
    """Venue-derived state after a resting-exit cancel/fill reconciliation.

    ``realized_net_proceeds`` must include every confirmed resting-order fill
    and its actual fees.  Nothing in this module estimates a fill.
    """

    remaining_quantity: Decimal
    realized_net_proceeds: Decimal


@dataclass(frozen=True)
class HybridExitAssessment:
    phase: HybridExitPhase
    remaining_quantity: Decimal
    realized_net_proceeds: Decimal
    ladder_gross_proceeds: Decimal
    supplied_exit_fee: Decimal
    ladder_net_proceeds: Decimal
    total_net_proceeds_if_filled: Decimal
    required_total_net_proceeds: Decimal
    worst_price_required: Decimal | None


def _require_nonnegative(value: Decimal, field: str) -> None:
    if value < ZERO:
        raise HybridExitOfflineError(f"{field} must be non-negative")


def full_ladder_proceeds(
    bids: Iterable[BidLevel], *, quantity: Decimal
) -> tuple[Decimal, Decimal | None]:
    """Return gross proceeds and the worst price for an exact full exit.

    The calculation consumes bids in provided best-to-worst order.  It refuses
    insufficient or malformed depth rather than assuming a partial fill.
    """
    _require_nonnegative(quantity, "quantity")
    if quantity == ZERO:
        return ZERO, None

    remaining = quantity
    gross = ZERO
    worst_price: Decimal | None = None
    for level in bids:
        if level.price <= ZERO or level.price > Decimal("1"):
            raise HybridExitOfflineError("bid price must be in (0, 1]")
        if level.quantity <= ZERO:
            raise HybridExitOfflineError("bid quantity must be positive")
        consumed = min(remaining, level.quantity)
        gross += consumed * level.price
        remaining -= consumed
        worst_price = level.price
        if remaining == ZERO:
            return gross, worst_price
    raise HybridExitOfflineError("insufficient bid depth for full remaining quantity")


def assess_hybrid_exit(
    *,
    position: ReconciledPosition,
    bids: Iterable[BidLevel],
    supplied_exit_fee: Decimal,
    required_total_net_proceeds: Decimal,
) -> HybridExitAssessment:
    """Assess a hypothetical all-or-nothing exit from immutable book data.

    A ``HANDOFF_REQUIRED`` result means the caller may begin a later live
    cancel/reconcile/FOK workflow.  This evaluator creates no order or intent.
    If full depth is absent or net proceeds miss the retained target, it returns
    ``MONITORING_RESTING_EXIT``.
    """
    _require_nonnegative(position.remaining_quantity, "remaining_quantity")
    _require_nonnegative(position.realized_net_proceeds, "realized_net_proceeds")
    _require_nonnegative(supplied_exit_fee, "supplied_exit_fee")
    _require_nonnegative(required_total_net_proceeds, "required_total_net_proceeds")

    if position.remaining_quantity == ZERO:
        return HybridExitAssessment(
            phase=HybridExitPhase.CLOSED,
            remaining_quantity=ZERO,
            realized_net_proceeds=position.realized_net_proceeds,
            ladder_gross_proceeds=ZERO,
            supplied_exit_fee=ZERO,
            ladder_net_proceeds=ZERO,
            total_net_proceeds_if_filled=position.realized_net_proceeds,
            required_total_net_proceeds=required_total_net_proceeds,
            worst_price_required=None,
        )

    try:
        gross, worst_price = full_ladder_proceeds(
            bids, quantity=position.remaining_quantity
        )
    except HybridExitOfflineError as exc:
        if str(exc) != "insufficient bid depth for full remaining quantity":
            raise
        return HybridExitAssessment(
            phase=HybridExitPhase.MONITORING_RESTING_EXIT,
            remaining_quantity=position.remaining_quantity,
            realized_net_proceeds=position.realized_net_proceeds,
            ladder_gross_proceeds=ZERO,
            supplied_exit_fee=supplied_exit_fee,
            ladder_net_proceeds=ZERO,
            total_net_proceeds_if_filled=position.realized_net_proceeds,
            required_total_net_proceeds=required_total_net_proceeds,
            worst_price_required=None,
        )

    ladder_net = gross - supplied_exit_fee
    total_net = position.realized_net_proceeds + ladder_net
    phase = (
        HybridExitPhase.HANDOFF_REQUIRED
        if total_net >= required_total_net_proceeds
        else HybridExitPhase.MONITORING_RESTING_EXIT
    )
    return HybridExitAssessment(
        phase=phase,
        remaining_quantity=position.remaining_quantity,
        realized_net_proceeds=position.realized_net_proceeds,
        ladder_gross_proceeds=gross,
        supplied_exit_fee=supplied_exit_fee,
        ladder_net_proceeds=ladder_net,
        total_net_proceeds_if_filled=total_net,
        required_total_net_proceeds=required_total_net_proceeds,
        worst_price_required=worst_price,
    )


def reassess_after_handoff_reconciliation(
    *,
    prior: HybridExitAssessment,
    reconciled_position: ReconciledPosition,
    bids: Iterable[BidLevel],
    supplied_exit_fee: Decimal,
) -> HybridExitAssessment:
    """Re-evaluate after the resting exit is confirmed inactive at the venue.

    This is deliberately an offline state transition.  A late resting-order
    fill can reduce the remaining quantity or complete the position; neither
    case may reuse the pre-cancel ladder or assume a full FOK fill.
    """
    if prior.phase is not HybridExitPhase.HANDOFF_REQUIRED:
        raise HybridExitOfflineError("handoff reconciliation requires prior handoff")
    assessment = assess_hybrid_exit(
        position=reconciled_position,
        bids=bids,
        supplied_exit_fee=supplied_exit_fee,
        required_total_net_proceeds=prior.required_total_net_proceeds,
    )
    if assessment.phase is HybridExitPhase.MONITORING_RESTING_EXIT:
        return HybridExitAssessment(
            phase=HybridExitPhase.RESTING_EXIT_RECALCULATION_REQUIRED,
            remaining_quantity=assessment.remaining_quantity,
            realized_net_proceeds=assessment.realized_net_proceeds,
            ladder_gross_proceeds=assessment.ladder_gross_proceeds,
            supplied_exit_fee=assessment.supplied_exit_fee,
            ladder_net_proceeds=assessment.ladder_net_proceeds,
            total_net_proceeds_if_filled=assessment.total_net_proceeds_if_filled,
            required_total_net_proceeds=assessment.required_total_net_proceeds,
            worst_price_required=assessment.worst_price_required,
        )
    return assessment

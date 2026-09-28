"""Strict settlement accounting for isolated live-shadow positions.

This module consumes only a normalized *official final* market outcome.  It
does not inspect a book, infer a fill, or contact a venue.  A separate
read-only collector will eventually publish the normalized outcome; until
then these functions make the accounting contract testable offline.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .kxbtcd_candidate_e_dashboard_shadow_projection import SHADOW_EVENT_SCHEMA_VERSION
from .kxbtcd_candidate_e_live_shadow_micro_simulator import (
    LiveShadowMicroState,
    LiveShadowMicroStep,
)
from .kxbtcd_candidate_e_shadow_v2_scenarios import ShadowV2Scenario


class LiveShadowSettlementError(ValueError):
    pass


OFFICIAL_FINAL_SETTLEMENT_BASIS = "OFFICIAL_FINAL_MARKET_RESULT"


@dataclass(frozen=True)
class OfficialKalshiSettlement:
    """Sanitized terminal market evidence accepted by the shadow sidecar."""

    market_ticker: str
    official_market_status: str
    official_market_result: str
    observed_utc: str

    def validated_result(self) -> str:
        if not isinstance(self.market_ticker, str) or not self.market_ticker:
            raise LiveShadowSettlementError("settlement market ticker is invalid")
        if self.official_market_status != "finalized":
            raise LiveShadowSettlementError("settlement is not officially finalized")
        if self.official_market_result not in {"yes", "no"}:
            raise LiveShadowSettlementError("settlement result is invalid")
        if not isinstance(self.observed_utc, str) or not self.observed_utc:
            raise LiveShadowSettlementError("settlement observed UTC is invalid")
        return self.official_market_result


def _event(
    *,
    run_id: str,
    scenario: ShadowV2Scenario,
    event_sequence: int,
    input_snapshot_sequence: int,
    observed_utc: str,
    event_type: str,
    **fields: object,
) -> dict[str, object]:
    return {
        "schema_version": SHADOW_EVENT_SCHEMA_VERSION,
        "run_id": run_id,
        "scenario_id": scenario.scenario_id,
        "scenario_edge_threshold": format(scenario.edge_threshold, "f"),
        "scenario_is_primary": scenario.is_primary,
        "execution_timing_basis": scenario.execution_timing_basis,
        "event_sequence": event_sequence,
        "input_snapshot_sequence": input_snapshot_sequence,
        "snapshot_generated_utc": observed_utc,
        "event_type": event_type,
        **fields,
    }


def settle_live_shadow_micro_for_scenario(
    *,
    prior: LiveShadowMicroState,
    run_id: str,
    scenario: ShadowV2Scenario,
    first_event_sequence: int,
    input_snapshot_sequence: int,
    settlement: OfficialKalshiSettlement,
) -> LiveShadowMicroStep:
    """Close one open simulated position against an official final outcome.

    The payout is intentionally binary and mechanical: one dollar per contract
    only for the matching side.  It is not a simulated order fill and carries
    no queue, displayed-depth, or exit-fee assumption.
    """
    result = settlement.validated_result()
    if not isinstance(run_id, str) or not run_id:
        raise LiveShadowSettlementError("settlement run id is invalid")
    if first_event_sequence < 1 or input_snapshot_sequence < 1:
        raise LiveShadowSettlementError("settlement event identity is invalid")
    if prior.remaining_quantity <= 0 or not prior.position_id:
        raise LiveShadowSettlementError("there is no open simulated position to settle")
    if prior.market_ticker != settlement.market_ticker:
        raise LiveShadowSettlementError("settlement ticker does not match open position")
    if prior.side not in {"YES", "NO"} or not prior.event_ticker:
        raise LiveShadowSettlementError("open simulated position is invalid")

    position_side = prior.side.lower()
    payout = prior.remaining_quantity if position_side == result else Decimal("0")
    settlement_event = _event(
        run_id=run_id,
        scenario=scenario,
        event_sequence=first_event_sequence,
        input_snapshot_sequence=input_snapshot_sequence,
        observed_utc=settlement.observed_utc,
        event_type="shadow_simulated_settlement",
        position_id=prior.position_id,
        market_ticker=prior.market_ticker,
        position_side=position_side,
        official_market_status=settlement.official_market_status,
        official_market_result=result,
        settlement_basis=OFFICIAL_FINAL_SETTLEMENT_BASIS,
        settlement_quantity=format(prior.remaining_quantity, "f"),
        simulated_settlement_payout=format(payout, "f"),
    )
    close_event = _event(
        run_id=run_id,
        scenario=scenario,
        event_sequence=first_event_sequence + 1,
        input_snapshot_sequence=input_snapshot_sequence,
        observed_utc=settlement.observed_utc,
        event_type="shadow_position_closed",
        position_id=prior.position_id,
    )
    return LiveShadowMicroStep(
        LiveShadowMicroState(
            event_ticker=prior.event_ticker,
            position_id=prior.position_id,
            market_ticker=prior.market_ticker,
            side=prior.side,
            remaining_quantity=Decimal("0"),
            entry_cost=prior.entry_cost,
            required_total_net_proceeds=prior.required_total_net_proceeds,
            entry_attempts=prior.entry_attempts,
            closed_event_tickers=prior.closed_event_tickers | {prior.event_ticker},
            pending_settlements=prior.pending_settlements,
            decision_diagnostics=prior.decision_diagnostics,
            market_universe=prior.market_universe,
            frozen_atm_event_ticker=prior.frozen_atm_event_ticker,
            frozen_atm_market_tickers=prior.frozen_atm_market_tickers,
            stop_loss_fraction=prior.stop_loss_fraction,
            profit_target_multiplier=prior.profit_target_multiplier,
            duration_cap_minutes=prior.duration_cap_minutes,
            trailing_activation_margin=prior.trailing_activation_margin,
        ),
        (settlement_event, close_event),
    )

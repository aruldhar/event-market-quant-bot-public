"""Frozen live-shadow scenario catalog for the V2 edge-threshold comparison."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


EDGE_THRESHOLDS = tuple(Decimal(value) for value in ("0.00", "0.01", "0.02", "0.03", "0.05"))
PRIMARY_EDGE_THRESHOLD = Decimal("0.02")
EXECUTION_TIMING_BASIS = "OBSERVED_SHADOW_PATH"
LATENCY_SENSITIVITY_SCOPE = "OFFLINE_ONLY_NOT_LIVE_RANKED"


@dataclass(frozen=True)
class ShadowV2Scenario:
    """One frozen edge policy evaluated on the common observed shadow path."""

    scenario_id: str
    edge_threshold: Decimal
    is_primary: bool
    execution_timing_basis: str


def _scenario_id(edge_threshold: Decimal) -> str:
    edge_cents = int(edge_threshold * 100)
    return f"edge_{edge_cents:03d}"


def _build_scenarios() -> tuple[ShadowV2Scenario, ...]:
    scenarios = tuple(
        ShadowV2Scenario(
            scenario_id=_scenario_id(edge_threshold),
            edge_threshold=edge_threshold,
            is_primary=edge_threshold == PRIMARY_EDGE_THRESHOLD,
            execution_timing_basis=EXECUTION_TIMING_BASIS,
        )
        for edge_threshold in EDGE_THRESHOLDS
    )
    if len(scenarios) != 5 or len({item.scenario_id for item in scenarios}) != 5:
        raise RuntimeError("frozen V2 live-shadow catalog is not a unique five-policy edge grid")
    if sum(item.is_primary for item in scenarios) != 1:
        raise RuntimeError("frozen V2 live-shadow catalog must contain exactly one primary")
    return scenarios


SHADOW_V2_SCENARIOS = _build_scenarios()
PRIMARY_SHADOW_V2_SCENARIO = next(item for item in SHADOW_V2_SCENARIOS if item.is_primary)

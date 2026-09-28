"""Atomic private-dashboard export for read-only shadow simulations."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

from .kxbtcd_candidate_e_dashboard_export import DashboardExportError, _json_value
from .kxbtcd_candidate_e_dashboard_projection import DashboardProjectionError
from .kxbtcd_candidate_e_dashboard_shadow_projection import (
    DashboardShadowProjectionError,
    project_shadow_ledger_events,
)
from .kxbtcd_candidate_e_shadow_v2_scenarios import (
    LATENCY_SENSITIVITY_SCOPE,
    PRIMARY_SHADOW_V2_SCENARIO,
    SHADOW_V2_SCENARIOS,
)
from .kxbtcd_candidate_e_soak_archive import write_json_atomic


SHADOW_DASHBOARD_SNAPSHOT_SCHEMA_VERSION = "kxbtcd_candidate_e_dashboard_shadow_snapshot.v1"
MULTI_SCENARIO_SHADOW_DASHBOARD_SNAPSHOT_SCHEMA_VERSION = (
    "kxbtcd_candidate_e_dashboard_shadow_snapshot.v2"
)
PNL_BASIS = "SIMULATED_OBSERVED_DEPTH_NOT_VENUE_REALIZED"
FILL_LIMITATIONS = [
    "does_not_prove_queue_priority",
    "does_not_prove_hidden_liquidity",
    "does_not_prove_cancellation_races",
    "does_not_prove_resting_order_fill",
]


def _utc(value: object) -> str:
    if not isinstance(value, str):
        raise DashboardExportError("dashboard generated UTC is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DashboardExportError("dashboard generated UTC is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise DashboardExportError("dashboard generated UTC must be explicit UTC")
    return value


def _projection_payload(events: Iterable[Mapping[str, object]]) -> dict[str, object]:
    try:
        projection = project_shadow_ledger_events(events)
    except (DashboardProjectionError, DashboardShadowProjectionError) as exc:
        raise DashboardExportError("shadow dashboard projection is invalid") from exc
    return {
        "summary": {
            "total_simulated_net_pnl": _json_value(projection.total_simulated_net_pnl),
            "simulated_closed_trade_count": projection.simulated_closed_trade_count,
            "simulated_open_position_count": projection.simulated_open_position_count,
        },
        "trades": [
            {key: _json_value(value) for key, value in asdict(trade).items()}
            for trade in projection.trades
        ],
    }


def build_shadow_dashboard_snapshot(
    *,
    events: Iterable[Mapping[str, object]],
    generated_utc: str,
) -> dict[str, object]:
    """Build the legacy single-primary snapshot for compatibility tests/tools."""
    payload = _projection_payload(events)
    return {
        "schema_version": SHADOW_DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
        "generated_utc": _utc(generated_utc),
        "pnl_basis": PNL_BASIS,
        "fill_limitations": list(FILL_LIMITATIONS),
        **payload,
    }


def build_multi_scenario_shadow_dashboard_snapshot(
    *,
    scenario_events: Mapping[str, Iterable[Mapping[str, object]]],
    generated_utc: str,
    input_snapshot_sequence: int,
) -> dict[str, object]:
    """Build one same-data read model containing every live edge scenario."""
    if (
        isinstance(input_snapshot_sequence, bool)
        or not isinstance(input_snapshot_sequence, int)
        or input_snapshot_sequence < 1
    ):
        raise DashboardExportError("input snapshot sequence must be positive")
    expected = {scenario.scenario_id for scenario in SHADOW_V2_SCENARIOS}
    supplied = set(scenario_events)
    if supplied != expected:
        raise DashboardExportError(
            "multi-scenario dashboard requires the exact live edge-policy catalog"
        )

    rows: list[dict[str, object]] = []
    primary_payload: dict[str, object] | None = None
    catalog: list[dict[str, object]] = []
    for scenario in SHADOW_V2_SCENARIOS:
        payload = _projection_payload(scenario_events[scenario.scenario_id])
        metadata = {
            "scenario_id": scenario.scenario_id,
            "edge_threshold": format(scenario.edge_threshold, "f"),
            "is_primary": scenario.is_primary,
            "execution_timing_basis": scenario.execution_timing_basis,
        }
        catalog.append(metadata)
        rows.append({**metadata, **payload})
        if scenario.is_primary:
            primary_payload = payload
    if primary_payload is None:
        raise DashboardExportError("frozen primary scenario is missing")

    return {
        "schema_version": MULTI_SCENARIO_SHADOW_DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
        "generated_utc": _utc(generated_utc),
        "input_snapshot_sequence": input_snapshot_sequence,
        "pnl_basis": PNL_BASIS,
        "fill_limitations": list(FILL_LIMITATIONS),
        "latency_sensitivity_scope": LATENCY_SENSITIVITY_SCOPE,
        "primary_scenario_id": PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
        "scenario_catalog": catalog,
        "scenarios": rows,
        "summary": primary_payload["summary"],
        "trades": primary_payload["trades"],
    }


def export_shadow_dashboard_snapshot(
    *,
    events: Iterable[Mapping[str, object]],
    generated_utc: str,
    output_path: str | Path,
) -> dict[str, object]:
    output = Path(output_path)
    if output.name != "shadow_dashboard_snapshot.json":
        raise DashboardExportError(
            "shadow dashboard output must use the canonical snapshot filename"
        )
    snapshot = build_shadow_dashboard_snapshot(
        events=events,
        generated_utc=generated_utc,
    )
    write_json_atomic(output, snapshot)
    return snapshot


def export_multi_scenario_shadow_dashboard_snapshot(
    *,
    scenario_events: Mapping[str, Iterable[Mapping[str, object]]],
    generated_utc: str,
    input_snapshot_sequence: int,
    output_path: str | Path,
) -> dict[str, object]:
    output = Path(output_path)
    if output.name != "shadow_dashboard_snapshot.json":
        raise DashboardExportError(
            "shadow dashboard output must use the canonical snapshot filename"
        )
    snapshot = build_multi_scenario_shadow_dashboard_snapshot(
        scenario_events=scenario_events,
        generated_utc=generated_utc,
        input_snapshot_sequence=input_snapshot_sequence,
    )
    write_json_atomic(output, snapshot)
    return snapshot

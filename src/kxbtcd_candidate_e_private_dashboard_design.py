"""Fail-closed design validator for the isolated Candidate-E dashboard boundary.

This module contains no HTTP client, dashboard server, venue credential,
order, cancellation, or execution capability. It freezes the boundary that
all dashboard deployment must preserve.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


class PrivateDashboardDesignError(ValueError):
    pass


CONFIG_PATH = Path("configs/kxbtcd_candidate_e_private_dashboard_design_v1.json")
EXPECTED_SCHEMA_VERSION = "kxbtcd_candidate_e_private_dashboard_design.v1"
EXPECTED_VIEWS = frozenset({
    "portfolio_summary", "scenario_lab", "scenario_detail", "trade_lifecycle_table",
    "position_and_pnl_detail", "strategy_decision_lineage", "venue_reconciliation_status",
    "runtime_reliability",
})
FORBIDDEN_LABELS = frozenset({
    "order_id", "client_order_id", "venue_order_id", "trade_id", "market_ticker",
})
EXPECTED_EDGE_THRESHOLDS = {"0.00", "0.01", "0.02", "0.03", "0.05"}
EXPECTED_SCENARIO_IDS = {"edge_000", "edge_001", "edge_002", "edge_003", "edge_005"}


def _mapping(payload: object, name: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise PrivateDashboardDesignError(f"{name} must be an object")
    return payload


def _exact(values: object, expected: set[str] | frozenset[str], name: str) -> None:
    if not isinstance(values, list) or set(values) != set(expected) or len(values) != len(expected):
        raise PrivateDashboardDesignError(f"{name} changed")


def validate_payload(payload: object) -> Mapping[str, object]:
    p = _mapping(payload, "dashboard design")
    if p.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise PrivateDashboardDesignError("dashboard schema version changed")
    scope = _mapping(p.get("scope"), "scope")
    if (scope.get("current_execution_mode") != "disabled"
            or any(scope.get(key) is not False for key in (
                "real_money_execution_authorized", "dashboard_can_submit_orders",
                "dashboard_can_cancel_orders", "dashboard_can_modify_strategy",
                "dashboard_can_access_venue_credentials"))):
        raise PrivateDashboardDesignError("dashboard scope must remain read-only")
    isolation = _mapping(p.get("isolation"), "isolation")
    if any(isolation.get(key) != value for key, value in {
        "runtime_to_dashboard_flow": "one_way_sanitized_projection",
        "dashboard_to_runtime_network_path": "none",
        "dashboard_failure_blocks_runtime": False,
        "dashboard_credential_mounts": "none",
        "dashboard_database_role": "read_only",
        "initial_access": "localhost_only_via_ssh_tunnel",
    }.items()):
        raise PrivateDashboardDesignError("dashboard isolation contract changed")
    ledger = _mapping(p.get("future_ledger_contract"), "future ledger contract")
    if (ledger.get("current_phase_persists_order_fill_position_state") is not False
            or ledger.get("event_storage") != "append_only_durable_ledger"
            or ledger.get("reconciliation_required_before_closed_position") is not True):
        raise PrivateDashboardDesignError("ledger safety contract changed")
    _exact(ledger.get("event_identity"), {"run_id", "event_sequence", "event_type"}, "ledger event identity")
    _exact(ledger.get("required_lineage"), {
        "git_head", "docker_image_digest", "strategy_fingerprint", "decision_record_id",
    }, "ledger lineage")
    pnl = _mapping(p.get("pnl_contract"), "P&L contract")
    if (pnl.get("realized_pnl_basis") != "confirmed_fills_and_confirmed_fees_only"
            or pnl.get("never_mix_realized_and_estimated_pnl") is not True):
        raise PrivateDashboardDesignError("P&L contract changed")
    shadow = _mapping(p.get("shadow_simulation_contract"), "shadow simulation contract")
    if any(shadow.get(key) != value for key, value in {
        "enabled_in_current_read_only_phase": True,
        "execution_side_effects": False,
        "input": "one_way_sanitized_causal_market_snapshots",
        "ledger": "append_only_simulation_only",
        "pnl_label": "simulated_observed_depth_not_venue_realized",
        "retained_exit_target": "entry_outlay_plus_selected_v2_net_edge_times_simulated_filled_quantity",
        "resting_exit_fill_claim": "not_proven_from_book_data",
        "simulated_entry_budget_dollars": "100.00",
        "shadow_failure_blocks_soak": False,
    }.items()):
        raise PrivateDashboardDesignError("shadow simulation contract changed")

    scenarios = _mapping(p.get("scenario_lab_contract"), "scenario lab contract")
    if any(scenarios.get(key) != value for key, value in {
        "live_ranked_dimension": "net_edge_threshold_only",
        "primary_scenario_id": "edge_002",
        "execution_timing_basis": "OBSERVED_SHADOW_PATH",
        "latency_sensitivity_scope": "OFFLINE_ONLY_NOT_LIVE_RANKED",
        "same_causal_snapshot_fanout": True,
    }.items()):
        raise PrivateDashboardDesignError("Scenario Lab execution contract changed")
    _exact(scenarios.get("edge_thresholds"), EXPECTED_EDGE_THRESHOLDS, "Scenario Lab edge thresholds")
    _exact(scenarios.get("scenario_ids"), EXPECTED_SCENARIO_IDS, "Scenario Lab scenario IDs")
    _exact(scenarios.get("scenario_state_identity"), {"run_id", "scenario_id"}, "Scenario Lab state identity")

    _exact(p.get("views"), EXPECTED_VIEWS, "dashboard views")
    metrics = _mapping(p.get("operational_metrics"), "operational metrics")
    if metrics.get("backend") != "prometheus_compatible_aggregates":
        raise PrivateDashboardDesignError("metrics backend changed")
    _exact(metrics.get("forbidden_high_cardinality_labels"), FORBIDDEN_LABELS, "forbidden metric labels")
    deployment = _mapping(p.get("deployment"), "deployment")
    if any(deployment.get(key) != value for key, value in {
        "dashboard_platform": "grafana",
        "grafana_version": "13.2.1",
        "grafana_sqlite_plugin_version": "4.0.6",
        "current_shadow_read_model": "sqlite_query_projection_v2",
        "current_shadow_read_model_access": "grafana_query_only_read_only_mount",
        "current_shadow_read_model_volume": "dedicated_projection_only_volume",
        "trade_read_model": "postgresql_when_enabled",
        "runtime_health_source": "prometheus_compatible_metrics",
        "dashboard_provisioning": "version_controlled",
    }.items()):
        raise PrivateDashboardDesignError("dashboard deployment contract changed")
    return p


def validate_design(repo_root: str | Path = ".") -> Mapping[str, object]:
    path = Path(repo_root) / CONFIG_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrivateDashboardDesignError("dashboard design is unreadable") from exc
    return validate_payload(payload)

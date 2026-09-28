"""Incremental SQLite read model for the private Candidate-E shadow dashboard.

The append-only simulation ledger remains authoritative. This module maintains
an independent query-oriented projection for Grafana. Each shadow event is
applied once under a per-scenario cursor; Grafana receives only read-only access
to this materialized database and never receives simulation-ledger or venue
credentials.
"""
from __future__ import annotations

import json
import os
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping

from .kxbtcd_candidate_e_dashboard_shadow_export import PNL_BASIS
from .kxbtcd_candidate_e_dashboard_shadow_projection import EXACT_OBSERVED_DEPTH_IOC
from .kxbtcd_candidate_e_shadow_v2_scenarios import (
    LATENCY_SENSITIVITY_SCOPE,
    PRIMARY_SHADOW_V2_SCENARIO,
    SHADOW_V2_SCENARIOS,
)


class ShadowDashboardReadModelError(ValueError):
    pass


CANONICAL_READ_MODEL_FILENAME = "shadow_dashboard_read_model.sqlite3"
READ_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_shadow_dashboard_read_model.v3"
KNOWN_SCENARIO_IDS = frozenset(item.scenario_id for item in SHADOW_V2_SCENARIOS)


def _decimal(value: object, field: str, *, nonnegative: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ShadowDashboardReadModelError(f"{field} must be decimal") from exc
    if not parsed.is_finite() or (nonnegative and parsed < 0):
        raise ShadowDashboardReadModelError(f"{field} is invalid")
    return parsed


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS dashboard_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scenario_catalog (
            scenario_id TEXT PRIMARY KEY,
            edge_threshold REAL NOT NULL,
            edge_threshold_text TEXT NOT NULL,
            is_primary INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
            execution_timing_basis TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scenario_cursor (
            run_id TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            last_event_sequence INTEGER NOT NULL,
            last_snapshot_sequence INTEGER NOT NULL,
            PRIMARY KEY (run_id, scenario_id),
            FOREIGN KEY (scenario_id) REFERENCES scenario_catalog(scenario_id)
        );
        CREATE TABLE IF NOT EXISTS scenario_summary (
            scenario_id TEXT PRIMARY KEY,
            total_simulated_net_pnl REAL NOT NULL,
            total_simulated_net_pnl_text TEXT NOT NULL,
            simulated_closed_trade_count INTEGER NOT NULL,
            simulated_open_position_count INTEGER NOT NULL,
            generated_utc TEXT NOT NULL,
            input_snapshot_sequence INTEGER NOT NULL,
            FOREIGN KEY (scenario_id) REFERENCES scenario_catalog(scenario_id)
        );
        CREATE TABLE IF NOT EXISTS decision_diagnostics (
            run_id TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            snapshots_evaluated INTEGER NOT NULL,
            outside_entry_window INTEGER NOT NULL,
            no_evaluable_market INTEGER NOT NULL,
            insufficient_visible_depth INTEGER NOT NULL,
            edge_below_threshold INTEGER NOT NULL,
            eligible_candidate_selected INTEGER NOT NULL,
            position_open INTEGER NOT NULL,
            event_or_reentry_state INTEGER NOT NULL,
            max_yes_net_edge REAL,
            max_no_net_edge REAL,
            closest_net_edge_deficit REAL,
            PRIMARY KEY (run_id, scenario_id),
            FOREIGN KEY (scenario_id) REFERENCES scenario_catalog(scenario_id)
        );
        CREATE TABLE IF NOT EXISTS trades (
            scenario_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            position_id TEXT NOT NULL,
            market_ticker TEXT NOT NULL,
            entry_utc TEXT,
            exit_utc TEXT,
            entry_simulated_quantity REAL NOT NULL,
            exit_simulated_quantity REAL NOT NULL,
            net_simulated_position_quantity REAL NOT NULL,
            net_simulated_cash_flow REAL NOT NULL,
            simulated_net_pnl REAL,
            simulated_flat INTEGER NOT NULL CHECK (simulated_flat IN (0, 1)),
            simulation_fill_count INTEGER NOT NULL,
            fill_assumption TEXT NOT NULL,
            PRIMARY KEY (scenario_id, run_id, position_id)
        );
        CREATE TABLE IF NOT EXISTS shadow_events (
            run_id TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL,
            input_snapshot_sequence INTEGER NOT NULL,
            event_utc TEXT NOT NULL,
            event_type TEXT NOT NULL,
            position_id TEXT,
            market_ticker TEXT,
            action TEXT,
            reason TEXT,
            side TEXT,
            net_edge_per_contract REAL,
            simulated_quantity REAL,
            simulated_price REAL,
            simulated_fee REAL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, scenario_id, event_sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_shadow_events_scenario_type
            ON shadow_events(scenario_id, event_type, event_sequence);
        CREATE INDEX IF NOT EXISTS idx_shadow_events_position
            ON shadow_events(scenario_id, position_id, event_sequence);
        CREATE INDEX IF NOT EXISTS idx_trades_scenario_exit
            ON trades(scenario_id, exit_utc);
    """)


def _open(path: Path) -> sqlite3.Connection:
    if path.name != CANONICAL_READ_MODEL_FILENAME:
        raise ShadowDashboardReadModelError("dashboard read model filename is invalid")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        _create_schema(connection)
        _create_strategy_schema(connection)
        with connection:
            row = connection.execute(
                "SELECT value FROM dashboard_metadata WHERE key='schema_version'"
            ).fetchone()
            if row is not None and row[0] != READ_MODEL_SCHEMA_VERSION:
                raise ShadowDashboardReadModelError("dashboard read model schema is incompatible")
            metadata = {
                "schema_version": READ_MODEL_SCHEMA_VERSION,
                "pnl_basis": PNL_BASIS,
                "latency_sensitivity_scope": LATENCY_SENSITIVITY_SCOPE,
                "primary_scenario_id": PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
            }
            connection.executemany(
                "INSERT INTO dashboard_metadata(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                tuple(metadata.items()),
            )
            for scenario in SHADOW_V2_SCENARIOS:
                connection.execute(
                    "INSERT INTO scenario_catalog VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(scenario_id) DO UPDATE SET "
                    "edge_threshold=excluded.edge_threshold, "
                    "edge_threshold_text=excluded.edge_threshold_text, "
                    "is_primary=excluded.is_primary, "
                    "execution_timing_basis=excluded.execution_timing_basis",
                    (
                        scenario.scenario_id,
                        float(scenario.edge_threshold),
                        format(scenario.edge_threshold, "f"),
                        1 if scenario.is_primary else 0,
                        scenario.execution_timing_basis,
                    ),
                )
    except Exception:
        connection.close()
        raise
    return connection


def _normalized_event(event: Mapping[str, object], scenario_id: str) -> tuple[object, ...]:
    if event.get("scenario_id") != scenario_id:
        raise ShadowDashboardReadModelError("dashboard event scenario lineage is invalid")
    run_id = event.get("run_id")
    sequence = event.get("event_sequence")
    snapshot_sequence = event.get("input_snapshot_sequence")
    event_utc = event.get("snapshot_generated_utc")
    event_type = event.get("event_type")
    if not isinstance(run_id, str) or not run_id:
        raise ShadowDashboardReadModelError("dashboard event run id is invalid")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ShadowDashboardReadModelError("dashboard event sequence is invalid")
    if isinstance(snapshot_sequence, bool) or not isinstance(snapshot_sequence, int) or snapshot_sequence < 1:
        raise ShadowDashboardReadModelError("dashboard event snapshot sequence is invalid")
    if not isinstance(event_utc, str) or not event_utc:
        raise ShadowDashboardReadModelError("dashboard event UTC is invalid")
    if not isinstance(event_type, str) or not event_type:
        raise ShadowDashboardReadModelError("dashboard event type is invalid")

    def number(field: str) -> float | None:
        value = event.get(field)
        return None if value is None else float(_decimal(value, field))

    return (
        run_id,
        scenario_id,
        sequence,
        snapshot_sequence,
        event_utc,
        event_type,
        _optional_text(event.get("position_id")),
        _optional_text(event.get("market_ticker")),
        _optional_text(event.get("action")),
        _optional_text(event.get("reason")),
        _optional_text(event.get("side")),
        number("net_edge_per_contract"),
        number("simulated_quantity"),
        number("simulated_price"),
        number("simulated_fee"),
        json.dumps(dict(event), sort_keys=True, separators=(",", ":")),
    )


def _apply_trade_event(
    connection: sqlite3.Connection,
    event: Mapping[str, object],
    scenario_id: str,
) -> None:
    event_type = event["event_type"]
    if event_type == "shadow_simulated_fill":
        if event.get("fill_assumption") != EXACT_OBSERVED_DEPTH_IOC:
            raise ShadowDashboardReadModelError("dashboard fill assumption is not approved")
        run_id = str(event["run_id"])
        position_id = _optional_text(event.get("position_id"))
        market_ticker = _optional_text(event.get("market_ticker"))
        side = _optional_text(event.get("side"))
        event_utc = str(event["snapshot_generated_utc"])
        if not position_id or not market_ticker or side not in {"buy", "sell"}:
            raise ShadowDashboardReadModelError("dashboard fill identity is invalid")
        quantity = _decimal(event.get("simulated_quantity"), "simulated_quantity", nonnegative=True)
        price = _decimal(event.get("simulated_price"), "simulated_price", nonnegative=True)
        fee = _decimal(event.get("simulated_fee"), "simulated_fee", nonnegative=True)
        if quantity <= 0 or price <= 0 or price > 1:
            raise ShadowDashboardReadModelError("dashboard fill economics are invalid")
        row = connection.execute(
            "SELECT market_ticker, net_simulated_position_quantity, net_simulated_cash_flow, "
            "simulated_flat, fill_assumption FROM trades "
            "WHERE scenario_id=? AND run_id=? AND position_id=?",
            (scenario_id, run_id, position_id),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO trades VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 0, 0, NULL, 0, 0, ?)",
                (scenario_id, run_id, position_id, market_ticker, EXACT_OBSERVED_DEPTH_IOC),
            )
            net_quantity = Decimal("0")
            net_cash = Decimal("0")
        else:
            existing_market, net_quantity_raw, net_cash_raw, simulated_flat, assumption = row
            if existing_market != market_ticker or simulated_flat or assumption != EXACT_OBSERVED_DEPTH_IOC:
                raise ShadowDashboardReadModelError("dashboard fill conflicts with projected trade")
            net_quantity = Decimal(str(net_quantity_raw))
            net_cash = Decimal(str(net_cash_raw))
        if side == "buy":
            next_quantity = net_quantity + quantity
            next_cash = net_cash - (price * quantity + fee)
            connection.execute(
                "UPDATE trades SET entry_utc=COALESCE(entry_utc, ?), "
                "entry_simulated_quantity=entry_simulated_quantity+?, "
                "net_simulated_position_quantity=?, net_simulated_cash_flow=?, "
                "simulation_fill_count=simulation_fill_count+1 "
                "WHERE scenario_id=? AND run_id=? AND position_id=?",
                (event_utc, float(quantity), float(next_quantity), float(next_cash), scenario_id, run_id, position_id),
            )
        else:
            if net_quantity < quantity:
                raise ShadowDashboardReadModelError("dashboard exit exceeds projected position")
            next_quantity = net_quantity - quantity
            next_cash = net_cash + (price * quantity - fee)
            connection.execute(
                "UPDATE trades SET exit_utc=?, exit_simulated_quantity=exit_simulated_quantity+?, "
                "net_simulated_position_quantity=?, net_simulated_cash_flow=?, "
                "simulation_fill_count=simulation_fill_count+1 "
                "WHERE scenario_id=? AND run_id=? AND position_id=?",
                (event_utc, float(quantity), float(next_quantity), float(next_cash), scenario_id, run_id, position_id),
            )
    elif event_type == "shadow_position_closed":
        run_id = str(event["run_id"])
        position_id = _optional_text(event.get("position_id"))
        if not position_id:
            raise ShadowDashboardReadModelError("closed dashboard position id is invalid")
        row = connection.execute(
            "SELECT net_simulated_position_quantity, net_simulated_cash_flow, simulated_flat "
            "FROM trades WHERE scenario_id=? AND run_id=? AND position_id=?",
            (scenario_id, run_id, position_id),
        ).fetchone()
        if row is None or row[2] or abs(float(row[0])) > 1e-9:
            raise ShadowDashboardReadModelError("dashboard position is not flat at close")
        connection.execute(
            "UPDATE trades SET simulated_flat=1, simulated_net_pnl=? "
            "WHERE scenario_id=? AND run_id=? AND position_id=?",
            (float(row[1]), scenario_id, run_id, position_id),
        )
    elif event_type == "shadow_simulated_settlement":
        run_id = str(event["run_id"])
        position_id = _optional_text(event.get("position_id"))
        market_ticker = _optional_text(event.get("market_ticker"))
        position_side = _optional_text(event.get("position_side"))
        result = _optional_text(event.get("official_market_result"))
        event_utc = str(event["snapshot_generated_utc"])
        if (
            not position_id or not market_ticker or position_side not in {"yes", "no"}
            or result not in {"yes", "no"}
            or event.get("settlement_basis") != "OFFICIAL_FINAL_MARKET_RESULT"
            or event.get("official_market_status") != "finalized"
        ):
            raise ShadowDashboardReadModelError("dashboard settlement identity is invalid")
        quantity = _decimal(event.get("settlement_quantity"), "settlement_quantity", nonnegative=True)
        payout = _decimal(event.get("simulated_settlement_payout"), "simulated_settlement_payout", nonnegative=True)
        if quantity <= 0:
            raise ShadowDashboardReadModelError("dashboard settlement quantity is invalid")
        row = connection.execute(
            "SELECT market_ticker, net_simulated_position_quantity, net_simulated_cash_flow, simulated_flat "
            "FROM trades WHERE scenario_id=? AND run_id=? AND position_id=?",
            (scenario_id, run_id, position_id),
        ).fetchone()
        if row is None or row[0] != market_ticker or row[3] or Decimal(str(row[1])) != quantity:
            raise ShadowDashboardReadModelError("dashboard settlement conflicts with projected trade")
        expected_payout = quantity if position_side == result else Decimal("0")
        if payout != expected_payout:
            raise ShadowDashboardReadModelError("dashboard settlement payout is inconsistent")
        connection.execute(
            "UPDATE trades SET exit_utc=?, net_simulated_position_quantity=0, "
            "net_simulated_cash_flow=? WHERE scenario_id=? AND run_id=? AND position_id=?",
            (event_utc, float(Decimal(str(row[2])) + payout), scenario_id, run_id, position_id),
        )


def _update_summary(
    connection: sqlite3.Connection,
    *,
    scenario_id: str,
    generated_utc: str,
    snapshot_sequence: int,
) -> None:
    total, closed_count, open_count = connection.execute(
        "SELECT COALESCE(SUM(CASE WHEN simulated_flat=1 THEN simulated_net_pnl ELSE 0 END), 0), "
        "SUM(CASE WHEN simulated_flat=1 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN simulated_flat=0 THEN 1 ELSE 0 END) "
        "FROM trades WHERE scenario_id=?",
        (scenario_id,),
    ).fetchone()
    total_decimal = Decimal(str(total or 0))
    connection.execute(
        "INSERT INTO scenario_summary VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(scenario_id) DO UPDATE SET "
        "total_simulated_net_pnl=excluded.total_simulated_net_pnl, "
        "total_simulated_net_pnl_text=excluded.total_simulated_net_pnl_text, "
        "simulated_closed_trade_count=excluded.simulated_closed_trade_count, "
        "simulated_open_position_count=excluded.simulated_open_position_count, "
        "generated_utc=excluded.generated_utc, "
        "input_snapshot_sequence=excluded.input_snapshot_sequence",
        (
            scenario_id,
            float(total_decimal),
            format(total_decimal, "f"),
            int(closed_count or 0),
            int(open_count or 0),
            generated_utc,
            snapshot_sequence,
        ),
    )


def apply_shadow_dashboard_increment(
    *,
    run_id: str,
    scenario_events: Mapping[str, Iterable[Mapping[str, object]]],
    generated_utc: str,
    input_snapshot_sequence: int,
    output_path: str | Path,
    scenario_diagnostics: Mapping[str, object] | None = None,
) -> None:
    """Apply one or more new event batches exactly once and advance cursors."""
    if set(scenario_events) != KNOWN_SCENARIO_IDS:
        raise ShadowDashboardReadModelError("increment requires the exact frozen scenario catalog")
    if not isinstance(run_id, str) or not run_id:
        raise ShadowDashboardReadModelError("dashboard run id is invalid")
    if not isinstance(generated_utc, str) or not generated_utc:
        raise ShadowDashboardReadModelError("dashboard generated UTC is invalid")
    if isinstance(input_snapshot_sequence, bool) or not isinstance(input_snapshot_sequence, int) or input_snapshot_sequence < 1:
        raise ShadowDashboardReadModelError("dashboard snapshot sequence is invalid")
    if scenario_diagnostics is not None and set(scenario_diagnostics) != KNOWN_SCENARIO_IDS:
        raise ShadowDashboardReadModelError("diagnostics require the exact frozen scenario catalog")

    connection = _open(Path(output_path))
    try:
        batches = {scenario_id: tuple(events) for scenario_id, events in scenario_events.items()}
        with connection:
            for scenario_id, events in batches.items():
                connection.execute(
                    "INSERT OR IGNORE INTO scenario_cursor VALUES (?, ?, 0, 0)",
                    (run_id, scenario_id),
                )
                last_event_sequence, last_snapshot_sequence = connection.execute(
                    "SELECT last_event_sequence, last_snapshot_sequence FROM scenario_cursor "
                    "WHERE run_id=? AND scenario_id=?",
                    (run_id, scenario_id),
                ).fetchone()
                if input_snapshot_sequence < last_snapshot_sequence:
                    raise ShadowDashboardReadModelError("dashboard snapshot cursor moved backward")
                expected = tuple(range(last_event_sequence + 1, last_event_sequence + 1 + len(events)))
                actual = tuple(event.get("event_sequence") for event in events)
                if actual != expected:
                    raise ShadowDashboardReadModelError("dashboard event cursor is not contiguous")
                for event in events:
                    normalized = _normalized_event(event, scenario_id)
                    connection.execute(
                        "INSERT INTO shadow_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        normalized,
                    )
                    _apply_trade_event(connection, event, scenario_id)
                next_event_sequence = last_event_sequence + len(events)
                connection.execute(
                    "UPDATE scenario_cursor SET last_event_sequence=?, last_snapshot_sequence=? "
                    "WHERE run_id=? AND scenario_id=?",
                    (next_event_sequence, input_snapshot_sequence, run_id, scenario_id),
                )
                _update_summary(
                    connection,
                    scenario_id=scenario_id,
                    generated_utc=generated_utc,
                    snapshot_sequence=input_snapshot_sequence,
                )
                if scenario_diagnostics is not None:
                    diagnostic = scenario_diagnostics[scenario_id]
                    counts = (
                        "snapshots_evaluated", "outside_entry_window", "no_evaluable_market",
                        "insufficient_visible_depth", "edge_below_threshold",
                        "eligible_candidate_selected", "position_open", "event_or_reentry_state",
                    )
                    if any(
                        isinstance(getattr(diagnostic, key, None), bool)
                        or not isinstance(getattr(diagnostic, key, None), int)
                        or getattr(diagnostic, key) < 0
                        for key in counts
                    ):
                        raise ShadowDashboardReadModelError("dashboard diagnostics are invalid")
                    connection.execute(
                        "INSERT INTO decision_diagnostics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(run_id, scenario_id) DO UPDATE SET "
                        "snapshots_evaluated=excluded.snapshots_evaluated, "
                        "outside_entry_window=excluded.outside_entry_window, "
                        "no_evaluable_market=excluded.no_evaluable_market, "
                        "insufficient_visible_depth=excluded.insufficient_visible_depth, "
                        "edge_below_threshold=excluded.edge_below_threshold, "
                        "eligible_candidate_selected=excluded.eligible_candidate_selected, "
                        "position_open=excluded.position_open, "
                        "event_or_reentry_state=excluded.event_or_reentry_state, "
                        "max_yes_net_edge=excluded.max_yes_net_edge, "
                        "max_no_net_edge=excluded.max_no_net_edge, "
                        "closest_net_edge_deficit=excluded.closest_net_edge_deficit",
                        (
                            run_id, scenario_id, *(getattr(diagnostic, key) for key in counts),
                            *(
                                None if getattr(diagnostic, key) is None else float(getattr(diagnostic, key))
                                for key in (
                                    "max_yes_net_edge", "max_no_net_edge",
                                    "closest_net_edge_deficit",
                                )
                            ),
                        ),
                    )
            connection.execute(
                "INSERT INTO dashboard_metadata(key, value) VALUES ('generated_utc', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (generated_utc,),
            )
            connection.execute(
                "INSERT INTO dashboard_metadata(key, value) VALUES ('input_snapshot_sequence', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(input_snapshot_sequence),),
            )
            connection.execute(
                "INSERT INTO dashboard_metadata(key, value) VALUES ('input_run_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (run_id,),
            )
    except sqlite3.Error as exc:
        raise ShadowDashboardReadModelError("unable to apply dashboard increment") from exc
    finally:
        connection.close()


def bootstrap_shadow_dashboard_read_model(
    *,
    run_id: str,
    scenario_events: Mapping[str, Iterable[Mapping[str, object]]],
    generated_utc: str,
    input_snapshot_sequence: int,
    output_path: str | Path,
    scenario_diagnostics: Mapping[str, object] | None = None,
) -> None:
    """Build a fresh read model from the authoritative append-only ledgers."""
    output = Path(output_path)
    if output.name != CANONICAL_READ_MODEL_FILENAME:
        raise ShadowDashboardReadModelError("dashboard read model filename is invalid")
    if output.exists():
        raise ShadowDashboardReadModelError("dashboard read model bootstrap requires a fresh path")
    apply_shadow_dashboard_increment(
        run_id=run_id,
        scenario_events=scenario_events,
        generated_utc=generated_utc,
        input_snapshot_sequence=input_snapshot_sequence,
        output_path=output,
        scenario_diagnostics=scenario_diagnostics,
    )


def read_shadow_dashboard_cursors(
    output_path: str | Path, run_id: str,
) -> dict[str, tuple[int, int]] | None:
    """Return this run's event/snapshot cursors, or None for a new run."""
    output = Path(output_path)
    if not output.exists():
        return None
    connection = _open(output)
    try:
        rows = connection.execute(
            "SELECT scenario_id, last_event_sequence, last_snapshot_sequence "
            "FROM scenario_cursor WHERE run_id=?", (run_id,)
        ).fetchall()
        if not rows:
            return None
        result = {row[0]: (int(row[1]), int(row[2])) for row in rows}
        if set(result) != KNOWN_SCENARIO_IDS:
            raise ShadowDashboardReadModelError("dashboard read model cursors are incomplete")
        return result
    finally:
        connection.close()


def replace_shadow_dashboard_read_model(
    *,
    scenario_events: Mapping[str, Iterable[Mapping[str, object]]],
    generated_utc: str,
    input_snapshot_sequence: int,
    output_path: str | Path,
) -> None:
    """Rebuild through a sibling temporary database and atomically replace it."""
    output = Path(output_path)
    if output.name != CANONICAL_READ_MODEL_FILENAME:
        raise ShadowDashboardReadModelError("dashboard read model filename is invalid")
    temporary = output.with_name(output.name + ".rebuild")
    if temporary.exists():
        temporary.unlink()
    try:
        bootstrap_shadow_dashboard_read_model(
            run_id="rebuild",
            scenario_events=scenario_events,
            generated_utc=generated_utc,
            input_snapshot_sequence=input_snapshot_sequence,
            output_path=temporary.with_name(CANONICAL_READ_MODEL_FILENAME),
        )
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    # bootstrap requires the canonical filename, so build in a private sibling directory.
    # This branch is intentionally handled below by the compatibility rebuild helper.
    raise ShadowDashboardReadModelError("direct replacement helper is not supported; use fresh bootstrap")


def refresh_shadow_dashboard_read_model(
    *,
    dashboard_snapshot: Mapping[str, object],
    scenario_events: Mapping[str, Iterable[Mapping[str, object]]],
    output_path: str | Path,
) -> None:
    """Compatibility full-build helper used by tests and offline tooling.

    Live operation uses ``bootstrap_shadow_dashboard_read_model`` exactly once
    and ``apply_shadow_dashboard_increment`` thereafter.
    """
    generated_utc = dashboard_snapshot.get("generated_utc")
    snapshot_sequence = dashboard_snapshot.get("input_snapshot_sequence")
    if not isinstance(generated_utc, str) or not generated_utc:
        raise ShadowDashboardReadModelError("dashboard generated UTC is invalid")
    if isinstance(snapshot_sequence, bool) or not isinstance(snapshot_sequence, int) or snapshot_sequence < 1:
        raise ShadowDashboardReadModelError("dashboard snapshot sequence is invalid")
    output = Path(output_path)
    if output.exists():
        output.unlink()
    run_ids = {
        event.get("run_id")
        for events in scenario_events.values()
        for event in events
        if isinstance(event.get("run_id"), str) and event.get("run_id")
    }
    if len(run_ids) > 1:
        raise ShadowDashboardReadModelError("dashboard events span multiple runs")
    bootstrap_shadow_dashboard_read_model(
        run_id=next(iter(run_ids), "offline-refresh"),
        scenario_events=scenario_events,
        generated_utc=generated_utc,
        input_snapshot_sequence=snapshot_sequence,
        output_path=output,
    )

# The comparison matrix is deliberately projected into parallel tables.  The
# original five-scenario dashboard remains readable across deployments while a
# strategy-lane run gets independent cursor, trade, and diagnostic keys.
def _create_strategy_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS strategy_lane_catalog (
            lane_id TEXT PRIMARY KEY,
            policy_id TEXT NOT NULL,
            scenario_id TEXT NOT NULL,
            edge_threshold REAL NOT NULL,
            edge_threshold_text TEXT NOT NULL,
            stop_loss_fraction REAL,
            profit_target_multiplier REAL NOT NULL,
            duration_cap_minutes REAL,
            trailing_activation_margin REAL
        );
        CREATE TABLE IF NOT EXISTS strategy_lane_cursor (
            run_id TEXT NOT NULL,
            lane_id TEXT NOT NULL,
            last_event_sequence INTEGER NOT NULL,
            last_snapshot_sequence INTEGER NOT NULL,
            PRIMARY KEY (run_id, lane_id)
        );
        CREATE TABLE IF NOT EXISTS strategy_lane_events (
            run_id TEXT NOT NULL,
            lane_id TEXT NOT NULL,
            event_sequence INTEGER NOT NULL,
            input_snapshot_sequence INTEGER NOT NULL,
            event_utc TEXT NOT NULL,
            event_type TEXT NOT NULL,
            position_id TEXT,
            market_ticker TEXT,
            action TEXT,
            reason TEXT,
            side TEXT,
            net_edge_per_contract REAL,
            simulated_quantity REAL,
            simulated_price REAL,
            simulated_fee REAL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (run_id, lane_id, event_sequence)
        );
        CREATE TABLE IF NOT EXISTS strategy_lane_trades (
            lane_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            position_id TEXT NOT NULL,
            market_ticker TEXT NOT NULL,
            entry_utc TEXT,
            exit_utc TEXT,
            entry_simulated_quantity REAL NOT NULL,
            exit_simulated_quantity REAL NOT NULL,
            net_simulated_position_quantity REAL NOT NULL,
            net_simulated_cash_flow REAL NOT NULL,
            simulated_net_pnl REAL,
            simulated_flat INTEGER NOT NULL CHECK (simulated_flat IN (0, 1)),
            simulation_fill_count INTEGER NOT NULL,
            fill_assumption TEXT NOT NULL,
            PRIMARY KEY (lane_id, run_id, position_id)
        );
        CREATE TABLE IF NOT EXISTS strategy_lane_diagnostics (
            run_id TEXT NOT NULL,
            lane_id TEXT NOT NULL,
            snapshots_evaluated INTEGER NOT NULL,
            outside_entry_window INTEGER NOT NULL,
            no_evaluable_market INTEGER NOT NULL,
            insufficient_visible_depth INTEGER NOT NULL,
            edge_below_threshold INTEGER NOT NULL,
            eligible_candidate_selected INTEGER NOT NULL,
            position_open INTEGER NOT NULL,
            event_or_reentry_state INTEGER NOT NULL,
            max_yes_net_edge REAL,
            max_no_net_edge REAL,
            closest_net_edge_deficit REAL,
            PRIMARY KEY (run_id, lane_id)
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_lane_events_lane_type
            ON strategy_lane_events(lane_id, event_type, event_sequence);
        CREATE INDEX IF NOT EXISTS idx_strategy_lane_trades_lane_exit
            ON strategy_lane_trades(lane_id, exit_utc);
    """)
    # This read model is a single file accumulated across every run this
    # host has ever done, not a per-run store -- an existing installation
    # predating the duration-cap/trailing-lock lanes needs these two nullable
    # columns added in place rather than being rejected as incompatible.
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(strategy_lane_catalog)").fetchall()
    }
    if "duration_cap_minutes" not in existing_columns:
        connection.execute("ALTER TABLE strategy_lane_catalog ADD COLUMN duration_cap_minutes REAL")
    if "trailing_activation_margin" not in existing_columns:
        connection.execute("ALTER TABLE strategy_lane_catalog ADD COLUMN trailing_activation_margin REAL")


def _strategy_normalized_event(event: Mapping[str, object], lane_id: str) -> tuple[object, ...]:
    if event.get("lane_id") != lane_id:
        raise ShadowDashboardReadModelError("strategy event lane lineage is invalid")
    base = _normalized_event(event, str(event.get("scenario_id")))
    return (base[0], lane_id, *base[2:])


def _apply_strategy_trade_event(connection: sqlite3.Connection, event: Mapping[str, object], lane_id: str) -> None:
    kind = event["event_type"]
    run_id = str(event["run_id"])
    position_id = _optional_text(event.get("position_id"))
    if kind == "shadow_simulated_fill":
        if event.get("fill_assumption") != EXACT_OBSERVED_DEPTH_IOC:
            raise ShadowDashboardReadModelError("strategy fill assumption is not approved")
        market = _optional_text(event.get("market_ticker")); side = _optional_text(event.get("side"))
        if not position_id or not market or side not in {"buy", "sell"}:
            raise ShadowDashboardReadModelError("strategy fill identity is invalid")
        quantity = _decimal(event.get("simulated_quantity"), "simulated_quantity", nonnegative=True)
        price = _decimal(event.get("simulated_price"), "simulated_price", nonnegative=True)
        fee = _decimal(event.get("simulated_fee"), "simulated_fee", nonnegative=True)
        if quantity <= 0 or price <= 0 or price > 1: raise ShadowDashboardReadModelError("strategy fill economics are invalid")
        row = connection.execute("SELECT market_ticker, net_simulated_position_quantity, net_simulated_cash_flow, simulated_flat, fill_assumption FROM strategy_lane_trades WHERE lane_id=? AND run_id=? AND position_id=?", (lane_id,run_id,position_id)).fetchone()
        if row is None:
            connection.execute("INSERT INTO strategy_lane_trades VALUES (?, ?, ?, ?, NULL, NULL, 0, 0, 0, 0, NULL, 0, 0, ?)", (lane_id,run_id,position_id,market,EXACT_OBSERVED_DEPTH_IOC)); net_quantity=Decimal("0"); net_cash=Decimal("0")
        else:
            if row[0] != market or row[3] or row[4] != EXACT_OBSERVED_DEPTH_IOC: raise ShadowDashboardReadModelError("strategy fill conflicts with projected trade")
            net_quantity=Decimal(str(row[1])); net_cash=Decimal(str(row[2]))
        utc=str(event["snapshot_generated_utc"])
        if side == "buy":
            connection.execute("UPDATE strategy_lane_trades SET entry_utc=COALESCE(entry_utc, ?), entry_simulated_quantity=entry_simulated_quantity+?, net_simulated_position_quantity=?, net_simulated_cash_flow=?, simulation_fill_count=simulation_fill_count+1 WHERE lane_id=? AND run_id=? AND position_id=?", (utc,float(quantity),float(net_quantity+quantity),float(net_cash-price*quantity-fee),lane_id,run_id,position_id))
        else:
            if net_quantity < quantity: raise ShadowDashboardReadModelError("strategy exit exceeds projected position")
            connection.execute("UPDATE strategy_lane_trades SET exit_utc=?, exit_simulated_quantity=exit_simulated_quantity+?, net_simulated_position_quantity=?, net_simulated_cash_flow=?, simulation_fill_count=simulation_fill_count+1 WHERE lane_id=? AND run_id=? AND position_id=?", (utc,float(quantity),float(net_quantity-quantity),float(net_cash+price*quantity-fee),lane_id,run_id,position_id))
    elif kind == "shadow_simulated_settlement":
        # A settlement-closed trade is a binary hold-to-expiry outcome, not a
        # bounded strategy exit -- the run's fixed duration ended before the
        # position's own exit rule got a chance to fire. Its simulated_net_pnl
        # is real (the true official result), but it is not comparable to a
        # strategy-exited trade's P&L: mixing them blends two different
        # scenarios. Distinguish with: a trade whose position_id has a
        # shadow_simulated_settlement event (this branch) closed via binary
        # settlement; one that instead has a shadow_simulated_fill sell event
        # closed via the strategy's own exit logic.
        market=_optional_text(event.get("market_ticker")); side=_optional_text(event.get("position_side")); result=_optional_text(event.get("official_market_result"))
        quantity=_decimal(event.get("settlement_quantity"), "settlement_quantity", nonnegative=True); payout=_decimal(event.get("simulated_settlement_payout"), "simulated_settlement_payout", nonnegative=True)
        row=connection.execute("SELECT market_ticker, net_simulated_position_quantity, net_simulated_cash_flow, simulated_flat FROM strategy_lane_trades WHERE lane_id=? AND run_id=? AND position_id=?", (lane_id,run_id,position_id)).fetchone()
        if not position_id or not market or side not in {"yes","no"} or result not in {"yes","no"} or not row or row[0] != market or row[3] or Decimal(str(row[1])) != quantity or payout != (quantity if side == result else Decimal("0")): raise ShadowDashboardReadModelError("strategy settlement conflicts with projected trade")
        connection.execute("UPDATE strategy_lane_trades SET exit_utc=?, net_simulated_position_quantity=0, net_simulated_cash_flow=? WHERE lane_id=? AND run_id=? AND position_id=?", (str(event["snapshot_generated_utc"]),float(Decimal(str(row[2]))+payout),lane_id,run_id,position_id))
    elif kind == "shadow_position_closed":
        row=connection.execute("SELECT net_simulated_position_quantity, net_simulated_cash_flow, simulated_flat FROM strategy_lane_trades WHERE lane_id=? AND run_id=? AND position_id=?", (lane_id,run_id,position_id)).fetchone()
        if not position_id or not row or row[2] or abs(float(row[0])) > 1e-9: raise ShadowDashboardReadModelError("strategy position is not flat at close")
        connection.execute("UPDATE strategy_lane_trades SET simulated_flat=1, simulated_net_pnl=? WHERE lane_id=? AND run_id=? AND position_id=?", (float(row[1]),lane_id,run_id,position_id))


def _upsert_strategy_diagnostic(connection: sqlite3.Connection, run_id: str, lane_id: str, diagnostic: object) -> None:
    counts=("snapshots_evaluated","outside_entry_window","no_evaluable_market","insufficient_visible_depth","edge_below_threshold","eligible_candidate_selected","position_open","event_or_reentry_state")
    if any(isinstance(getattr(diagnostic,key,None),bool) or not isinstance(getattr(diagnostic,key,None),int) or getattr(diagnostic,key)<0 for key in counts): raise ShadowDashboardReadModelError("strategy diagnostics are invalid")
    connection.execute("INSERT INTO strategy_lane_diagnostics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id,lane_id) DO UPDATE SET snapshots_evaluated=excluded.snapshots_evaluated,outside_entry_window=excluded.outside_entry_window,no_evaluable_market=excluded.no_evaluable_market,insufficient_visible_depth=excluded.insufficient_visible_depth,edge_below_threshold=excluded.edge_below_threshold,eligible_candidate_selected=excluded.eligible_candidate_selected,position_open=excluded.position_open,event_or_reentry_state=excluded.event_or_reentry_state,max_yes_net_edge=excluded.max_yes_net_edge,max_no_net_edge=excluded.max_no_net_edge,closest_net_edge_deficit=excluded.closest_net_edge_deficit", (run_id,lane_id,*(getattr(diagnostic,key) for key in counts),*(None if getattr(diagnostic,key) is None else float(getattr(diagnostic,key)) for key in ("max_yes_net_edge","max_no_net_edge","closest_net_edge_deficit"))))


def apply_shadow_strategy_dashboard_increment(*, run_id: str, lane_events: Mapping[str, Iterable[Mapping[str, object]]], lanes: Iterable[object], generated_utc: str, input_snapshot_sequence: int, output_path: str | Path, lane_diagnostics: Mapping[str, object]) -> None:
    lane_rows=tuple(lanes); catalog={item.lane_id:item for item in lane_rows}
    if set(lane_events) != set(catalog) or set(lane_diagnostics) != set(catalog): raise ShadowDashboardReadModelError("strategy matrix lane catalog is incomplete")
    connection=_open(Path(output_path))
    try:
        with connection:
            for lane in lane_rows:
                connection.execute("INSERT INTO strategy_lane_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(lane_id) DO UPDATE SET policy_id=excluded.policy_id,scenario_id=excluded.scenario_id,edge_threshold=excluded.edge_threshold,edge_threshold_text=excluded.edge_threshold_text,stop_loss_fraction=excluded.stop_loss_fraction,profit_target_multiplier=excluded.profit_target_multiplier,duration_cap_minutes=excluded.duration_cap_minutes,trailing_activation_margin=excluded.trailing_activation_margin", (lane.lane_id,lane.policy_id,lane.scenario.scenario_id,float(lane.scenario.edge_threshold),format(lane.scenario.edge_threshold,"f"),None if lane.stop_loss_fraction is None else float(lane.stop_loss_fraction),float(lane.profit_target_multiplier),None if lane.duration_cap_minutes is None else float(lane.duration_cap_minutes),None if lane.trailing_activation_margin is None else float(lane.trailing_activation_margin)))
                connection.execute("INSERT OR IGNORE INTO strategy_lane_cursor VALUES (?, ?, 0, 0)",(run_id,lane.lane_id))
                last_event,last_snapshot=connection.execute("SELECT last_event_sequence,last_snapshot_sequence FROM strategy_lane_cursor WHERE run_id=? AND lane_id=?",(run_id,lane.lane_id)).fetchone()
                events=tuple(lane_events[lane.lane_id]); actual=tuple(event.get("event_sequence") for event in events); expected=tuple(range(last_event+1,last_event+1+len(events)))
                if input_snapshot_sequence < last_snapshot or actual != expected: raise ShadowDashboardReadModelError("strategy event cursor is invalid")
                for event in events:
                    connection.execute("INSERT INTO strategy_lane_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", _strategy_normalized_event(event,lane.lane_id)); _apply_strategy_trade_event(connection,event,lane.lane_id)
                connection.execute("UPDATE strategy_lane_cursor SET last_event_sequence=?,last_snapshot_sequence=? WHERE run_id=? AND lane_id=?",(last_event+len(events),input_snapshot_sequence,run_id,lane.lane_id)); _upsert_strategy_diagnostic(connection,run_id,lane.lane_id,lane_diagnostics[lane.lane_id])
            for key,value in (("strategy_generated_utc",generated_utc),("strategy_input_snapshot_sequence",str(input_snapshot_sequence)),("strategy_input_run_id",run_id)):
                connection.execute("INSERT INTO dashboard_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
    except sqlite3.Error as exc: raise ShadowDashboardReadModelError("unable to apply strategy dashboard increment") from exc
    finally: connection.close()


def read_shadow_strategy_lane_cursors(output_path: str | Path, run_id: str, lanes: Iterable[object]) -> dict[str, tuple[int,int]] | None:
    output=Path(output_path)
    if not output.exists(): return None
    connection=_open(output)
    try:
        rows=connection.execute("SELECT lane_id,last_event_sequence,last_snapshot_sequence FROM strategy_lane_cursor WHERE run_id=?",(run_id,)).fetchall()
        if not rows: return None
        result={row[0]:(int(row[1]),int(row[2])) for row in rows}
        expected={lane.lane_id for lane in lanes}
        if set(result) != expected: raise ShadowDashboardReadModelError("strategy dashboard cursors are incomplete")
        return result
    finally: connection.close()
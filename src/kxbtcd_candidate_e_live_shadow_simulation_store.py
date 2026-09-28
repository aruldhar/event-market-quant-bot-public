"""Transactional, append-only local store for isolated live-shadow scenario events."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .kxbtcd_candidate_e_live_shadow_micro_simulator import (
    DURATION_CAP_MINUTES,
    MARKET_UNIVERSES,
    MOVING_ATM_ELEVEN,
    PROFIT_TARGET_MULTIPLIERS,
    STOP_LOSS_FRACTIONS,
    TRAILING_ACTIVATION_MARGINS,
    LiveShadowMicroState,
    LiveShadowDecisionDiagnostics,
    LiveShadowPendingSettlement,
)
from .kxbtcd_candidate_e_shadow_v2_scenarios import (
    PRIMARY_SHADOW_V2_SCENARIO,
    SHADOW_V2_SCENARIOS,
)
from .kxbtcd_candidate_e_shadow_strategy_lanes import SHADOW_STRATEGY_LANES


class LiveShadowSimulationStoreError(ValueError):
    pass


CANONICAL_STORE_FILENAME = "live_shadow_simulation.sqlite3"
STORE_SCHEMA_VERSION = "kxbtcd_candidate_e_live_shadow_simulation_store.v2"
KNOWN_SCENARIO_IDS = frozenset(item.scenario_id for item in SHADOW_V2_SCENARIOS)
KNOWN_SIMULATION_IDS = KNOWN_SCENARIO_IDS | frozenset(item.lane_id for item in SHADOW_STRATEGY_LANES)


@dataclass(frozen=True)
class LiveShadowStoredState:
    last_snapshot_sequence: int
    last_generated_utc: str | None
    next_event_sequence: int
    simulation_state: LiveShadowMicroState

    @classmethod
    def new(cls) -> "LiveShadowStoredState":
        return cls(0, None, 1, LiveShadowMicroState.new())


def _scenario_id(value: str) -> str:
    if value not in KNOWN_SIMULATION_IDS:
        raise LiveShadowSimulationStoreError("shadow scenario id is not in the frozen catalog")
    return value


def _state_json(state: LiveShadowMicroState) -> str:
    value = asdict(state)
    value["remaining_quantity"] = format(state.remaining_quantity, "f")
    value["entry_cost"] = format(state.entry_cost, "f")
    value["required_total_net_proceeds"] = (
        None if state.required_total_net_proceeds is None
        else format(state.required_total_net_proceeds, "f")
    )
    value["closed_event_tickers"] = sorted(state.closed_event_tickers)
    value["frozen_atm_market_tickers"] = list(state.frozen_atm_market_tickers)
    value["stop_loss_fraction"] = (
        None if state.stop_loss_fraction is None else format(state.stop_loss_fraction, "f")
    )
    value["profit_target_multiplier"] = format(state.profit_target_multiplier, "f")
    value["duration_cap_minutes"] = (
        None if state.duration_cap_minutes is None else format(state.duration_cap_minutes, "f")
    )
    value["trailing_activation_margin"] = (
        None if state.trailing_activation_margin is None
        else format(state.trailing_activation_margin, "f")
    )
    value["peak_favorable_price"] = (
        None if state.peak_favorable_price is None else format(state.peak_favorable_price, "f")
    )
    value["pending_settlements"] = [{
        "event_ticker": item.event_ticker,
        "position_id": item.position_id,
        "market_ticker": item.market_ticker,
        "side": item.side,
        "remaining_quantity": format(item.remaining_quantity, "f"),
        "entry_cost": format(item.entry_cost, "f"),
        "required_total_net_proceeds": format(item.required_total_net_proceeds, "f"),
    } for item in state.pending_settlements]
    value["decision_diagnostics"] = {
        "snapshots_evaluated": state.decision_diagnostics.snapshots_evaluated,
        "outside_entry_window": state.decision_diagnostics.outside_entry_window,
        "no_evaluable_market": state.decision_diagnostics.no_evaluable_market,
        "insufficient_visible_depth": state.decision_diagnostics.insufficient_visible_depth,
        "edge_below_threshold": state.decision_diagnostics.edge_below_threshold,
        "eligible_candidate_selected": state.decision_diagnostics.eligible_candidate_selected,
        "position_open": state.decision_diagnostics.position_open,
        "event_or_reentry_state": state.decision_diagnostics.event_or_reentry_state,
        "max_yes_net_edge": None if state.decision_diagnostics.max_yes_net_edge is None else format(state.decision_diagnostics.max_yes_net_edge, "f"),
        "max_no_net_edge": None if state.decision_diagnostics.max_no_net_edge is None else format(state.decision_diagnostics.max_no_net_edge, "f"),
        "closest_net_edge_deficit": None if state.decision_diagnostics.closest_net_edge_deficit is None else format(state.decision_diagnostics.closest_net_edge_deficit, "f"),
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _state_from_json(text: str) -> LiveShadowMicroState:
    try:
        value = json.loads(text)
        closed = value["closed_event_tickers"]
        if not isinstance(closed, list) or any(
            not isinstance(item, str) or not item for item in closed
        ):
            raise ValueError
        filled_entry_count = value.get("filled_entry_count", 0)
        reentry_market = value.get("reentry_reference_market_ticker")
        reentry_side = value.get("reentry_reference_side")
        reentry_not_before = value.get("reentry_not_before_snapshot_sequence", 0)
        pending_rows = value.get("pending_settlements", [])
        market_universe = value.get("market_universe", MOVING_ATM_ELEVEN)
        frozen_event = value.get("frozen_atm_event_ticker")
        frozen_tickers = value.get("frozen_atm_market_tickers", [])
        stop_loss_fraction = value.get("stop_loss_fraction")
        profit_target_multiplier = value.get("profit_target_multiplier", "1.00")
        duration_cap_minutes = value.get("duration_cap_minutes")
        trailing_activation_margin = value.get("trailing_activation_margin")
        entered_monotonic_ns = value.get("entered_monotonic_ns")
        peak_favorable_price = value.get("peak_favorable_price")
        if (
            isinstance(filled_entry_count, bool)
            or not isinstance(filled_entry_count, int)
            or filled_entry_count < 0
            or filled_entry_count > 2
            or reentry_market is not None and (not isinstance(reentry_market, str) or not reentry_market)
            or reentry_side is not None and reentry_side not in {"YES", "NO"}
            or (reentry_market is None) != (reentry_side is None)
            or isinstance(reentry_not_before, bool)
            or not isinstance(reentry_not_before, int)
            or reentry_not_before < 0
            or not isinstance(pending_rows, list)
            or market_universe not in MARKET_UNIVERSES
            or frozen_event is not None and (not isinstance(frozen_event, str) or not frozen_event)
            or not isinstance(frozen_tickers, list)
            or any(not isinstance(ticker, str) or not ticker for ticker in frozen_tickers)
            or len(set(frozen_tickers)) != len(frozen_tickers)
            or (stop_loss_fraction is not None and Decimal(stop_loss_fraction) not in STOP_LOSS_FRACTIONS)
            or Decimal(profit_target_multiplier) not in PROFIT_TARGET_MULTIPLIERS
            or (
                duration_cap_minutes is not None
                and Decimal(duration_cap_minutes) not in DURATION_CAP_MINUTES
            )
            or (
                trailing_activation_margin is not None
                and Decimal(trailing_activation_margin) not in TRAILING_ACTIVATION_MARGINS
            )
            or (
                entered_monotonic_ns is not None
                and (isinstance(entered_monotonic_ns, bool) or not isinstance(entered_monotonic_ns, int)
                     or entered_monotonic_ns < 0)
            )
        ):
            raise ValueError
        pending = tuple(LiveShadowPendingSettlement(
            event_ticker=row["event_ticker"], position_id=row["position_id"],
            market_ticker=row["market_ticker"], side=row["side"],
            remaining_quantity=Decimal(row["remaining_quantity"]),
            entry_cost=Decimal(row["entry_cost"]),
            required_total_net_proceeds=Decimal(row["required_total_net_proceeds"]),
        ) for row in pending_rows)
        if any(
            not item.event_ticker or not item.position_id or not item.market_ticker
            or item.side not in {"YES", "NO"} or item.remaining_quantity <= 0
            or item.entry_cost < 0 or item.required_total_net_proceeds < 0
            for item in pending
        ):
            raise ValueError
        raw_diagnostics = value.get("decision_diagnostics", {})
        if not isinstance(raw_diagnostics, dict):
            raise ValueError
        diagnostic_counts = (
            "snapshots_evaluated", "outside_entry_window", "no_evaluable_market",
            "insufficient_visible_depth", "edge_below_threshold",
            "eligible_candidate_selected", "position_open", "event_or_reentry_state",
        )
        diagnostics = LiveShadowDecisionDiagnostics(**{
            key: raw_diagnostics.get(key, 0) for key in diagnostic_counts
        }, **{
            key: (
                None if raw_diagnostics.get(key) is None else Decimal(raw_diagnostics[key])
            )
            for key in ("max_yes_net_edge", "max_no_net_edge", "closest_net_edge_deficit")
        })
        if any(
            isinstance(getattr(diagnostics, key), bool)
            or not isinstance(getattr(diagnostics, key), int)
            or getattr(diagnostics, key) < 0
            for key in diagnostic_counts
        ):
            raise ValueError
        return LiveShadowMicroState(
            event_ticker=value["event_ticker"],
            position_id=value["position_id"],
            market_ticker=value["market_ticker"],
            side=value["side"],
            remaining_quantity=Decimal(value["remaining_quantity"]),
            entry_cost=Decimal(value["entry_cost"]),
            required_total_net_proceeds=(
                None if value["required_total_net_proceeds"] is None
                else Decimal(value["required_total_net_proceeds"])
            ),
            entry_attempts=value["entry_attempts"],
            closed_event_tickers=frozenset(closed),
            filled_entry_count=filled_entry_count,
            reentry_reference_market_ticker=reentry_market,
            reentry_reference_side=reentry_side,
            reentry_not_before_snapshot_sequence=reentry_not_before,
            pending_settlements=pending,
            decision_diagnostics=diagnostics,
            market_universe=market_universe,
            frozen_atm_event_ticker=frozen_event,
            frozen_atm_market_tickers=tuple(frozen_tickers),
            stop_loss_fraction=(
                None if stop_loss_fraction is None else Decimal(stop_loss_fraction)
            ),
            profit_target_multiplier=Decimal(profit_target_multiplier),
            duration_cap_minutes=(
                None if duration_cap_minutes is None else Decimal(duration_cap_minutes)
            ),
            trailing_activation_margin=(
                None if trailing_activation_margin is None else Decimal(trailing_activation_margin)
            ),
            entered_monotonic_ns=entered_monotonic_ns,
            peak_favorable_price=(
                None if peak_favorable_price is None else Decimal(peak_favorable_price)
            ),
        )
    except (KeyError, TypeError, ValueError, ArithmeticError, json.JSONDecodeError) as exc:
        raise LiveShadowSimulationStoreError("stored simulation state is invalid") from exc


class LiveShadowSimulationStore:
    """Append-only scenario ledgers plus checkpoints in transactional SQLite."""

    def __init__(self, path: str | Path, *, read_only: bool = False):
        self.path = Path(path)
        if self.path.name != CANONICAL_STORE_FILENAME:
            raise LiveShadowSimulationStoreError("simulation store filename is invalid")
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = (
            sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
            if read_only else sqlite3.connect(self.path)
        )
        if not read_only:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
        try:
            if read_only:
                self._validate_schema()
            else:
                self._ensure_schema()
        except Exception:
            self.connection.close()
            raise

    def _ensure_schema(self) -> None:
        existing_tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in ("shadow_events", "shadow_runner_state"):
            if table not in existing_tables:
                continue
            columns = {
                row[1]
                for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "scenario_id" not in columns:
                raise LiveShadowSimulationStoreError(
                    "legacy single-scenario shadow store is incompatible; "
                    "start the multi-scenario runner with a fresh shadow-only store"
                )
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS shadow_store_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shadow_events (
                run_id TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, scenario_id, event_sequence)
            );
            CREATE TABLE IF NOT EXISTS shadow_runner_state (
                run_id TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                last_snapshot_sequence INTEGER NOT NULL,
                last_generated_utc TEXT,
                next_event_sequence INTEGER NOT NULL,
                simulation_state_json TEXT NOT NULL,
                PRIMARY KEY (run_id, scenario_id)
            );
        """)
        row = self.connection.execute(
            "SELECT value FROM shadow_store_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            self.connection.execute(
                "INSERT INTO shadow_store_metadata (key, value) VALUES ('schema_version', ?)",
                (STORE_SCHEMA_VERSION,),
            )
            self.connection.commit()
        elif row[0] != STORE_SCHEMA_VERSION:
            raise LiveShadowSimulationStoreError(
                "shadow simulation store schema version is incompatible"
            )

    def _validate_schema(self) -> None:
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"shadow_store_metadata", "shadow_events", "shadow_runner_state"}
        if not required.issubset(tables):
            raise LiveShadowSimulationStoreError("shadow simulation store schema is incomplete")
        for table in ("shadow_events", "shadow_runner_state"):
            columns = {
                row[1]
                for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "scenario_id" not in columns:
                raise LiveShadowSimulationStoreError(
                    "legacy single-scenario shadow store is incompatible; "
                    "start the multi-scenario runner with a fresh shadow-only store"
                )
        row = self.connection.execute(
            "SELECT value FROM shadow_store_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None or row[0] != STORE_SCHEMA_VERSION:
            raise LiveShadowSimulationStoreError("shadow simulation store schema version is incompatible")

    def close(self) -> None:
        self.connection.close()

    def load(
        self,
        run_id: str,
        scenario_id: str = PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
    ) -> LiveShadowStoredState:
        scenario_id = _scenario_id(scenario_id)
        row = self.connection.execute(
            "SELECT last_snapshot_sequence, last_generated_utc, "
            "next_event_sequence, simulation_state_json "
            "FROM shadow_runner_state WHERE run_id = ? AND scenario_id = ?",
            (run_id, scenario_id),
        ).fetchone()
        if row is None:
            return LiveShadowStoredState.new()
        sequence, utc, next_event_sequence, state_json = row
        if (
            not isinstance(sequence, int)
            or sequence < 0
            or not isinstance(next_event_sequence, int)
            or next_event_sequence < 1
            or (utc is not None and not isinstance(utc, str))
        ):
            raise LiveShadowSimulationStoreError(
                "stored simulation checkpoint is invalid"
            )
        return LiveShadowStoredState(
            sequence, utc, next_event_sequence, _state_from_json(state_json)
        )

    def events(
        self,
        run_id: str,
        scenario_id: str = PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
    ) -> tuple[dict[str, object], ...]:
        scenario_id = _scenario_id(scenario_id)
        rows = self.connection.execute(
            "SELECT payload_json FROM shadow_events "
            "WHERE run_id = ? AND scenario_id = ? ORDER BY event_sequence",
            (run_id, scenario_id),
        ).fetchall()
        try:
            return tuple(json.loads(row[0]) for row in rows)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LiveShadowSimulationStoreError(
                "stored shadow ledger is invalid"
            ) from exc

    def all_events(self, run_id: str) -> dict[str, tuple[dict[str, object], ...]]:
        return {
            scenario.scenario_id: self.events(run_id, scenario.scenario_id)
            for scenario in SHADOW_V2_SCENARIOS
        }

    def strategy_events(self, run_id: str) -> dict[str, tuple[dict[str, object], ...]]:
        """Return the independent lane ledgers for the comparison dashboard."""
        return {lane.lane_id: self.events(run_id, lane.lane_id) for lane in SHADOW_STRATEGY_LANES}

    def strategy_states(self, run_id: str) -> dict[str, LiveShadowStoredState]:
        return {lane.lane_id: self.load(run_id, lane.lane_id) for lane in SHADOW_STRATEGY_LANES}

    def states(self, run_id: str) -> dict[str, LiveShadowStoredState]:
        return {
            scenario.scenario_id: self.load(run_id, scenario.scenario_id)
            for scenario in SHADOW_V2_SCENARIOS
        }

    def commit_snapshot(
        self,
        *,
        run_id: str,
        snapshot_sequence: int,
        generated_utc: str,
        previous: LiveShadowStoredState,
        next_state: LiveShadowMicroState,
        events: Iterable[dict[str, object]],
        scenario_id: str = PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
    ) -> LiveShadowStoredState:
        scenario_id = _scenario_id(scenario_id)
        if snapshot_sequence <= previous.last_snapshot_sequence:
            raise LiveShadowSimulationStoreError(
                "snapshot sequence is not newer than stored state"
            )
        event_rows = tuple(events)
        expected_sequences = tuple(
            range(
                previous.next_event_sequence,
                previous.next_event_sequence + len(event_rows),
            )
        )
        actual_sequences = tuple(event.get("event_sequence") for event in event_rows)
        if actual_sequences != expected_sequences:
            raise LiveShadowSimulationStoreError(
                "shadow events do not have the expected contiguous sequence"
            )
        for event in event_rows:
            identity = event.get("lane_id", event.get("scenario_id"))
            if (
                event.get("run_id") != run_id
                or identity != scenario_id
                or event.get("input_snapshot_sequence") != snapshot_sequence
            ):
                raise LiveShadowSimulationStoreError(
                    "shadow event lineage is invalid"
                )
        next_event_sequence = previous.next_event_sequence + len(event_rows)
        try:
            with self.connection:
                self.connection.executemany(
                    "INSERT INTO shadow_events "
                    "(run_id, scenario_id, event_sequence, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        (
                            run_id,
                            scenario_id,
                            event["event_sequence"],
                            json.dumps(event, sort_keys=True, separators=(",", ":")),
                        )
                        for event in event_rows
                    ),
                )
                self.connection.execute(
                    "INSERT INTO shadow_runner_state "
                    "(run_id, scenario_id, last_snapshot_sequence, "
                    "last_generated_utc, next_event_sequence, simulation_state_json) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(run_id, scenario_id) DO UPDATE SET "
                    "last_snapshot_sequence=excluded.last_snapshot_sequence, "
                    "last_generated_utc=excluded.last_generated_utc, "
                    "next_event_sequence=excluded.next_event_sequence, "
                    "simulation_state_json=excluded.simulation_state_json",
                    (
                        run_id,
                        scenario_id,
                        snapshot_sequence,
                        generated_utc,
                        next_event_sequence,
                        _state_json(next_state),
                    ),
                )
        except sqlite3.Error as exc:
            raise LiveShadowSimulationStoreError(
                "unable to commit isolated simulation snapshot"
            ) from exc
        return LiveShadowStoredState(
            snapshot_sequence, generated_utc, next_event_sequence, next_state
        )

    def commit_settlement(
        self,
        *,
        run_id: str,
        previous: LiveShadowStoredState,
        next_state: LiveShadowMicroState,
        events: Iterable[dict[str, object]],
        scenario_id: str = PRIMARY_SHADOW_V2_SCENARIO.scenario_id,
    ) -> LiveShadowStoredState:
        """Append final-outcome events without inventing a new book snapshot."""
        scenario_id = _scenario_id(scenario_id)
        if previous.last_snapshot_sequence < 1:
            raise LiveShadowSimulationStoreError("settlement has no causal snapshot lineage")
        event_rows = tuple(events)
        expected = tuple(range(previous.next_event_sequence, previous.next_event_sequence + len(event_rows)))
        if tuple(event.get("event_sequence") for event in event_rows) != expected:
            raise LiveShadowSimulationStoreError("settlement events do not have contiguous sequence")
        for event in event_rows:
            identity = event.get("lane_id", event.get("scenario_id"))
            if (
                event.get("run_id") != run_id
                or identity != scenario_id
                or event.get("input_snapshot_sequence") != previous.last_snapshot_sequence
            ):
                raise LiveShadowSimulationStoreError("settlement event lineage is invalid")
        next_sequence = previous.next_event_sequence + len(event_rows)
        try:
            with self.connection:
                self.connection.executemany(
                    "INSERT INTO shadow_events (run_id, scenario_id, event_sequence, payload_json) VALUES (?, ?, ?, ?)",
                    ((run_id, scenario_id, event["event_sequence"], json.dumps(event, sort_keys=True, separators=(",", ":"))) for event in event_rows),
                )
                self.connection.execute(
                    "UPDATE shadow_runner_state SET last_generated_utc=?, next_event_sequence=?, simulation_state_json=? "
                    "WHERE run_id=? AND scenario_id=?",
                    (event_rows[-1]["snapshot_generated_utc"], next_sequence, _state_json(next_state), run_id, scenario_id),
                )
        except sqlite3.Error as exc:
            raise LiveShadowSimulationStoreError("unable to commit isolated simulation settlement") from exc
        return LiveShadowStoredState(previous.last_snapshot_sequence, str(event_rows[-1]["snapshot_generated_utc"]), next_sequence, next_state)

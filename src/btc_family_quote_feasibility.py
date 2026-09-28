"""Outcome-blind BTC-family historical quote-feasibility comparison.

Checkpoint 10 compares KXBTC15M, KXBTC, and KXBTCD without opening outcomes.
The primary evaluation unit is a settlement cluster. Real one-minute candles are
kept at their actual timestamps and assigned to normalized early/middle/late
bands within each market's own active lifetime. No anchor snapping, forward
fill, synthetic continuity, volume/liquidity selection, or outcome filtering is
allowed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .btc_family_quote_feasibility_schema import (
    CLUSTER_FIELDS,
    CLUSTER_SCHEMA_VERSION,
    LADDER_PROBES_PER_CLUSTER,
    MIN_CLUSTER_ANY_QUOTE_COVERAGE,
    MIN_CLUSTER_BAND_COVERAGE,
    MIN_LADDER_ALL_PROBE_ALL_BANDS_COVERAGE,
    MIN_PROBE_MARKET_ANY_QUOTE_COVERAGE,
    MODERN_LADDER_REGIME_ID,
    OBSERVATION_FIELDS,
    OBSERVATION_SCHEMA_VERSION,
    PROBE_FIELDS,
    PROBE_SCHEMA_VERSION,
    SUMMARY_FIELDS,
    SUMMARY_SCHEMA_VERSION,
    TARGET_CLUSTERS_PER_FAMILY,
    TARGET_FAMILIES,
    TIME_BANDS,
    WINDOW_FIELDS,
    WINDOW_SCHEMA_VERSION,
)
from .btc_rule_template import (
    BtcRuleTemplateError,
    validate_all_ladder_cluster_semantics,
)


class BtcFamilyQuoteFeasibilityError(RuntimeError):
    """Raised when the comparison cannot be completed without guessing."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference


class RawFirstJsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class InventoryInputs:
    manifest_path: Path
    manifest_sha256: str
    run_id: str
    market_csv_path: Path
    raw_archive_path: Path
    market_rows: tuple[dict[str, str], ...]
    raw_records: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class FeasibilityRows:
    clusters: tuple[dict[str, str], ...]
    probes: tuple[dict[str, str], ...]
    windows: tuple[dict[str, str], ...]
    observations: tuple[dict[str, str], ...]
    summaries: tuple[dict[str, str], ...]
    inventory_run_id: str
    inventory_manifest_path: str
    inventory_manifest_sha256: str
    cutoff_market_settled_ts: str
    cutoff_raw_source: str
    cutoff_raw_session_id: str
    cutoff_raw_request_id: str


@dataclass(frozen=True)
class CsvPaths:
    clusters: Path
    probes: Path
    windows: Path
    observations: Path
    summaries: Path

    def all(self) -> tuple[Path, ...]:
        return (self.clusters, self.probes, self.windows, self.observations, self.summaries)


def load_latest_completed_inventory(
    repository_root: str | Path = ".",
    *,
    manifest_root: str | Path = "data/manifests",
) -> InventoryInputs:
    repo = Path(repository_root).resolve()
    root = (repo / manifest_root).resolve() if not Path(manifest_root).is_absolute() else Path(manifest_root)
    candidates = sorted(
        root.rglob("collect_btc_research_unit_inventory_*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") != "completed":
            continue
        collector = manifest.get("collector")
        if not isinstance(collector, Mapping) or collector.get("name") != "collect_btc_research_unit_inventory":
            continue
        run_id = _required_text(manifest.get("run_id"), "inventory manifest run_id")
        files = manifest.get("files")
        if not isinstance(files, list):
            raise BtcFamilyQuoteFeasibilityError("inventory manifest files must be a list")
        market_paths: list[Path] = []
        raw_paths: list[Path] = []
        for item in files:
            if not isinstance(item, Mapping):
                continue
            spec = item.get("path")
            if not isinstance(spec, Mapping):
                continue
            resolved = _resolve_stored_path(spec, repo)
            if item.get("role") == "derived_csv" and "btc_markets" in resolved.name:
                market_paths.append(resolved)
            elif item.get("role") == "raw_api_archive":
                raw_paths.append(resolved)
        if len(market_paths) != 1 or len(raw_paths) != 1:
            raise BtcFamilyQuoteFeasibilityError(
                "completed BTC inventory must contain exactly one btc_markets CSV and one raw archive"
            )
        market_rows = _read_csv(market_paths[0])
        raw_records = _read_jsonl(raw_paths[0])
        return InventoryInputs(
            manifest_path=path.resolve(),
            manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            run_id=run_id,
            market_csv_path=market_paths[0],
            raw_archive_path=raw_paths[0],
            market_rows=tuple(market_rows),
            raw_records=tuple(raw_records),
        )
    raise BtcFamilyQuoteFeasibilityError("no completed Checkpoint-10 BTC inventory manifest found")


def build_selected_clusters_and_probes(
    *,
    run_id: str,
    inventory: InventoryInputs,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build an equal 20-cluster/family sample without quote/outcome selection."""

    market_rows = list(inventory.market_rows)
    by_series_event: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in market_rows:
        series = row.get("series_ticker", "")
        event = row.get("event_ticker", "")
        if series and event:
            by_series_event.setdefault((series, event), []).append(row)

    ladder_summaries = validate_all_ladder_cluster_semantics(
        market_rows,
        inventory.raw_records,
        series_tickers=("KXBTC", "KXBTCD"),
    )
    ladder_by_series: dict[str, list[Any]] = {"KXBTC": [], "KXBTCD": []}
    for summary in ladder_summaries:
        if summary.regime_id == MODERN_LADDER_REGIME_ID:
            ladder_by_series[summary.series_ticker].append(summary)

    selected_specs: list[tuple[str, str, str, str, str, list[dict[str, str]]]] = []

    # KXBTC15M is already resolved in the inventory as a two-boundary family.
    fifteen_candidates: list[tuple[str, list[dict[str, str]]]] = []
    for (series, event), rows in by_series_event.items():
        if series != "KXBTC15M":
            continue
        if any(row.get("cluster_status") != "resolved" for row in rows):
            raise BtcFamilyQuoteFeasibilityError(
                f"KXBTC15M event {event} is not resolved in the source inventory"
            )
        fifteen_candidates.append((event, rows))
    selected_15 = _hash_select(fifteen_candidates, TARGET_CLUSTERS_PER_FAMILY, key=lambda item: item[0])
    for event, rows in selected_15:
        cluster_ids = {_required_text(row.get("settlement_cluster_id"), "settlement_cluster_id") for row in rows}
        if len(cluster_ids) != 1:
            raise BtcFamilyQuoteFeasibilityError(f"KXBTC15M event {event} has multiple cluster IDs")
        probe = _hash_select(rows, 1, key=lambda row: _required_text(row.get("ticker"), "ticker"))
        primitives = {_required_text(row.get("primitive_ids_json"), "primitive_ids_json") for row in rows}
        if len(primitives) != 1:
            raise BtcFamilyQuoteFeasibilityError(f"KXBTC15M event {event} has inconsistent primitives")
        selected_specs.append((
            "KXBTC15M", event, next(iter(cluster_ids)),
            "kxbtc15m_two_boundary_brti_average_direction",
            next(iter(primitives)), probe,
        ))

    for series in ("KXBTC", "KXBTCD"):
        eligible = ladder_by_series[series]
        chosen = _hash_select(eligible, TARGET_CLUSTERS_PER_FAMILY, key=lambda item: item.event_ticker)
        for summary in chosen:
            rows = by_series_event.get((series, summary.event_ticker), [])
            if len(rows) != summary.market_count:
                raise BtcFamilyQuoteFeasibilityError(
                    f"{series} event {summary.event_ticker} market count changed after semantic validation"
                )
            probes = select_structural_probe_markets(rows)
            selected_specs.append((
                series,
                summary.event_ticker,
                summary.source_cluster_id,
                summary.regime_id,
                json.dumps([summary.settlement_primitive_id], separators=(",", ":")),
                probes,
            ))

    cluster_rows: list[dict[str, str]] = []
    probe_rows: list[dict[str, str]] = []
    counts = {family: 0 for family in TARGET_FAMILIES}

    for family, event, cluster_id, regime_id, primitives_json, probes in selected_specs:
        counts[family] += 1
        open_times = {_required_text(row.get("open_time"), "open_time") for row in probes}
        close_times = {_required_text(row.get("close_time"), "close_time") for row in probes}
        if len(open_times) != 1 or len(close_times) != 1:
            raise BtcFamilyQuoteFeasibilityError(
                f"selected probe markets for {family} event {event} do not share one active window"
            )
        open_time = next(iter(open_times))
        close_time = next(iter(close_times))
        duration = _duration_seconds(open_time, close_time)
        cluster_rows.append({
            "schema_version": CLUSTER_SCHEMA_VERSION,
            "run_id": run_id,
            "inventory_run_id": inventory.run_id,
            "family": family,
            "series_ticker": family,
            "event_ticker": event,
            "source_cluster_id": cluster_id,
            "regime_id": regime_id,
            "primitive_ids_json": primitives_json,
            "open_time": open_time,
            "close_time": close_time,
            "duration_seconds": str(duration),
            "selection_hash": _selection_hash(event),
            "probe_market_count": str(len(probes)),
            "cluster_selection_rule": "sha256_event_ticker_ascending_equal_20_per_family",
        })
        roles = ["single"] if family == "KXBTC15M" else ["q25", "q50", "q75"]
        if len(roles) != len(probes):
            raise BtcFamilyQuoteFeasibilityError(f"unexpected probe count for {family} {event}")
        for role, row in zip(roles, probes):
            probe_rows.append({
                "schema_version": PROBE_SCHEMA_VERSION,
                "run_id": run_id,
                "inventory_run_id": inventory.run_id,
                "family": family,
                "event_ticker": event,
                "source_cluster_id": cluster_id,
                "ticker": _required_text(row.get("ticker"), "ticker"),
                "probe_role": role,
                "strike_type": str(row.get("strike_type") or ""),
                "floor_strike": str(row.get("floor_strike") or ""),
                "cap_strike": str(row.get("cap_strike") or ""),
                "functional_strike": str(row.get("functional_strike") or ""),
                "open_time": _required_text(row.get("open_time"), "open_time"),
                "close_time": _required_text(row.get("close_time"), "close_time"),
                "settlement_ts": _required_text(row.get("settlement_ts"), "settlement_ts"),
                "inventory_raw_source": _required_text(row.get("raw_source"), "raw_source"),
                "inventory_raw_session_id": _required_text(row.get("raw_session_id"), "raw_session_id"),
                "inventory_raw_request_id": _required_text(row.get("raw_request_id"), "raw_request_id"),
            })

    if counts != {family: TARGET_CLUSTERS_PER_FAMILY for family in TARGET_FAMILIES}:
        raise BtcFamilyQuoteFeasibilityError(f"equal family sample not achieved: {counts}")
    _validate_exact_rows(cluster_rows, CLUSTER_FIELDS, "cluster")
    _validate_exact_rows(probe_rows, PROBE_FIELDS, "probe")
    return cluster_rows, probe_rows


def select_structural_probe_markets(rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Select 25th/50th/75th structural strike positions, outcome/quote blind."""

    if len(rows) < LADDER_PROBES_PER_CLUSTER:
        raise BtcFamilyQuoteFeasibilityError("ladder event has fewer than three markets")
    positioned: list[tuple[Decimal, str, dict[str, str]]] = []
    for original in rows:
        row = dict(original)
        anchor = _strike_anchor(row)
        positioned.append((anchor, _required_text(row.get("ticker"), "ticker"), row))
    positioned.sort(key=lambda item: (item[0], item[1]))
    indexes = [math.floor((len(positioned) - 1) * q) for q in (0.25, 0.50, 0.75)]
    if len(set(indexes)) != 3:
        raise BtcFamilyQuoteFeasibilityError("structural quantile probes collapsed to duplicate positions")
    return [positioned[index][2] for index in indexes]


def collect_quote_feasibility_rows(
    client: RawFirstJsonClient,
    *,
    run_id: str,
    inventory: InventoryInputs,
) -> FeasibilityRows:
    cluster_rows, probe_rows = build_selected_clusters_and_probes(run_id=run_id, inventory=inventory)
    cutoff_response = client.get_json("/historical/cutoff")
    cutoff_text = _required_text(cutoff_response.payload.get("market_settled_ts"), "market_settled_ts")
    cutoff = _parse_utc(cutoff_text, "market_settled_ts")

    windows: list[dict[str, str]] = []
    observations: list[dict[str, str]] = []
    cluster_lookup = {row["source_cluster_id"]: row for row in cluster_rows}

    for probe in probe_rows:
        family = probe["family"]
        ticker = probe["ticker"]
        settlement = _parse_utc(probe["settlement_ts"], "settlement_ts")
        route_tier = "historical" if settlement < cutoff else "live"
        open_dt = _parse_utc(probe["open_time"], "open_time")
        close_dt = _parse_utc(probe["close_time"], "close_time")
        duration = int((close_dt - open_dt).total_seconds())
        if duration <= 0:
            raise BtcFamilyQuoteFeasibilityError(f"non-positive active duration for {ticker}")
        start_ts = int(open_dt.timestamp())
        end_ts = int(close_dt.timestamp())
        params: dict[str, Any] = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": 1,
        }
        if route_tier == "historical":
            path = f"/historical/markets/{ticker}/candlesticks"
        else:
            path = f"/series/{family}/markets/{ticker}/candlesticks"
            params["include_latest_before_start"] = "false"
        response = client.get_json(path, params=params)
        obs = build_observation_rows(
            run_id=run_id,
            inventory_run_id=inventory.run_id,
            family=family,
            event_ticker=probe["event_ticker"],
            cluster_id=probe["source_cluster_id"],
            ticker=ticker,
            probe_role=probe["probe_role"],
            open_time=open_dt,
            close_time=close_dt,
            route_tier=route_tier,
            response=response,
        )
        observations.extend(obs)
        counts = {band: 0 for band in TIME_BANDS}
        valid = [row for row in obs if row["valid_quote_observation"] == "true"]
        for row in valid:
            counts[row["time_band"]] += 1
        windows.append({
            "schema_version": WINDOW_SCHEMA_VERSION,
            "run_id": run_id,
            "inventory_run_id": inventory.run_id,
            "raw_source": _required_text(response.raw_record.source, "raw.source"),
            "raw_session_id": _required_text(response.raw_record.session_id, "raw.session_id"),
            "raw_request_id": _required_text(response.raw_record.request_id, "raw.request_id"),
            "route_tier": route_tier,
            "family": family,
            "event_ticker": probe["event_ticker"],
            "source_cluster_id": probe["source_cluster_id"],
            "ticker": ticker,
            "probe_role": probe["probe_role"],
            "open_time": probe["open_time"],
            "close_time": probe["close_time"],
            "duration_seconds": str(duration),
            "period_interval_minutes": "1",
            "candle_count": str(len(obs)),
            "valid_quote_observation_count": str(len(valid)),
            "invalid_quote_observation_count": str(len(obs) - len(valid)),
            "crossed_quote_count": str(sum(row["crossed_close"] == "true" for row in obs)),
            "early_valid_count": str(counts["early"]),
            "middle_valid_count": str(counts["middle"]),
            "late_valid_count": str(counts["late"]),
        })

    summaries = build_summary_rows(cluster_rows, probe_rows, observations)
    _validate_exact_rows(windows, WINDOW_FIELDS, "window")
    _validate_exact_rows(observations, OBSERVATION_FIELDS, "observation")
    _validate_exact_rows(summaries, SUMMARY_FIELDS, "summary")

    return FeasibilityRows(
        clusters=tuple(cluster_rows),
        probes=tuple(probe_rows),
        windows=tuple(windows),
        observations=tuple(observations),
        summaries=tuple(summaries),
        inventory_run_id=inventory.run_id,
        inventory_manifest_path=str(inventory.manifest_path),
        inventory_manifest_sha256=inventory.manifest_sha256,
        cutoff_market_settled_ts=cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        cutoff_raw_source=_required_text(cutoff_response.raw_record.source, "cutoff raw source"),
        cutoff_raw_session_id=_required_text(cutoff_response.raw_record.session_id, "cutoff raw session"),
        cutoff_raw_request_id=_required_text(cutoff_response.raw_record.request_id, "cutoff raw request"),
    )


def build_observation_rows(
    *,
    run_id: str,
    inventory_run_id: str,
    family: str,
    event_ticker: str,
    cluster_id: str,
    ticker: str,
    probe_role: str,
    open_time: datetime,
    close_time: datetime,
    route_tier: str,
    response: RawFirstJsonResponse,
) -> list[dict[str, str]]:
    payload_ticker = _required_text(response.payload.get("ticker"), "candles.ticker")
    if payload_ticker != ticker:
        raise BtcFamilyQuoteFeasibilityError(
            f"candlestick ticker mismatch: expected {ticker}, got {payload_ticker}"
        )
    candles = response.payload.get("candlesticks")
    if not isinstance(candles, list):
        raise BtcFamilyQuoteFeasibilityError("candlesticks must be a list")
    close_key = "close" if route_tier == "historical" else "close_dollars"
    family_fields = "historical_plain" if route_tier == "historical" else "live_dollars"
    start_ts = int(open_time.timestamp())
    close_ts = int(close_time.timestamp())
    duration = close_ts - start_ts
    if duration <= 0:
        raise BtcFamilyQuoteFeasibilityError(f"invalid active duration for {ticker}")
    seen: set[int] = set()
    rows: list[dict[str, str]] = []
    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise BtcFamilyQuoteFeasibilityError(f"candlesticks[{index}] must be an object")
        end_ts = candle.get("end_period_ts")
        if not isinstance(end_ts, int) or isinstance(end_ts, bool):
            raise BtcFamilyQuoteFeasibilityError("candle end_period_ts must be integer")
        if end_ts in seen:
            raise BtcFamilyQuoteFeasibilityError(f"duplicate candle timestamp {end_ts} for {ticker}")
        seen.add(end_ts)
        if not start_ts <= end_ts <= close_ts:
            raise BtcFamilyQuoteFeasibilityError(
                f"candle {end_ts} for {ticker} lies outside active lifetime [{start_ts}, {close_ts}]"
            )
        bid_obj = _mapping_or_none(candle.get("yes_bid"), "yes_bid")
        ask_obj = _mapping_or_none(candle.get("yes_ask"), "yes_ask")
        bid = _decimal_or_none(None if bid_obj is None else bid_obj.get(close_key))
        ask = _decimal_or_none(None if ask_obj is None else ask_obj.get(close_key))
        pair = bid is not None and ask is not None
        crossed = bool(pair and bid > ask)
        valid = False
        reason = ""
        q_mid = ""
        spread = ""
        if bid is None and ask is None:
            reason = "missing_bid_and_ask"
        elif bid is None:
            reason = "missing_bid"
        elif ask is None:
            reason = "missing_ask"
        elif bid < 0 or bid > 1 or ask < 0 or ask > 1:
            reason = "quote_out_of_range"
        elif bid > ask:
            reason = "crossed_quote"
        else:
            valid = True
            q_mid = _decimal_text((bid + ask) / Decimal("2"))
            spread = _decimal_text(ask - bid)
        ttc = close_ts - end_ts
        band = normalized_time_band(ttc, duration)
        rows.append({
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "run_id": run_id,
            "inventory_run_id": inventory_run_id,
            "raw_source": _required_text(response.raw_record.source, "raw.source"),
            "raw_session_id": _required_text(response.raw_record.session_id, "raw.session_id"),
            "raw_request_id": _required_text(response.raw_record.request_id, "raw.request_id"),
            "route_tier": route_tier,
            "family": family,
            "event_ticker": event_ticker,
            "source_cluster_id": cluster_id,
            "ticker": ticker,
            "probe_role": probe_role,
            "source_field_family": family_fields,
            "end_period_ts": str(end_ts),
            "open_time": _format_utc(open_time),
            "close_time": _format_utc(close_time),
            "duration_seconds": str(duration),
            "time_to_close_seconds": str(ttc),
            "normalized_time_remaining": f"{ttc / duration:.6f}",
            "time_band": band,
            "period_interval_minutes": "1",
            "yes_bid_close": _decimal_text(bid),
            "yes_ask_close": _decimal_text(ask),
            "q_mid": q_mid,
            "spread": spread,
            "quote_pair_present": _bool_text(pair),
            "crossed_close": _bool_text(crossed),
            "valid_quote_observation": _bool_text(valid),
            "exclusion_reason": reason,
        })
    rows.sort(key=lambda row: int(row["end_period_ts"]))
    return rows


def normalized_time_band(time_to_close_seconds: int, duration_seconds: int) -> str:
    if duration_seconds <= 0:
        raise BtcFamilyQuoteFeasibilityError("duration_seconds must be positive")
    if not 0 <= time_to_close_seconds <= duration_seconds:
        raise BtcFamilyQuoteFeasibilityError("time_to_close_seconds outside active lifetime")
    # Exact rational comparisons avoid floating boundary drift.
    if 3 * time_to_close_seconds >= 2 * duration_seconds:
        return "early"
    if 3 * time_to_close_seconds >= duration_seconds:
        return "middle"
    return "late"


def build_summary_rows(
    clusters: Sequence[Mapping[str, str]],
    probes: Sequence[Mapping[str, str]],
    observations: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for family in TARGET_FAMILIES:
        family_clusters = [row for row in clusters if row["family"] == family]
        family_probes = [row for row in probes if row["family"] == family]
        family_valid = [
            row for row in observations
            if row["family"] == family and row["valid_quote_observation"] == "true"
        ]
        cluster_ids = [row["source_cluster_id"] for row in family_clusters]
        probe_ids = [row["ticker"] for row in family_probes]
        valid_by_cluster = {cluster: [] for cluster in cluster_ids}
        valid_by_probe = {ticker: [] for ticker in probe_ids}
        for row in family_valid:
            valid_by_cluster[row["source_cluster_id"]].append(row)
            valid_by_probe[row["ticker"]].append(row)
        cluster_with = sum(bool(rows) for rows in valid_by_cluster.values())
        probe_with = sum(bool(rows) for rows in valid_by_probe.values())
        band_cluster_sets = {band: set() for band in TIME_BANDS}
        for row in family_valid:
            band_cluster_sets[row["time_band"]].add(row["source_cluster_id"])
        all_three = set(cluster_ids)
        for band in TIME_BANDS:
            all_three &= band_cluster_sets[band]

        probes_by_cluster: dict[str, list[str]] = {cluster: [] for cluster in cluster_ids}
        for row in family_probes:
            probes_by_cluster[row["source_cluster_id"]].append(row["ticker"])
        all_probe_band_sets = {band: set() for band in TIME_BANDS}
        for cluster, tickers in probes_by_cluster.items():
            for band in TIME_BANDS:
                if tickers and all(
                    any(obs["time_band"] == band for obs in valid_by_probe[ticker])
                    for ticker in tickers
                ):
                    all_probe_band_sets[band].add(cluster)
        all_probe_all_three = set(cluster_ids)
        for band in TIME_BANDS:
            all_probe_all_three &= all_probe_band_sets[band]

        n_clusters = len(family_clusters)
        n_probes = len(family_probes)
        cluster_any = _ratio(cluster_with, n_clusters)
        probe_any = _ratio(probe_with, n_probes)
        band_cov = {band: _ratio(len(band_cluster_sets[band]), n_clusters) for band in TIME_BANDS}
        all_three_cov = _ratio(len(all_three), n_clusters)
        all_probe_band_cov = {
            band: _ratio(len(all_probe_band_sets[band]), n_clusters) for band in TIME_BANDS
        }
        all_probe_all_three_cov = _ratio(len(all_probe_all_three), n_clusters)
        target_met = n_clusters == TARGET_CLUSTERS_PER_FAMILY
        base_pass = (
            target_met
            and cluster_any >= MIN_CLUSTER_ANY_QUOTE_COVERAGE
            and probe_any >= MIN_PROBE_MARKET_ANY_QUOTE_COVERAGE
            and all(band_cov[band] >= MIN_CLUSTER_BAND_COVERAGE for band in TIME_BANDS)
        )
        ladder_applicable = family in {"KXBTC", "KXBTCD"}
        ladder_pass = (
            all_probe_all_three_cov >= MIN_LADDER_ALL_PROBE_ALL_BANDS_COVERAGE
            if ladder_applicable else True
        )
        if not target_met:
            status = "insufficient_cluster_sample"
        elif not base_pass:
            status = "quote_feasibility_gate_failed"
        elif ladder_applicable and not ladder_pass:
            status = "quote_feasibility_pass_ladder_breadth_failed"
        else:
            status = "quote_feasibility_pass"
        durations = sorted(int(row["duration_seconds"]) for row in family_clusters)
        output.append({
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "family": family,
            "target_cluster_count": str(TARGET_CLUSTERS_PER_FAMILY),
            "cluster_count": str(n_clusters),
            "probe_market_count": str(n_probes),
            "valid_quote_observation_count": str(len(family_valid)),
            "clusters_with_valid_quote": str(cluster_with),
            "probe_markets_with_valid_quote": str(probe_with),
            "cluster_any_quote_coverage": _float_text(cluster_any),
            "probe_market_any_quote_coverage": _float_text(probe_any),
            "early_cluster_coverage": _float_text(band_cov["early"]),
            "middle_cluster_coverage": _float_text(band_cov["middle"]),
            "late_cluster_coverage": _float_text(band_cov["late"]),
            "all_three_band_cluster_coverage": _float_text(all_three_cov),
            "all_probe_early_cluster_coverage": _float_text(all_probe_band_cov["early"]),
            "all_probe_middle_cluster_coverage": _float_text(all_probe_band_cov["middle"]),
            "all_probe_late_cluster_coverage": _float_text(all_probe_band_cov["late"]),
            "all_probe_all_three_band_cluster_coverage": _float_text(all_probe_all_three_cov),
            "median_duration_seconds": _float_text(float(median(durations)) if durations else 0.0),
            "min_duration_seconds": str(min(durations) if durations else 0),
            "max_duration_seconds": str(max(durations) if durations else 0),
            "sample_target_met": _bool_text(target_met),
            "base_quote_feasibility_pass": _bool_text(base_pass),
            "ladder_breadth_gate_applicable": _bool_text(ladder_applicable),
            "ladder_breadth_pass": _bool_text(ladder_pass),
            "status": status,
        })
    return output


def validate_rows(rows: FeasibilityRows, *, run_id: str) -> dict[str, int]:
    _validate_exact_rows(rows.clusters, CLUSTER_FIELDS, "cluster")
    _validate_exact_rows(rows.probes, PROBE_FIELDS, "probe")
    _validate_exact_rows(rows.windows, WINDOW_FIELDS, "window")
    _validate_exact_rows(rows.observations, OBSERVATION_FIELDS, "observation")
    _validate_exact_rows(rows.summaries, SUMMARY_FIELDS, "summary")
    for collection in (rows.clusters, rows.probes, rows.windows, rows.observations):
        for row in collection:
            if row["run_id"] != run_id:
                raise BtcFamilyQuoteFeasibilityError("derived row run_id mismatch")
            if row["inventory_run_id"] != rows.inventory_run_id:
                raise BtcFamilyQuoteFeasibilityError("derived row inventory_run_id mismatch")
    family_cluster_counts = {
        family: sum(row["family"] == family for row in rows.clusters)
        for family in TARGET_FAMILIES
    }
    if family_cluster_counts != {family: TARGET_CLUSTERS_PER_FAMILY for family in TARGET_FAMILIES}:
        raise BtcFamilyQuoteFeasibilityError(f"family cluster counts changed: {family_cluster_counts}")
    if any("result" in row for row in rows.observations):
        raise BtcFamilyQuoteFeasibilityError("outcome field materialized in observation rows")
    return {
        "cluster_rows": len(rows.clusters),
        "probe_rows": len(rows.probes),
        "window_rows": len(rows.windows),
        "observation_rows": len(rows.observations),
        "valid_quote_observation_rows": sum(
            row["valid_quote_observation"] == "true" for row in rows.observations
        ),
    }


def write_csvs(output_dir: str | Path, *, run_id: str, rows: FeasibilityRows) -> CsvPaths:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = CsvPaths(
        clusters=root / f"{run_id}_btc_family_clusters.csv",
        probes=root / f"{run_id}_btc_family_probe_markets.csv",
        windows=root / f"{run_id}_btc_family_quote_windows.csv",
        observations=root / f"{run_id}_btc_family_quote_observations.csv",
        summaries=root / f"{run_id}_btc_family_quote_summary.csv",
    )
    for path, fields, data in (
        (paths.clusters, CLUSTER_FIELDS, rows.clusters),
        (paths.probes, PROBE_FIELDS, rows.probes),
        (paths.windows, WINDOW_FIELDS, rows.windows),
        (paths.observations, OBSERVATION_FIELDS, rows.observations),
        (paths.summaries, SUMMARY_FIELDS, rows.summaries),
    ):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)
    return paths


def _strike_anchor(row: Mapping[str, str]) -> Decimal:
    floor = _decimal_or_none(row.get("floor_strike"))
    cap = _decimal_or_none(row.get("cap_strike"))
    functional = _decimal_or_none(row.get("functional_strike"))
    if floor is not None and cap is not None:
        return (floor + cap) / Decimal("2")
    if floor is not None:
        return floor
    if cap is not None:
        return cap
    if functional is not None:
        return functional
    raise BtcFamilyQuoteFeasibilityError(
        f"market {_required_text(row.get('ticker'), 'ticker')} has no structural strike coordinate"
    )


def _hash_select(items: Sequence[Any], count: int, *, key) -> list[Any]:
    if len(items) < count:
        raise BtcFamilyQuoteFeasibilityError(
            f"need {count} eligible items but only {len(items)} are available"
        )
    return sorted(items, key=lambda item: (_selection_hash(key(item)), key(item)))[:count]


def _selection_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _duration_seconds(open_time: str, close_time: str) -> int:
    duration = int((_parse_utc(close_time, "close_time") - _parse_utc(open_time, "open_time")).total_seconds())
    if duration <= 0:
        raise BtcFamilyQuoteFeasibilityError("market active duration must be positive")
    return duration



def _resolve_stored_path(spec: Mapping[str, Any], repository_root: Path) -> Path:
    kind = spec.get("kind")
    value = spec.get("value")
    if not isinstance(value, str) or not value:
        raise BtcFamilyQuoteFeasibilityError("manifest path value must be non-empty text")
    if kind == "repository_relative":
        candidate = (repository_root / value).resolve()
        try:
            candidate.relative_to(repository_root)
        except ValueError as exc:
            raise BtcFamilyQuoteFeasibilityError(
                f"repository-relative manifest path escapes repository: {value!r}"
            ) from exc
        return candidate
    if kind == "absolute":
        return Path(value).resolve()
    raise BtcFamilyQuoteFeasibilityError(f"unsupported manifest path kind: {kind!r}")

def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BtcFamilyQuoteFeasibilityError(
                    f"inventory raw archive line {line_number} is invalid JSON"
                ) from exc
            if not isinstance(item, dict):
                raise BtcFamilyQuoteFeasibilityError("inventory raw archive contains non-object record")
            output.append(item)
    return output


def _parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise BtcFamilyQuoteFeasibilityError(f"{field} is not ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BtcFamilyQuoteFeasibilityError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str) -> str:
    if value is None or not str(value).strip():
        raise BtcFamilyQuoteFeasibilityError(f"required field {field!r} is missing")
    return str(value).strip()


def _mapping_or_none(value: Any, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise BtcFamilyQuoteFeasibilityError(f"{field} must be object or null")
    return value


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise BtcFamilyQuoteFeasibilityError("boolean is not a decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BtcFamilyQuoteFeasibilityError(f"invalid decimal value {value!r}") from exc
    if not result.is_finite():
        raise BtcFamilyQuoteFeasibilityError("decimal must be finite")
    return result


def _decimal_text(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _float_text(value: float) -> str:
    return f"{value:.6f}"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _validate_exact_rows(rows: Iterable[Mapping[str, str]], fields: Sequence[str], label: str) -> None:
    expected = tuple(fields)
    for row in rows:
        if tuple(row.keys()) != expected:
            raise BtcFamilyQuoteFeasibilityError(
                f"{label} row fields differ from schema: {tuple(row.keys())!r}"
            )

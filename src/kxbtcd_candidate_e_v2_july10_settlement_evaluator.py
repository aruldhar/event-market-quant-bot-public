"""Frozen Candidate-E July-10 settlement collection/scoring helpers.

This module is intentionally narrow:
- it reads the already-frozen P&L evaluation contract and repaired path artifact;
- it identifies only settlement tickers required by EXACT scenarios;
- it resolves Kalshi live-vs-historical storage tier for exact settlement tickers;
- it normalizes finalized binary Kalshi market records;
- it scores EXACT scenarios and keeps CENSORED scenarios interval-valued;
- it never chooses/ranks a policy and never places orders.

Network access lives only in the separate collector CLI.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from . import kxbtcd_candidate_e_v2_july10_pnl_evaluation_contract as pnl_contract

CONTRACT_PATH = Path("configs/kxbtcd_candidate_e_v2_july10_pnl_evaluation_contract.json")
SETTLEMENT_CACHE_DIR = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_exact_settlement_cache"
)
SETTLEMENT_MANIFEST_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_exact_settlements.json"
)
PNL_REPORT_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_v2_pnl_evaluation.json"
)
SOURCE_NAME = "kalshi_partitioned_market_settlement_v1"
KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE = (
    "Checkpoint 21N-Y-D2 - Partition-Aware Settlement Transport"
)
REQUIRED_CLOSEOUT_PATHS = (
    "src/kxbtcd_candidate_e_v2_july10_settlement_evaluator.py",
    "collect_kxbtcd_candidate_e_v2_july10_settlements.py",
    "validate_kxbtcd_candidate_e_v2_july10_settlement_readiness.py",
    "tests/test_kxbtcd_candidate_e_v2_july10_settlement_evaluator.py",
    "docs/PROJECT_STATE.md",
    "docs/AI_HANDOFF.md",
    "docs/DECISIONS.md",
    "docs/EXPERIMENT_LOG.md",
    "docs/BACKLOG.md",
)
_TICKER_RE = re.compile(r"^[A-Z0-9.-]+$")


class SettlementEvaluationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SettlementEvaluationError(message)


def d(value: Any, name: str) -> Decimal:
    return pnl_contract.d(value, name)


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." not in text:
        return text
    out = text.rstrip("0").rstrip(".")
    return out if out else "0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload: Any) -> str:
    raw = canonical_json_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    if path.exists():
        require(path.read_bytes() == raw, f"refusing non-identical overwrite: {path}")
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return digest


def load_frozen_inputs(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    contract_path = repo / CONTRACT_PATH
    require(contract_path.is_file(), f"missing P&L contract: {CONTRACT_PATH}")
    contract = pnl_contract.load_contract(contract_path)

    frozen = contract["frozen_evidence"]
    path_file = repo / frozen["repaired_outcome_blind_path_relative_path"]
    require(path_file.is_file(), "missing frozen repaired outcome-blind path artifact")
    require(
        sha256_file(path_file) == frozen["repaired_outcome_blind_path_sha256"],
        "repaired outcome-blind path SHA mismatch",
    )
    paths = load_json(path_file)
    require(len(paths.get("policy_results", [])) == 60, "expected exactly 60 policy results")
    safety = paths.get("safety", {})
    require(safety.get("outcomes_accessed") is False, "path artifact is not outcome-blind")
    require(safety.get("strategy_pnl_calculated") is False, "path artifact already contains P&L")
    require(int(safety.get("orders_placed", -1)) == 0, "path artifact orders_placed != 0")
    return contract, paths


def classification_map(contract: Mapping[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    out: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in contract["scenario_classification"]:
        key = pnl_contract.scenario_key(row)
        require(key not in out, f"duplicate scenario classification: {key}")
        out[key] = dict(row)
    return out


def fallback_tickers_by_class(
    contract: Mapping[str, Any],
    paths: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    classes = classification_map(contract)
    exact: set[str] = set()
    censored: set[str] = set()
    seen = set()

    for row in paths["policy_results"]:
        key = pnl_contract.scenario_key(row)
        require(key in classes, f"path scenario absent from classification: {key}")
        seen.add(key)
        cls = classes[key]["path_observation_class"]
        for trade in row["policy_result"].get("trades", []):
            status = trade["liquidation"]["status"]
            if cls == "EXACT":
                require(
                    status in {"EXIT_FULL", "EXIT_MISSED_SETTLEMENT_FALLBACK"},
                    f"EXACT scenario contains non-exact liquidation status {status!r}: {key}",
                )
            if status != "EXIT_MISSED_SETTLEMENT_FALLBACK":
                continue
            ticker = str(trade["signal"]["market_ticker"])
            require(_TICKER_RE.fullmatch(ticker) is not None, f"invalid ticker syntax: {ticker}")
            if cls == "EXACT":
                exact.add(ticker)
            elif cls == "CENSORED":
                censored.add(ticker)
            else:
                raise SettlementEvaluationError(f"unknown path observation class {cls!r}")

    require(seen == set(classes), "path/classification scenario grids differ")
    return {
        "exact_required": tuple(sorted(exact)),
        "censored_fallback": tuple(sorted(censored)),
        "overlap": tuple(sorted(exact & censored)),
    }


LIVE_MARKETS_PATH = "/markets"
HISTORICAL_MARKETS_PATH = "/historical/markets"


def market_filter_params(ticker: str) -> dict[str, str]:
    require(_TICKER_RE.fullmatch(ticker) is not None, f"invalid ticker syntax: {ticker}")
    return {"tickers": ticker}


def market_source_endpoint(path: str, ticker: str) -> str:
    require(path in {LIVE_MARKETS_PATH, HISTORICAL_MARKETS_PATH}, "invalid market source path")
    params = market_filter_params(ticker)
    return f"{path}?tickers={params['tickers']}"


def exact_filtered_market(
    *,
    expected_ticker: str,
    payload: Mapping[str, Any],
    allow_zero: bool,
) -> Mapping[str, Any] | None:
    markets = payload.get("markets")
    require(isinstance(markets, list), "market response must contain markets array")
    if len(markets) == 0:
        require(allow_zero, "selected market storage tier returned zero exact matches")
        return None
    require(len(markets) == 1, f"exact ticker filter returned {len(markets)} markets")
    market = markets[0]
    require(isinstance(market, Mapping), "markets[0] must be an object")
    require(
        str(market.get("ticker", "")) == expected_ticker,
        "exact ticker filter returned the wrong market",
    )
    return market


def normalize_market_list_response(
    *,
    expected_ticker: str,
    payload: Mapping[str, Any],
    source_tier: str,
    source_path: str,
    raw_reference: Mapping[str, str],
    request_started_at_utc: str,
    received_at_utc: str,
) -> dict[str, Any]:
    require(source_tier in {"live_recent", "historical"}, "invalid source tier")
    expected_path = LIVE_MARKETS_PATH if source_tier == "live_recent" else HISTORICAL_MARKETS_PATH
    require(source_path == expected_path, "source tier/path mismatch")
    require(set(raw_reference) == {"source", "session_id", "request_id"}, "invalid raw reference")
    market = exact_filtered_market(
        expected_ticker=expected_ticker,
        payload=payload,
        allow_zero=False,
    )
    assert market is not None
    yes_value = pnl_contract.validate_binary_settlement(
        market_ticker=expected_ticker,
        settlement=market,
    )
    normalized_market = {
        "ticker": str(market["ticker"]),
        "event_ticker": str(market.get("event_ticker", "")),
        "market_type": str(market["market_type"]),
        "status": str(market["status"]),
        "result": str(market["result"]).lower(),
        "settlement_value_dollars": decimal_text(yes_value),
        "settlement_ts": str(market["settlement_ts"]),
        "is_provisional": market.get("is_provisional"),
    }
    return {
        "schema_version": "candidate_e_v2_exact_settlement_record.v1",
        "source_id": SOURCE_NAME,
        "source_tier": source_tier,
        "source_endpoint": market_source_endpoint(source_path, expected_ticker),
        "market": normalized_market,
        "raw_reference": dict(raw_reference),
        "request_started_at_utc": request_started_at_utc,
        "received_at_utc": received_at_utc,
    }


def validate_cached_settlement_record(record: Mapping[str, Any], ticker: str) -> dict[str, Any]:
    require(
        record.get("schema_version") == "candidate_e_v2_exact_settlement_record.v1",
        f"unexpected cached settlement schema for {ticker}",
    )
    require(record.get("source_id") == SOURCE_NAME, f"wrong settlement source for {ticker}")
    require(record.get("source_tier") in {"live_recent", "historical"}, f"wrong source tier for {ticker}")
    market = record.get("market")
    require(isinstance(market, Mapping), f"cached settlement missing market for {ticker}")
    pnl_contract.validate_binary_settlement(market_ticker=ticker, settlement=market)
    raw_reference = record.get("raw_reference")
    require(isinstance(raw_reference, Mapping), f"cached settlement missing raw reference for {ticker}")
    require(
        set(raw_reference) == {"source", "session_id", "request_id"},
        f"cached settlement raw reference malformed for {ticker}",
    )
    return dict(record)


def settlement_cache_path(repo: Path, ticker: str) -> Path:
    require(_TICKER_RE.fullmatch(ticker) is not None, f"invalid ticker syntax: {ticker}")
    return repo / SETTLEMENT_CACHE_DIR / f"{ticker}.json"


def load_cached_required_settlements(
    repo: Path,
    required_tickers: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ticker in required_tickers:
        path = settlement_cache_path(repo, ticker)
        if not path.exists():
            continue
        record = validate_cached_settlement_record(load_json(path), ticker)
        out[ticker] = record
    return out


def build_settlement_manifest(
    *,
    required_tickers: tuple[str, ...],
    censored_fallback_tickers: tuple[str, ...],
    cached_records: Mapping[str, Mapping[str, Any]],
    raw_files: list[dict[str, str]],
) -> dict[str, Any]:
    require(set(cached_records) == set(required_tickers), "settlement cache is incomplete or excessive")
    rows = []
    for ticker in required_tickers:
        record = cached_records[ticker]
        rows.append(
            {
                "ticker": ticker,
                "cache_relative_path": str(SETTLEMENT_CACHE_DIR / f"{ticker}.json").replace("\\", "/"),
                "cache_sha256": hashlib.sha256(canonical_json_bytes(record)).hexdigest(),
                "source_tier": record["source_tier"],
                "source_endpoint": record["source_endpoint"],
                "market": record["market"],
                "raw_reference": record["raw_reference"],
            }
        )
    return {
        "schema_version": "candidate_e_v2_exact_settlement_manifest.v1",
        "source_id": SOURCE_NAME,
        "required_exact_settlement_tickers": list(required_tickers),
        "censored_fallback_tickers_not_requested_unless_overlapping": list(censored_fallback_tickers),
        "exact_censored_ticker_overlap": sorted(set(required_tickers) & set(censored_fallback_tickers)),
        "settlements": rows,
        "raw_files_written_this_run": raw_files,
        "safety": {
            "strategy_rerun": False,
            "orders_placed": 0,
            "censored_scenarios_receive_point_pnl": False,
        },
    }


def _settlement_market_map(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {ticker: record["market"] for ticker, record in records.items()}


def build_pnl_report(
    *,
    contract: Mapping[str, Any],
    paths: Mapping[str, Any],
    settlement_records: Mapping[str, Mapping[str, Any]],
    settlement_manifest_sha256: str,
) -> dict[str, Any]:
    classes = classification_map(contract)
    fallback = fallback_tickers_by_class(contract, paths)
    required = fallback["exact_required"]
    require(set(settlement_records) == set(required), "exact settlement set does not match frozen need")
    settlement_map = _settlement_market_map(settlement_records)

    scenarios = []
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    exact_count = 0
    censored_count = 0

    for row in paths["policy_results"]:
        key = pnl_contract.scenario_key(row)
        cls_row = classes[key]
        cls = cls_row["path_observation_class"]
        policy = row["policy_result"]

        if cls == "EXACT":
            exact_count += 1
            point = pnl_contract.exact_policy_pnl(policy, settlement_map)
            lo, hi = pnl_contract.event_interval(
                path_observation_class="EXACT",
                exact_pnl=point,
                contract=contract,
            )
            point_text: str | None = decimal_text(point)
        elif cls == "CENSORED":
            censored_count += 1
            lo, hi = pnl_contract.event_interval(
                path_observation_class="CENSORED",
                exact_pnl=None,
                contract=contract,
            )
            point_text = None
        else:
            raise SettlementEvaluationError(f"unknown path observation class {cls!r}")

        scenario = {
            "event_ticker": key[0],
            "threshold_dollars": key[1],
            "latency_ms": key[2],
            "path_observation_class": cls,
            "selection_or_rearm_censored": bool(cls_row["selection_or_rearm_censored"]),
            "explicit_liquidation_censored": bool(cls_row["explicit_liquidation_censored"]),
            "filled_trade_count": len(policy.get("trades", [])),
            "point_pnl_dollars": point_text,
            "pnl_interval_dollars": [decimal_text(lo), decimal_text(hi)],
        }
        scenarios.append(scenario)
        groups[(key[1], key[2])].append(scenario)

    require(exact_count == 27 and censored_count == 33, "frozen exact/censored counts changed")
    require(len(groups) == 15, "expected 15 threshold/latency policy settings")

    settings = []
    robustness = Counter()
    for (threshold, latency), rows in sorted(
        groups.items(), key=lambda item: (Decimal(item[0][0]), item[0][1])
    ):
        rows = sorted(rows, key=lambda x: x["event_ticker"])
        require(len(rows) == 4, "each policy setting must contain exactly four events")
        intervals = [
            (d(r["pnl_interval_dollars"][0], "lower"), d(r["pnl_interval_dollars"][1], "upper"))
            for r in rows
        ]
        agg = pnl_contract.aggregate_four_event_intervals(intervals)
        cls = agg["classification"]
        robustness[cls] += 1
        settings.append(
            {
                "threshold_dollars": threshold,
                "latency_ms": latency,
                "exact_coverage_n_of_4": sum(r["path_observation_class"] == "EXACT" for r in rows),
                "events": rows,
                "four_event_pnl_sum_interval_dollars": [
                    decimal_text(agg["sum_interval"][0]),
                    decimal_text(agg["sum_interval"][1]),
                ],
                "four_event_event_equal_mean_pnl_interval_dollars": [
                    decimal_text(agg["event_equal_mean_interval"][0]),
                    decimal_text(agg["event_equal_mean_interval"][1]),
                ],
                "robustness_classification": cls,
            }
        )

    return {
        "schema_version": "candidate_e_v2_july10_pnl_evaluation.v1",
        "checkpoint_id": "21N-Y-E-OUTCOME-EVALUATION",
        "strategy_id": paths["strategy_id"],
        "frozen_repaired_path_sha256": contract["frozen_evidence"][
            "repaired_outcome_blind_path_sha256"
        ],
        "frozen_censorship_refinement_sha256": contract["frozen_evidence"][
            "competitive_censorship_refinement_sha256"
        ],
        "settlement_manifest_sha256": settlement_manifest_sha256,
        "scenario_count": 60,
        "exact_scenario_count": exact_count,
        "censored_scenario_count": censored_count,
        "required_exact_settlement_tickers": list(required),
        "scenario_results": sorted(
            scenarios,
            key=lambda x: (Decimal(x["threshold_dollars"]), x["latency_ms"], x["event_ticker"]),
        ),
        "policy_settings": settings,
        "robustness_classification_counts": dict(sorted(robustness.items())),
        "interpretation": {
            "july10_role": "development_mechanics_evidence_only",
            "advancement_gate": False,
            "policy_ranking_or_selection_performed": False,
            "censored_scenarios_receive_point_pnl": False,
            "all_four_events_retained_per_policy_setting": True,
        },
        "safety": {
            "strategy_rerun": False,
            "orders_placed": 0,
            "production_execution_authorized": False,
        },
    }


def _git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return cp.stdout.strip()


def require_collection_closeout_gate(repo: Path) -> dict[str, Any]:
    require(_git(repo, "branch", "--show-current") == "main", "collection requires branch main")
    require(_git(repo, "status", "--porcelain") == "", "collection requires a clean worktree")
    head = _git(repo, "rev-parse", "HEAD")
    origin = _git(repo, "rev-parse", "origin/main")
    require(head == origin, "collection requires HEAD == origin/main")

    receipt_path = repo / "docs/LAST_CHECKPOINT_CLOSEOUT.json"
    require(receipt_path.is_file(), "missing LAST_CHECKPOINT_CLOSEOUT.json")
    receipt = load_json(receipt_path)
    require(
        receipt.get("checkpoint_message") == EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE,
        "settlement implementation has not been safely closed/pushed",
    )
    committed = set(receipt.get("committed_paths", []))
    missing = set(REQUIRED_CLOSEOUT_PATHS) - committed
    require(not missing, f"closeout receipt missing required paths: {sorted(missing)}")
    checkpoint_commit = str(receipt.get("checkpoint_commit", ""))
    require(checkpoint_commit, "closeout receipt missing checkpoint_commit")

    for rel in REQUIRED_CLOSEOUT_PATHS[:4]:
        cp = subprocess.run(
            ["git", "diff", "--quiet", checkpoint_commit, "--", rel],
            cwd=repo,
        )
        require(cp.returncode == 0, f"local {rel} differs from closed implementation commit")
    return receipt

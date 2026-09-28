#!/usr/bin/env python3
"""Open and evaluate the frozen KXBTC15M H3 holdout exactly once.

The command is public and read-only.  It byte-hashes its inputs, then creates
an immutable pre-outcome freeze receipt before extracting or interpreting any
holdout archive or requesting a finalized label.  It validates the exact
26-market sample and evaluates only the frozen causal-native H3 policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import validate_fee_inputs, write_csv
from analyze_kxbtc15m_h3_frequency import (
    _raw_snapshot_sets,
    simulate_market as simulate_frequency_market,
)
from analyze_kxbtc15m_h3_native_exit_policies import (
    BASELINE_POLICY,
    find_native_entry,
    simulate_policy,
    verify_baseline_reproduction,
)
from analyze_kxbtc15m_h3_time_windows import _bootstrap, _mean, _quantile
from audit_kxbtc15m_raw_depth import (
    AuditError,
    DevelopmentMarket,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
)
from src.config import (
    DEFAULT_MANIFEST_ROOT,
    DEFAULT_RAW_LOG_ROOT,
    DEFAULT_RUNTIME_EVENT_ROOT,
    KALSHI_PUBLIC_BASE_URL,
)
from src.public_census_http import PublicCensusHttpClient
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


EXPERIMENT_ID = "kxbtc15m_h3_native_4_5m_protected50_holdout.v1"
COLLECTOR_NAME = "evaluate_kxbtc15m_h3_holdout"
HOLDOUT_FIRST_TICKER = "KXBTC15M-26AUG121445-45"
HOLDOUT_LAST_TICKER = "KXBTC15M-26AUG122100-00"
EXPECTED_HOLDOUT_MARKETS = 26
MINIMUM_FILLED_MARKETS = 10
FULL_LOSS_FRACTION = Decimal("0.90")
FREEZE_FILENAME = "KXBTC15M_H3_HOLDOUT_PREOUTCOME_FREEZE.json"
REPORT_FILENAME = "KXBTC15M_H3_HOLDOUT.md"
OUTCOME_FILENAME = "kxbtc15m_h3_holdout_outcomes.csv"
SCENARIO_FILENAME = "kxbtc15m_h3_holdout_scenarios.csv"
SUMMARY_FILENAME = "kxbtc15m_h3_holdout_summary.csv"

DESIGN: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "sample": {
        "partition": "holdout",
        "market_count": EXPECTED_HOLDOUT_MARKETS,
        "first_ticker": HOLDOUT_FIRST_TICKER,
        "last_ticker": HOLDOUT_LAST_TICKER,
        "quality_rule": "frozen KXBTC15M primary raw-depth eligibility gate",
    },
    "entry": {
        "monitoring": "every causal archived HTTP response receipt",
        "window": "240 < seconds_remaining <= 300",
        "favored_midpoint_band": "0.90 <= midpoint < 0.98",
        "selection": "first qualifying observation",
        "latency_seconds": 1,
        "delayed_state_recheck": False,
        "execution": "full archived depth",
        "maximum_budget_usd_including_fees": 100,
    },
    "exit": {
        "profit_target": "50% of maximum settlement profit",
        "target_protected_after_latency": True,
        "latency_seconds": 1,
        "execution": "full archived depth",
        "preclose_cash_fallback_seconds": 10,
        "settlement_only_after_preclose_liquidity_failure": True,
    },
    "position_policy": {
        "cycles_per_market": 1,
        "reentry": False,
        "runner": False,
        "compounding": False,
    },
    "primary_metric": "mean P&L per eligible holdout market; no-trades are $0",
    "confidence_interval": {
        "method": "market bootstrap",
        "draws": 2000,
        "seed": 20260813,
        "bounds": "ordered draws 49 and 1949",
    },
    "support_gate": {
        "minimum_filled_markets": MINIMUM_FILLED_MARKETS,
        "mean_pnl_per_eligible_market_strictly_positive": True,
        "bootstrap_95pct_lower_bound_strictly_positive": True,
        "full_capital_losses": 0,
        "full_capital_loss_definition": "P&L <= -90% of entry cash outflow",
    },
    "development_reference_only": {
        "eligible_markets": 96,
        "filled_markets": 57,
        "mean_pnl_per_market": 2.32,
        "bootstrap_95pct_ci": [1.87, 2.77],
        "worst_filled_pnl": 1.10,
    },
    "permissions": {
        "public_http_only": True,
        "authentication": False,
        "orders": False,
        "external_btc_data": False,
    },
}


class H3HoldoutError(RuntimeError):
    """Raised when the sealed evaluation cannot be completed exactly."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def design_fingerprint() -> str:
    return hashlib.sha256(_canonical_json(DESIGN).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _required(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if result is None or str(result) == "":
        raise H3HoldoutError(f"required field {field!r} is missing")
    return str(result)


def select_holdout_manifests(root: Path) -> list[dict[str, Any]]:
    """Select the exact chronological 26-market frozen holdout partition."""

    manifests: list[dict[str, Any]] = []
    for path in root.rglob("record_orderbook_*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        ticker = document.get("arguments", {}).get("ticker")
        if ticker and document.get("status") == "completed":
            manifests.append(document)
    manifests.sort(key=lambda item: parse_time(_required(item, "started_at_utc")))

    selected: list[dict[str, Any]] = []
    active = False
    for manifest in manifests:
        ticker = _required(manifest.get("arguments", {}), "ticker")
        if ticker == HOLDOUT_FIRST_TICKER:
            active = True
        if active:
            selected.append(manifest)
        if ticker == HOLDOUT_LAST_TICKER:
            break

    if len(selected) != EXPECTED_HOLDOUT_MARKETS:
        raise H3HoldoutError(
            f"expected {EXPECTED_HOLDOUT_MARKETS} frozen holdout manifests; "
            f"found {len(selected)}"
        )
    tickers = [_required(item["arguments"], "ticker") for item in selected]
    if tickers[0] != HOLDOUT_FIRST_TICKER or tickers[-1] != HOLDOUT_LAST_TICKER:
        raise H3HoldoutError("holdout boundary ticker changed")
    if len(set(tickers)) != len(tickers):
        raise H3HoldoutError("holdout partition contains a duplicate ticker")
    return selected


def _matching_completed_manifest(manifest_root: Path) -> Path | None:
    for path in manifest_root.rglob("*.json") if manifest_root.exists() else ():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            document.get("collector", {}).get("name") == COLLECTOR_NAME
            and document.get("status") == "completed"
            and document.get("arguments", {}).get("experiment_id") == EXPERIMENT_ID
            and document.get("arguments", {}).get("design_fingerprint")
            == design_fingerprint()
        ):
            return path
    return None


def _code_hashes(repo_root: Path) -> dict[str, str]:
    names = (
        "evaluate_kxbtc15m_h3_holdout.py",
        "analyze_kxbtc15m_h3_native_exit_policies.py",
        "analyze_kxbtc15m_h3_frequency.py",
        "analyze_kxbtc15m_h3_target_protection.py",
        "analyze_kxbtc15m_h3_exit_policies.py",
        "analyze_kxbtc15m_bounded_simulation.py",
        "audit_kxbtc15m_raw_depth.py",
    )
    output: dict[str, str] = {}
    for name in names:
        path = (repo_root / name).resolve()
        if not path.is_file():
            raise H3HoldoutError(f"frozen implementation file is missing: {path}")
        output[name] = _sha256(path)
    return output


def create_or_verify_freeze_receipt(
    path: Path, *, repo_root: Path, audit_zip: Path, series_csv: Path,
    fee_changes_csv: Path,
) -> dict[str, Any]:
    current_hashes = _code_hashes(repo_root)
    current_inputs = {
        "audit_zip": _sha256(audit_zip),
        "series_csv": _sha256(series_csv),
        "fee_changes_csv": _sha256(fee_changes_csv),
    }
    if path.exists():
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt.get("design_fingerprint") != design_fingerprint():
            raise H3HoldoutError("existing freeze receipt has a different design")
        if receipt.get("implementation_sha256") != current_hashes:
            raise H3HoldoutError(
                "implementation changed after the pre-outcome freeze; restore the exact files"
            )
        if receipt.get("input_sha256") != current_inputs:
            raise H3HoldoutError(
                "an input changed after the pre-outcome freeze; restore the exact inputs"
            )
        return receipt

    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": "kxbtc15m_h3_holdout_preoutcome_freeze.v1",
        "created_at_utc": _utc_now(),
        "status": "frozen_before_holdout_archive_or_outcome_read",
        "experiment_id": EXPERIMENT_ID,
        "design_fingerprint": design_fingerprint(),
        "design": DESIGN,
        "implementation_sha256": current_hashes,
        "input_sha256": current_inputs,
        "holdout_outcomes_materialized": False,
        "authentication_used": False,
        "orders_placed": 0,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return receipt


def collect_outcomes(
    client: PublicCensusHttpClient,
    markets: Sequence[DevelopmentMarket],
    *,
    run_id: str,
    freeze_sha256: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, market_item in enumerate(markets, start=1):
        ticker = market_item.ticker
        response = client.get_json(f"/markets/{ticker}")
        payload = response.payload.get("market")
        if not isinstance(payload, Mapping):
            raise H3HoldoutError(f"{ticker}: outcome response is missing market object")
        if _required(payload, "ticker") != ticker:
            raise H3HoldoutError(f"{ticker}: outcome response ticker mismatch")
        status = _required(payload, "status").lower()
        result = _required(payload, "result").lower()
        if status != "finalized" or result not in {"yes", "no"}:
            raise H3HoldoutError(
                f"{ticker}: expected finalized yes/no; got status={status!r}, result={result!r}"
            )
        rows.append({
            "schema_version": "kxbtc15m_h3_holdout_outcome.v1",
            "experiment_id": EXPERIMENT_ID,
            "design_fingerprint": design_fingerprint(),
            "freeze_receipt_sha256": freeze_sha256,
            "run_id": run_id,
            "market_index": market_item.index,
            "ticker": ticker,
            "raw_source": response.raw_record.source,
            "raw_session_id": response.raw_record.session_id,
            "raw_request_id": response.raw_record.request_id,
            "received_at_utc": response.received_at_utc,
            "status": status,
            "result": result,
            "winning_side": result.upper(),
        })
        print(f"[outcome {number:02d}/{len(markets)}] {ticker}")
    if len(rows) != EXPECTED_HOLDOUT_MARKETS:
        raise H3HoldoutError("holdout outcome count changed")
    if {row["ticker"] for row in rows} != {market.ticker for market in markets}:
        raise H3HoldoutError("holdout outcome ticker set changed")
    return rows


def summarize_holdout(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(rows) != EXPECTED_HOLDOUT_MARKETS:
        raise H3HoldoutError(
            f"expected {EXPECTED_HOLDOUT_MARKETS} scenario rows; found {len(rows)}"
        )
    completed = [row for row in rows if row["status"] == "completed"]
    pnl_market = [float(row["pnl"] or 0.0) for row in rows]
    pnl_filled = [float(row["pnl"]) for row in completed]
    mean_market, ci_low, ci_high = _bootstrap(pnl_market)
    full_losses = sum(bool(row["full_capital_loss"]) for row in completed)
    gates = {
        "minimum_filled_markets_pass": len(completed) >= MINIMUM_FILLED_MARKETS,
        "positive_mean_pass": mean_market > 0,
        "positive_ci_lower_pass": ci_low > 0,
        "zero_full_losses_pass": full_losses == 0,
    }
    gate_pass = all(gates.values())
    if gate_pass:
        decision = "supported"
    elif mean_market > 0 and full_losses == 0:
        decision = "inconclusive"
    else:
        decision = "not_supported"
    return {
        "schema_version": "kxbtc15m_h3_holdout_summary.v1",
        "experiment_id": EXPERIMENT_ID,
        "design_fingerprint": design_fingerprint(),
        "eligible_markets": len(rows),
        "triggered_markets": sum(bool(row["triggered"]) for row in rows),
        "entry_filled_markets": len(completed),
        "total_pnl": sum(pnl_market),
        "mean_pnl_per_eligible_market": mean_market,
        "bootstrap_ci_low_per_eligible_market": ci_low,
        "bootstrap_ci_high_per_eligible_market": ci_high,
        "mean_pnl_per_filled_entry": _mean(pnl_filled) if completed else None,
        "profitable_rate_per_filled_entry": _mean(
            [bool(row["profitable"]) for row in completed]
        ) if completed else None,
        "protected_target_fill_rate": _mean(
            [bool(row["target_filled"]) for row in completed]
        ) if completed else None,
        "fallback_rate": _mean(
            [bool(row["fallback_used"]) for row in completed]
        ) if completed else None,
        "settlement_exit_rate": _mean(
            ["settlement" in str(row["exit_reason"]) for row in completed]
        ) if completed else None,
        "favored_side_won_rate": _mean(
            [bool(row["favored_side_won"]) for row in completed]
        ) if completed else None,
        "full_capital_losses": full_losses,
        "pnl_05_quantile_per_filled_entry": (
            _quantile(pnl_filled, 0.05) if completed else None
        ),
        "worst_pnl_per_filled_entry": min(pnl_filled) if completed else None,
        **gates,
        "holdout_support_gate_pass": gate_pass,
        "holdout_decision": decision,
        "holdout_read": True,
        "external_btc_data_used": False,
        "authentication_used": False,
        "orders_placed": 0,
    }


def _money(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    number = float(value)
    return "n/a" if math.isnan(number) else f"${number:.2f}"


def _percent(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    number = float(value)
    return "n/a" if math.isnan(number) else f"{number:.1%}"


def markdown_report(summary: Mapping[str, Any], freeze_sha256: str) -> str:
    supported = bool(summary["holdout_support_gate_pass"])
    conclusion = (
        "The frozen H3 policy receives sealed-holdout support under the preregistered gate."
        if supported else
        "The frozen H3 policy does not pass every preregistered sealed-holdout gate."
    )
    return "\n".join([
        "# KXBTC15M H3 sealed-holdout evaluation",
        "",
        "**One-shot confirmatory test; frozen 26-market holdout opened.**",
        "",
        f"Experiment: `{EXPERIMENT_ID}`.  Design fingerprint: `{design_fingerprint()}`.  "
        f"Pre-outcome freeze receipt SHA-256: `{freeze_sha256}`.",
        "",
        "The tested rule is the first causal-native favored midpoint from 90% to below 98% "
        "during 4-to-5 minutes remaining, a one-second unprotected full-depth entry with a "
        "$100 cap and fees, a protected 50%-of-maximum-profit exit, and the frozen ten-second "
        "preclose fallback. No early entry, runner, re-entry, compounding, external BTC feed, "
        "authentication, or order placement is allowed.",
        "",
        "| Eligible | Filled | Total P&L | Mean / market | 95% bootstrap CI | Mean / fill | Profitable | Target fill | Fallback | Settlement | Full losses | 5% tail | Worst |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {summary['eligible_markets']} | {summary['entry_filled_markets']} | "
        f"{_money(summary['total_pnl'])} | {_money(summary['mean_pnl_per_eligible_market'])} | "
        f"{_money(summary['bootstrap_ci_low_per_eligible_market'])} to "
        f"{_money(summary['bootstrap_ci_high_per_eligible_market'])} | "
        f"{_money(summary['mean_pnl_per_filled_entry'])} | "
        f"{_percent(summary['profitable_rate_per_filled_entry'])} | "
        f"{_percent(summary['protected_target_fill_rate'])} | "
        f"{_percent(summary['fallback_rate'])} | {_percent(summary['settlement_exit_rate'])} | "
        f"{summary['full_capital_losses']} | "
        f"{_money(summary['pnl_05_quantile_per_filled_entry'])} | "
        f"{_money(summary['worst_pnl_per_filled_entry'])} |",
        "",
        "## Preregistered support gate",
        "",
        "| Gate | Required | Observed | Pass |",
        "|---|---:|---:|---:|",
        f"| Filled markets | at least {MINIMUM_FILLED_MARKETS} | "
        f"{summary['entry_filled_markets']} | {summary['minimum_filled_markets_pass']} |",
        f"| Mean P&L / eligible market | above $0 | "
        f"{_money(summary['mean_pnl_per_eligible_market'])} | {summary['positive_mean_pass']} |",
        f"| 95% bootstrap lower bound | above $0 | "
        f"{_money(summary['bootstrap_ci_low_per_eligible_market'])} | "
        f"{summary['positive_ci_lower_pass']} |",
        f"| Full-capital losses | 0 | {summary['full_capital_losses']} | "
        f"{summary['zero_full_losses_pass']} |",
        "",
        f"**Decision: {str(summary['holdout_decision']).upper()}.** {conclusion}",
        "",
        "The holdout is now permanently opened and must not be reused to tune H3. A pass is "
        "evidence of generalization, not a profitability guarantee or authorization for paper, "
        "demo, or live execution. A failure or inconclusive result must not be repaired by testing "
        "variants on these same 26 markets.",
    ]) + "\n"


def _validate_output_is_fresh(output_dir: Path, manifest_root: Path) -> None:
    completed = _matching_completed_manifest(manifest_root)
    if completed is not None:
        raise H3HoldoutError(
            f"matching completed holdout evaluation already exists: {completed}"
        )
    materialized = [
        output_dir / name
        for name in (REPORT_FILENAME, OUTCOME_FILENAME, SCENARIO_FILENAME, SUMMARY_FILENAME)
        if (output_dir / name).exists()
    ]
    if materialized:
        raise H3HoldoutError(
            "holdout evaluation output already exists; refusing a second evaluation: "
            + ", ".join(str(path) for path in materialized)
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--series-csv", type=Path, required=True)
    parser.add_argument("--fee-changes-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/kxbtc15m_h3_holdout"),
    )
    parser.add_argument("--manifest-root", type=Path, default=DEFAULT_MANIFEST_ROOT)
    parser.add_argument("--raw-log-root", type=Path, default=DEFAULT_RAW_LOG_ROOT)
    parser.add_argument(
        "--runtime-event-root", type=Path, default=DEFAULT_RUNTIME_EVENT_ROOT
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    validate_fee_inputs(args.series_csv, args.fee_changes_csv)
    _validate_output_is_fresh(args.output_dir, args.manifest_root)
    freeze_path = args.output_dir / FREEZE_FILENAME
    receipt = create_or_verify_freeze_receipt(
        freeze_path,
        repo_root=repo_root,
        audit_zip=args.audit_zip,
        series_csv=args.series_csv,
        fee_changes_csv=args.fee_changes_csv,
    )
    freeze_sha256 = _sha256(freeze_path)

    client = PublicCensusHttpClient(
        base_url=KALSHI_PUBLIC_BASE_URL,
        source_name="kalshi_public_rest",
        raw_root=args.raw_log_root,
        timeout_seconds=30.0,
    )
    manifest = CollectionRunManifest(
        collector_name=COLLECTOR_NAME,
        arguments={
            "experiment_id": EXPERIMENT_ID,
            "design_fingerprint": design_fingerprint(),
            "freeze_receipt_sha256": freeze_sha256,
            "partition": "holdout",
            "planned_market_requests": EXPECTED_HOLDOUT_MARKETS,
            "model_or_metric_change_after_freeze": False,
            "authentication_used": False,
            "execution_enabled": False,
        },
        manifest_root=args.manifest_root,
        repository_root=repo_root,
        source_sessions=[{
            "source": client.raw_recorder.source_name,
            "session_id": client.raw_recorder.session_id,
        }],
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        args.runtime_event_root,
        run_id=manifest.run_id,
        collector_name=COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(runtime)
    derived_paths: list[Path] = []
    scenario_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    try:
        runtime.emit(
            "collector.started",
            severity="info",
            message="Frozen KXBTC15M H3 holdout evaluation started",
            context={
                "design_fingerprint": design_fingerprint(),
                "holdout_market_requests": EXPECTED_HOLDOUT_MARKETS,
                "model_or_metric_change_after_freeze": False,
                "orders_placed": 0,
            },
        )
        with TemporaryDirectory(prefix="kxbtc15m_h3_holdout_") as temporary:
            audit_root = Path(temporary)
            safe_extract_zip(args.audit_zip, audit_root)
            selected = select_holdout_manifests(audit_root)
            markets = [
                assess_market(index, item, audit_root)
                for index, item in enumerate(selected, start=101)
            ]
            ineligible = [market for market in markets if not market.eligible]
            if ineligible:
                detail = "; ".join(
                    f"{market.ticker}={','.join(market.exclusion_reasons)}"
                    for market in ineligible
                )
                raise H3HoldoutError(f"holdout primary quality gate failed: {detail}")

            outcome_rows = collect_outcomes(
                client,
                markets,
                run_id=manifest.run_id,
                freeze_sha256=freeze_sha256,
            )
            outcome_by_ticker = {
                str(row["ticker"]): str(row["winning_side"]) for row in outcome_rows
            }
            for number, market_item in enumerate(markets, start=1):
                _legacy, snapshots = _raw_snapshot_sets(market_item, repo_root)
                close = market_close_utc(market_item.ticker)
                entry_context = find_native_entry(snapshots, close)
                row = simulate_policy(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcome_by_ticker[market_item.ticker],
                    ticker=market_item.ticker,
                    segment="holdout_26",
                    policy=BASELINE_POLICY,
                    kind="fraction",
                    value=Decimal("0.50"),
                    entry_context=entry_context,
                )
                frequency = simulate_frequency_market(
                    snapshots=snapshots,
                    close_time=close,
                    winning_side=outcome_by_ticker[market_item.ticker],
                    ticker=market_item.ticker,
                    frequency="native",
                    entry_mode="unprotected",
                    clock_basis="causal_response_receipt",
                    diagnostic_segment="holdout_26",
                )
                verify_baseline_reproduction(row, frequency)
                row.update({
                    "experiment_id": EXPERIMENT_ID,
                    "design_fingerprint": design_fingerprint(),
                    "freeze_receipt_sha256": freeze_sha256,
                    "market_index": market_item.index,
                    "partition": "holdout",
                    "holdout_read": True,
                    "outcomes_materialized": True,
                    "authentication_used": False,
                    "orders_placed": 0,
                })
                scenario_rows.append(row)
                print(f"[evaluate {number:02d}/{len(markets)}] {market_item.ticker}")

        summary = summarize_holdout(scenario_rows)
        outcome_path = args.output_dir / OUTCOME_FILENAME
        scenario_path = args.output_dir / SCENARIO_FILENAME
        summary_path = args.output_dir / SUMMARY_FILENAME
        report_path = args.output_dir / REPORT_FILENAME
        derived_paths = [outcome_path, scenario_path, summary_path]
        write_csv(outcome_path, outcome_rows)
        write_csv(scenario_path, scenario_rows)
        write_csv(summary_path, [summary])
        report_path.write_text(markdown_report(summary, freeze_sha256), encoding="utf-8")
        runtime.emit(
            "collector.completed",
            severity="info",
            message="Frozen KXBTC15M H3 holdout evaluation completed",
            context={
                "holdout_markets": EXPECTED_HOLDOUT_MARKETS,
                "filled_markets": summary["entry_filled_markets"],
                "holdout_decision": summary["holdout_decision"],
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            derived_csv_files=derived_paths,
            runtime_event_files=runtime.written_paths,
            result=summary,
        )
    except BaseException as exc:
        try:
            runtime.emit(
                "collector.failed",
                severity="critical",
                message="Frozen KXBTC15M H3 holdout evaluation failed",
                context={
                    "outcomes_collected": len(outcome_rows),
                    "scenarios_evaluated": len(scenario_rows),
                    "orders_placed": 0,
                },
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        except RuntimeEventWriteError:
            pass
        try:
            manifest.fail(
                exc,
                raw_files=client.raw_recorder.written_paths,
                derived_csv_files=[path for path in derived_paths if path.exists()],
                runtime_event_files=runtime.written_paths,
                result={
                    "outcomes_collected": len(outcome_rows),
                    "scenarios_evaluated": len(scenario_rows),
                    "orders_placed": 0,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from exc
        raise

    assert summary is not None
    print("KXBTC15M H3 sealed-holdout evaluation: COMPLETE")
    print(f"Experiment: {EXPERIMENT_ID}")
    print(f"Design fingerprint: {design_fingerprint()}")
    print(f"Eligible holdout markets: {summary['eligible_markets']}")
    print(f"Filled markets: {summary['entry_filled_markets']}")
    print(f"Mean P&L / eligible market: ${summary['mean_pnl_per_eligible_market']:.4f}")
    print(
        "Bootstrap 95% CI: "
        f"${summary['bootstrap_ci_low_per_eligible_market']:.4f} to "
        f"${summary['bootstrap_ci_high_per_eligible_market']:.4f}"
    )
    print(f"Full-capital losses: {summary['full_capital_losses']}")
    print(f"Holdout decision: {str(summary['holdout_decision']).upper()}")
    print("Holdout outcomes materialized: yes")
    print("Authentication used: no")
    print("Orders placed: 0")
    print(f"Report: {args.output_dir / REPORT_FILENAME}")
    print(f"Manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    main()

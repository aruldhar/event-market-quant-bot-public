"""Validate the frozen July-10 settlement-sensitivity predeclaration.

This module has no network client and no order-placement path.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PREDECLARATION_PATH = Path(
    "configs/kxbtcd_candidate_e_v2_july10_settlement_sensitivity_predeclaration.json"
)
OBSERVED_MANIFEST_PATH = Path(
    "configs/kxbtcd_candidate_e_v2_july10_observed_entry_manifest.json"
)
OFFICIAL_SETTLEMENT_MANIFEST_PATH = Path(
    "data/analysis/predexon_credit_efficiency/july10_candidate_e_v2_exact_settlements.json"
)
OFFICIAL_PNL_REPORT_PATH = Path(
    "data/analysis/predexon_credit_efficiency/july10_candidate_e_v2_pnl_evaluation.json"
)

class SensitivityPredeclarationError(RuntimeError):
    pass

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SensitivityPredeclarationError(message)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def canonical_json_sha(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def d(value: Any, name: str) -> Decimal:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SensitivityPredeclarationError(f"{name} must be decimal-compatible") from exc
    require(out.is_finite(), f"{name} must be finite")
    return out

def validate_observed_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_sha: str | None = None,
) -> dict[str, Any]:
    require(
        manifest.get("schema_version")
        == "candidate_e_v2_july10_observed_entry_manifest.v1",
        "unexpected observed-entry manifest schema",
    )
    require(manifest.get("scenario_count") == 60, "scenario count changed")
    expected_classes = {
        "EXACT": 27,
        "CENSORED_SELECTION_REARM_ONLY": 27,
        "CENSORED_LIQUIDATION_ONLY": 3,
        "CENSORED_BOTH": 3,
    }
    require(
        manifest.get("scenario_class_counts") == expected_classes,
        "censorship subclass counts changed",
    )
    trades = manifest.get("observed_filled_trades")
    require(isinstance(trades, list), "observed_filled_trades must be a list")
    require(len(trades) == 93, "expected 93 observed filled trades")
    tickers = manifest.get("settlement_ticker_universe")
    require(
        isinstance(tickers, list)
        and tickers == sorted(set(tickers))
        and all(isinstance(x, str) and x for x in tickers),
        "settlement ticker universe is not unique/sorted",
    )
    require(
        manifest.get("unique_observed_market_ticker_count") == len(tickers),
        "unique ticker count mismatch",
    )
    for row in trades:
        require(row["path_observation_class"] in {"EXACT", "CENSORED"}, "bad path class")
        require(row["side"] in {"YES", "NO"}, "bad side")
        fill = d(row["entry_filled_quantity"], "entry fill")
        residual = d(row["known_residual_settlement_quantity"], "residual")
        require(fill > 0, "nonpositive observed fill")
        require(Decimal("0") <= residual <= fill, "invalid residual quantity")
        require(row["market_ticker"] in tickers, "trade ticker absent from frozen ticker set")
    safety = manifest.get("safety", {})
    require(safety.get("derived_from_outcome_blind_path_only") is True, "manifest not outcome-blind")
    require(safety.get("settlement_fields_read") is False, "manifest read settlement fields")
    require(int(safety.get("network_requests", -1)) == 0, "manifest network requests != 0")
    require(int(safety.get("orders_placed", -1)) == 0, "manifest orders != 0")
    if expected_sha is not None:
        require(canonical_json_sha(manifest) == expected_sha, "observed-entry manifest SHA mismatch")
    return dict(manifest)

def validate_predeclaration(repo_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repo_root)
    predecl = load_json(repo / PREDECLARATION_PATH)
    require(
        predecl.get("schema_version")
        == "candidate_e_v2_july10_settlement_sensitivity_predeclaration.v1",
        "unexpected sensitivity predeclaration schema",
    )
    require(predecl.get("checkpoint_id") == "21N-Y-E1", "checkpoint id mismatch")
    require(
        predecl.get("analysis_role") == "post_outcome_exploratory_sensitivity_only",
        "analysis role changed",
    )

    official = predecl["official_result_binding"]
    require(official["official_result_remains_immutable"] is True, "official result changed")
    require(official["exact_scenarios"] == 27, "official exact count changed")
    require(official["censored_scenarios"] == 33, "official censored count changed")
    require(
        official["robustness_classification_counts"] == {"INCONCLUSIVE": 15},
        "official robustness result changed",
    )
    require(
        sha256_file(repo / OFFICIAL_SETTLEMENT_MANIFEST_PATH)
        == official["settlement_manifest_sha256"],
        "official settlement manifest SHA mismatch",
    )
    require(
        sha256_file(repo / OFFICIAL_PNL_REPORT_PATH)
        == official["pnl_report_sha256"],
        "official P&L report SHA mismatch",
    )

    manifest = load_json(repo / OBSERVED_MANIFEST_PATH)
    manifest = validate_observed_manifest(
        manifest,
        expected_sha=predecl["observed_entry_manifest"]["sha256"],
    )
    future = predecl["future_settlement_access"]
    require(
        future["exact_ticker_universe"] == manifest["settlement_ticker_universe"],
        "future settlement ticker universe drifted",
    )
    require(
        future["ticker_count"] == len(manifest["settlement_ticker_universe"]),
        "future settlement ticker count mismatch",
    )

    analyses = predecl["analyses"]
    require(
        set(analyses)
        == {
            "coherent_liquidation_only_hybrid",
            "observed_trace_terminal_value",
            "independent_entry_settlement_diagnostic",
        },
        "analysis menu changed",
    )
    coherent = analyses["coherent_liquidation_only_hybrid"]
    require(coherent["exact_27_use_official_pnl_unchanged"] is True, "exact-27 rule changed")
    require(coherent["liquidation_only_censored_scenarios"] == 3, "liquidation-only count changed")
    require(
        coherent["selection_or_rearm_censored_scenarios_remain_incomplete"] == 30,
        "selection/rearm count changed",
    )

    interp = predecl["interpretation"]
    require(interp["cannot_override_official_inconclusive_result"] is True, "official-result firewall changed")
    require(interp["policy_ranking_or_selection_forbidden"] is True, "policy-ranking firewall changed")

    safety = predecl["safety"]
    require(safety["new_outcomes_accessed_during_predeclaration"] is False, "new outcome access occurred")
    require(int(safety["network_requests_by_predeclaration"]) == 0, "network requests != 0")
    require(int(safety["orders_placed"]) == 0, "orders != 0")
    return predecl

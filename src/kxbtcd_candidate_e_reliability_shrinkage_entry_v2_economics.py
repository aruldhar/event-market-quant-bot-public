"""Checkpoint 21N-G frozen Strategy-v2 development economics.

Scores ONLY alpha=0.50 and alpha=0.75 from the exact frozen 21N-F
outcome-independent selection artifact. Alpha=0.25 is sample-ineligible and
alpha=1.00 is the already-known Strategy-v1 reference; this module refuses to
score either one.

This is quoted-entry historical screening, not a historical fill simulation.
It has no network, order, paper-broker, demo, or real-execution surface.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_reliability_shrinkage_entry_v2_development_economics.json")
AUDIT_CLOSEOUT_PATH = Path("configs/kxbtcd_candidate_e_reliability_shrinkage_entry_v2_opportunity_audit_result_closeout.json")
STRATEGY_V2_CONFIG_PATH = Path("configs/kxbtcd_candidate_e_reliability_shrinkage_entry_v2.json")

STRATEGY_ID = "kxbtcd_candidate_e_reliability_shrinkage_entry_v2"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
EXPECTED_STRATEGY_V2_FINGERPRINT = "b3fd3a3c71c5750604ef4e6eddd23043a75952d2c06a48cbb39ae6ef1066bd50"
EXPECTED_STRATEGY_V2_CONFIG_SHA256 = "8e8e56c5960ecd8e3d2ee3c3b864eeabb513945ed58e79a0f15aa62dcebc512e"
EXPECTED_AUDIT_FINGERPRINT = "b0971d51ac76fc26402dfbab49fde85167cb0bb4153069b80d1db2dbaccdcf20"
EXPECTED_AUDIT_CLOSEOUT_FINGERPRINT = "ff2a021063155c6fdfd012818363faccc2906468471d61b49e61572740606dcd"
EXPECTED_SELECTION_SHA256 = "ff4aa15a61f8b98506a35626113bd60e4cc9c1758a3504065ed452074e6e6790"
EXPECTED_ECONOMICS_FINGERPRINT = "139435ffb43d51d09afa4154aeba2fe9c22cb82b5b7edd435516d4ab71e2c55f"

DEVELOPMENT_STAGES = ("H1_OOF", "H2", "H3")
EXPECTED_STAGE_EVENTS = {"H1_OOF": 1070, "H2": 750, "H3": 750}
EXPECTED_TOTAL_EVENTS = 2570
BLOCK_COUNT = 5
EVENTS_PER_BLOCK = 514

PREDICTION_SCHEMAS = {
    "H1_OOF": "kxbtcd_candidate_e_h1_oof_prediction.v1",
    "H2": "kxbtcd_candidate_e_h2_prediction.v1",
    "H3": "kxbtcd_candidate_e_h3_prediction.v1",
}
EXPECTED_PREDICTION_SHA256S = {
    "H1_OOF": "867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16",
    "H2": "4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6",
    "H3": "091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380",
}
EXPECTED_PREDICTION_ROW_COUNTS = {"H1_OOF": 31656, "H2": 22354, "H3": 22409}
ONE_CENT = Decimal("0.01")
FEE_RATE = Decimal("0.07")

ALL_AUDIT_ALPHAS = (Decimal("0.25"), Decimal("0.50"), Decimal("0.75"), Decimal("1.00"))
ELIGIBLE_ALPHAS = (Decimal("0.50"), Decimal("0.75"))
PROHIBITED_SCORE_ALPHAS = (Decimal("0.25"), Decimal("1.00"))
EXPECTED_ENTER_COUNTS = {
    Decimal("0.25"): 15,
    Decimal("0.50"): 276,
    Decimal("0.75"): 591,
    Decimal("1.00"): 820,
}
EXPECTED_STAGE_ENTER_COUNTS = {
    Decimal("0.25"): {"H1_OOF": 3, "H2": 6, "H3": 6},
    Decimal("0.50"): {"H1_OOF": 75, "H2": 102, "H3": 99},
    Decimal("0.75"): {"H1_OOF": 203, "H2": 191, "H3": 197},
    Decimal("1.00"): {"H1_OOF": 308, "H2": 254, "H3": 258},
}
STRESSES = (Decimal("0.00"), Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))

SELECTION_SCHEMA = "kxbtcd_candidate_e_reliability_shrinkage_event_selection.v1"
EVALUATION_SCHEMA = "kxbtcd_candidate_e_reliability_shrinkage_development_economic_evaluation.v1"
RECEIPT_SCHEMA = "kxbtcd_candidate_e_reliability_shrinkage_development_economic_receipt.v1"

SCENARIO_FIELDS = (
    "schema_version","strategy_id","alpha","stress_dollars","event_ticker",
    "event_close_time_utc","block_id","stage","action","market_ticker",
    "structural_role","ttc_target_minutes","side","candidate_probability",
    "market_midpoint_yes_probability","candidate_side_probability",
    "adjusted_side_probability","quoted_purchase_price",
    "quoted_standard_entry_fee","adjusted_net_edge_per_contract","outcome",
    "side_payout","scenario_valid","scenario_purchase_price",
    "scenario_standard_entry_fee","scenario_capital_deployed",
    "scenario_realized_pnl",
)

ALPHA_SCORE_FIELDS = (
    "alpha","entry_count","abstention_count","base_mean_pnl_per_event",
    "plus_1c_mean_pnl_per_event","base_positive_block_count",
    "base_newest_block_positive","base_h3_mean_pnl_per_event",
    "condition_base_pooled_positive","condition_plus_1c_pooled_positive",
    "condition_at_least_4_of_5_blocks_positive",
    "condition_newest_block_positive","condition_h3_positive",
    "development_gate_pass",
)


class ReliabilityShrinkageEconomicsError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise ReliabilityShrinkageEconomicsError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ReliabilityShrinkageEconomicsError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _unit(value: Any, name: str) -> Decimal:
    result = _decimal(value, name)
    if result < 0 or result > 1:
        _error(f"{name} must be in [0,1]")
    return result


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    if "." not in text:
        return text + ".0"
    stripped = text.rstrip("0").rstrip(".")
    return stripped if stripped else "0"



def _parse_outcome(value: Any, name: str) -> int:
    text = str(value).strip()
    if text not in {"0", "1", "0.0", "1.0"}:
        _error(f"{name} must be binary 0/1")
    return int(float(text))


def standard_entry_fee(price: Decimal) -> Decimal:
    price = _unit(price, "fee price")
    raw = FEE_RATE * price * (Decimal("1") - price)
    return raw.quantize(ONE_CENT, rounding=ROUND_CEILING)


def _parse_utc(value: Any, name: str) -> datetime:
    text = str(value).strip()
    if not text:
        _error(f"{name} is empty")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReliabilityShrinkageEconomicsError(f"{name} is not ISO timestamp") from exc
    if dt.tzinfo is None:
        _error(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def canonical_sha256(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: str | Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value


def _validate_canonical_fingerprint(
    document: Mapping[str, Any], *, field: str, expected: str, label: str
) -> None:
    supplied = str(document.get(field, "")).strip()
    copy = dict(document)
    copy.pop(field, None)
    calculated = canonical_sha256(copy)
    if supplied != calculated:
        _error(f"{label} fingerprint does not reproduce: {supplied} != {calculated}")
    if supplied != expected:
        _error(f"{label} fingerprint is not frozen expected value")



def build_outcome_map(
    sources_by_stage: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    source_paths: Mapping[str, str | Path] | None = None,
    enforce_frozen_counts: bool = True,
) -> dict[tuple[str, str, str], int]:
    if set(sources_by_stage) != set(DEVELOPMENT_STAGES):
        _error("outcome sources must be exactly H1_OOF, H2, H3")
    if source_paths is not None:
        for stage, expected in EXPECTED_PREDICTION_SHA256S.items():
            path = source_paths.get(stage)
            if path is None or sha256_file(path) != expected:
                _error(f"{stage} prediction source hash changed")

    result: dict[tuple[str, str, str], int] = {}
    stage_rows = {stage: 0 for stage in DEVELOPMENT_STAGES}
    stage_events = {stage: set() for stage in DEVELOPMENT_STAGES}
    state_seen = {stage: set() for stage in DEVELOPMENT_STAGES}

    for stage in DEVELOPMENT_STAGES:
        schema = PREDICTION_SCHEMAS[stage]
        for index, source in enumerate(sources_by_stage[stage]):
            if source.get("schema_version") != schema:
                _error(f"{stage} outcome row[{index}] schema mismatch")
            if source.get("candidate_id") != CANDIDATE_ID:
                continue
            state = str(source.get("state_id", "")).strip()
            event = str(source.get("event_ticker", "")).strip()
            market = str(source.get("market_ticker", "")).strip()
            if not state or not event or not market:
                _error(f"{stage} outcome row[{index}] identity missing")
            if state in state_seen[stage]:
                _error(f"duplicate {stage} state {state}")
            state_seen[stage].add(state)
            stage_rows[stage] += 1
            stage_events[stage].add(event)
            outcome = _parse_outcome(source.get("outcome"), f"{stage}[{index}].outcome")
            key = (stage, event, market)
            prior = result.setdefault(key, outcome)
            if prior != outcome:
                _error(f"inconsistent outcome for {stage}/{event}/{market}")

    if enforce_frozen_counts:
        for stage in DEVELOPMENT_STAGES:
            if stage_rows[stage] != EXPECTED_PREDICTION_ROW_COUNTS[stage]:
                _error(f"{stage} Candidate-E outcome row count changed")
            if len(stage_events[stage]) != EXPECTED_STAGE_EVENTS[stage]:
                _error(f"{stage} Candidate-E event count changed")
    return result


def validate_audit_result_closeout(path: str | Path = AUDIT_CLOSEOUT_PATH) -> dict[str, Any]:
    doc = load_json(path)
    if doc.get("schema_version") != "kxbtcd_candidate_e_reliability_shrinkage_opportunity_audit_result_closeout.v1":
        _error("opportunity-audit result closeout schema mismatch")
    if doc.get("strategy_id") != STRATEGY_ID:
        _error("opportunity-audit closeout strategy mismatch")
    if doc.get("strategy_v2_predeclaration_fingerprint") != EXPECTED_STRATEGY_V2_FINGERPRINT:
        _error("opportunity-audit closeout Strategy-v2 fingerprint mismatch")
    _validate_canonical_fingerprint(
        doc,
        field="opportunity_audit_result_closeout_fingerprint",
        expected=EXPECTED_AUDIT_CLOSEOUT_FINGERPRINT,
        label="opportunity-audit result closeout",
    )
    audit = doc.get("opportunity_audit", {})
    if audit.get("audit_fingerprint") != EXPECTED_AUDIT_FINGERPRINT:
        _error("frozen opportunity audit fingerprint mismatch")
    if audit.get("alpha_event_selections_sha256") != EXPECTED_SELECTION_SHA256:
        _error("frozen alpha selection SHA mismatch")
    continuation = doc.get("continuation", {})
    if continuation.get("selection_eligible_alphas") != ["0.50", "0.75"]:
        _error("selection-eligible alpha set changed")
    if continuation.get("alpha_0_25_outcome_scoring_allowed") is not False:
        _error("alpha=0.25 outcome scoring must remain prohibited")
    if continuation.get("alpha_1_outcome_rescoring_allowed") is not False:
        _error("alpha=1 outcome rescoring must remain prohibited")
    for key, expected_alpha in (("0.25", Decimal("0.25")), ("0.50", Decimal("0.50")), ("0.75", Decimal("0.75")), ("1.00", Decimal("1.00"))):
        result = doc["alpha_results"][key]
        if result.get("entry_count") != EXPECTED_ENTER_COUNTS[expected_alpha]:
            _error(f"closeout entry count changed for alpha={key}")
    for key, value in doc.get("safety", {}).items():
        if value is not False:
            _error(f"closeout safety.{key} must be false")
    return doc


def validate_economics_predeclaration(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    doc = load_json(path)
    if doc.get("schema_version") != "kxbtcd_candidate_e_reliability_shrinkage_development_economics_predeclaration.v1":
        _error("development economics schema mismatch")
    if doc.get("strategy_id") != STRATEGY_ID or doc.get("candidate_id") != CANDIDATE_ID:
        _error("development economics identity mismatch")
    if doc.get("parent_strategy_v2_predeclaration_fingerprint") != EXPECTED_STRATEGY_V2_FINGERPRINT:
        _error("parent Strategy-v2 fingerprint mismatch")
    binding = doc.get("opportunity_audit_binding", {})
    if binding.get("audit_fingerprint") != EXPECTED_AUDIT_FINGERPRINT:
        _error("economics opportunity-audit fingerprint mismatch")
    if binding.get("audit_result_closeout_fingerprint") != EXPECTED_AUDIT_CLOSEOUT_FINGERPRINT:
        _error("economics audit-closeout fingerprint mismatch")
    if binding.get("alpha_event_selections_sha256") != EXPECTED_SELECTION_SHA256:
        _error("economics selection SHA mismatch")
    policy = doc.get("alpha_policy", {})
    if tuple(_decimal(v, "eligible alpha") for v in policy.get("selection_eligible_alphas", ())) != ELIGIBLE_ALPHAS:
        _error("eligible alpha menu changed")
    if tuple(_decimal(v, "prohibited alpha") for v in policy.get("outcome_scoring_prohibited_alphas", ())) != PROHIBITED_SCORE_ALPHAS:
        _error("prohibited scoring alpha menu changed")
    if policy.get("no_new_alpha_search") is not True or policy.get("no_post_outcome_alpha_repair") is not True:
        _error("post-outcome alpha-search firewall changed")
    if tuple(_decimal(v, "stress") for v in doc["stress_policy"]["adverse_purchase_price_stress_dollars"]) != STRESSES:
        _error("stress menu changed")
    if doc["development_scope"].get("chronological_block_count") != BLOCK_COUNT:
        _error("chronological block count changed")
    if doc["development_scope"].get("events_per_block") != EVENTS_PER_BLOCK:
        _error("chronological block size changed")
    safety = doc.get("safety", {})
    for key in (
        "development_strategy_pnl_calculated_before_implementation_freeze",
        "c1_c2_strategy_pnl_authorized","c3_accessed","protected_reserve_accessed",
        "network_access_authorized","paper_broker_authorized",
        "demo_execution_authorized","real_money_execution_authorized","orders_authorized",
    ):
        if safety.get(key) is not False:
            _error(f"economics safety.{key} must be false")
    _validate_canonical_fingerprint(
        doc,
        field="development_economics_predeclaration_fingerprint",
        expected=EXPECTED_ECONOMICS_FINGERPRINT,
        label="development economics",
    )
    return doc


def validate_strategy_v2_config(path: str | Path = STRATEGY_V2_CONFIG_PATH) -> dict[str, Any]:
    if sha256_file(path) != EXPECTED_STRATEGY_V2_CONFIG_SHA256:
        _error("Strategy-v2 config SHA changed from frozen opportunity audit")
    doc = load_json(path)
    if doc.get("strategy_id") != STRATEGY_ID:
        _error("Strategy-v2 config identity mismatch")
    if doc.get("strategy_v2_predeclaration_fingerprint") != EXPECTED_STRATEGY_V2_FINGERPRINT:
        _error("Strategy-v2 config fingerprint mismatch")
    return doc


def validate_opportunity_summary(summary: Mapping[str, Any]) -> None:
    if summary.get("strategy_id") != STRATEGY_ID:
        _error("opportunity summary strategy mismatch")
    if summary.get("strategy_v2_predeclaration_fingerprint") != EXPECTED_STRATEGY_V2_FINGERPRINT:
        _error("opportunity summary Strategy-v2 fingerprint mismatch")
    supplied = str(summary.get("audit_fingerprint", "")).strip()
    if supplied != EXPECTED_AUDIT_FINGERPRINT:
        _error("opportunity summary audit fingerprint mismatch")
    copy = dict(summary)
    copy.pop("audit_fingerprint", None)
    output_hashes = copy.pop("output_sha256s", None)
    if canonical_sha256(copy) != EXPECTED_AUDIT_FINGERPRINT:
        _error("opportunity summary does not reproduce frozen audit fingerprint")
    if not isinstance(output_hashes, dict):
        _error("opportunity summary output hashes missing")
    if output_hashes.get("alpha_event_selections") != EXPECTED_SELECTION_SHA256:
        _error("opportunity summary alpha selection SHA mismatch")
    if summary.get("scope", {}).get("settlement_outcomes_used") is not False:
        _error("opportunity audit unexpectedly used outcomes")
    if summary.get("scope", {}).get("realized_pnl_calculated") is not False:
        _error("opportunity audit unexpectedly calculated P&L")
    if summary.get("continuation", {}).get("any_candidate_materiality_pass") is not True:
        _error("opportunity audit continuation result changed")
    if summary.get("selection", {}).get("alpha_winner_selected") is not False:
        _error("opportunity audit must not have selected alpha")
    for key, value in summary.get("safety", {}).items():
        if value is not False:
            _error(f"opportunity summary safety.{key} must be false")


def validate_selection_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    selection_path: str | Path | None = None,
) -> tuple[dict[str, str], ...]:
    if selection_path is not None and sha256_file(selection_path) != EXPECTED_SELECTION_SHA256:
        _error("alpha-event selection file SHA changed from frozen opportunity audit")
    expected_rows = EXPECTED_TOTAL_EVENTS * len(ALL_AUDIT_ALPHAS)
    if len(rows) != expected_rows:
        _error(f"alpha-event selection row count changed: {len(rows)} != {expected_rows}")

    seen: set[tuple[Decimal, str]] = set()
    event_identity: dict[str, tuple[str, str]] = {}
    per_alpha_events = {a: set() for a in ALL_AUDIT_ALPHAS}
    enter_counts = {a: 0 for a in ALL_AUDIT_ALPHAS}
    stage_enter_counts = {a: {s: 0 for s in DEVELOPMENT_STAGES} for a in ALL_AUDIT_ALPHAS}
    projected: list[dict[str, str]] = []

    for index, source in enumerate(rows):
        if source.get("schema_version") != SELECTION_SCHEMA:
            _error(f"selection row[{index}] schema mismatch")
        if source.get("strategy_id") != STRATEGY_ID:
            _error(f"selection row[{index}] strategy mismatch")
        alpha = _decimal(source.get("alpha"), f"selection[{index}].alpha")
        if alpha not in ALL_AUDIT_ALPHAS:
            _error(f"selection row[{index}] alpha outside frozen audit menu")
        event = str(source.get("event_ticker", "")).strip()
        close = str(source.get("event_close_time_utc", "")).strip()
        stage = str(source.get("stage", "")).strip()
        action = str(source.get("action", "")).strip()
        if not event or not close or stage not in DEVELOPMENT_STAGES:
            _error(f"selection row[{index}] incomplete event identity")
        _parse_utc(close, f"selection[{index}].event_close_time_utc")
        if action not in {"ENTER", "ABSTAIN"}:
            _error(f"selection row[{index}] invalid action")
        key = (alpha, event)
        if key in seen:
            _error(f"duplicate alpha/event selection: {alpha} {event}")
        seen.add(key)
        per_alpha_events[alpha].add(event)
        prior = event_identity.setdefault(event, (close, stage))
        if prior != (close, stage):
            _error(f"inconsistent event identity across alphas: {event}")
        if action == "ENTER":
            enter_counts[alpha] += 1
            stage_enter_counts[alpha][stage] += 1
            for field in (
                "market_ticker","structural_role","ttc_target_minutes","side",
                "quoted_purchase_price","standard_entry_fee",
                "adjusted_net_edge_per_contract",
            ):
                if not str(source.get(field, "")).strip():
                    _error(f"selection row[{index}] ENTER missing {field}")
        projected.append({k: str(v) if v is not None else "" for k, v in source.items()})

    if len(event_identity) != EXPECTED_TOTAL_EVENTS:
        _error("development event universe changed")
    for alpha in ALL_AUDIT_ALPHAS:
        if len(per_alpha_events[alpha]) != EXPECTED_TOTAL_EVENTS:
            _error(f"alpha={alpha} event universe incomplete")
        if enter_counts[alpha] != EXPECTED_ENTER_COUNTS[alpha]:
            _error(f"alpha={alpha} enter count changed")
        if stage_enter_counts[alpha] != EXPECTED_STAGE_ENTER_COUNTS[alpha]:
            _error(f"alpha={alpha} stage entry counts changed")
    return tuple(projected)


def _block_map(rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    reference = [r for r in rows if _decimal(r["alpha"], "alpha") == Decimal("1.00")]
    ordered = sorted(
        ((str(r["event_ticker"]), _parse_utc(r["event_close_time_utc"], "close")) for r in reference),
        key=lambda x: (x[1], x[0]),
    )
    if len(ordered) != EXPECTED_TOTAL_EVENTS:
        _error("reference event count changed while building blocks")
    return {event: f"B{i // EVENTS_PER_BLOCK}" for i, (event, _) in enumerate(ordered)}


def _max_drawdown(pnls: Sequence[Decimal]) -> Decimal:
    cumulative = Decimal("0")
    peak = Decimal("0")
    worst = Decimal("0")
    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > worst:
            worst = drawdown
    return worst


def _metric_summary(
    scenario_rows: Sequence[Mapping[str, str]],
    *,
    alpha: Decimal,
    stress: Decimal,
) -> dict[str, Any]:
    rows = [
        r for r in scenario_rows
        if _decimal(r["alpha"], "alpha") == alpha
        and _decimal(r["stress_dollars"], "stress") == stress
    ]
    if len(rows) != EXPECTED_TOTAL_EVENTS:
        _error("scenario metric event count mismatch")
    scenario_valid = all(r["scenario_valid"] == "true" for r in rows)
    entry_rows = [r for r in rows if r["action"] == "ENTER"]
    abstentions = EXPECTED_TOTAL_EVENTS - len(entry_rows)
    if not scenario_valid:
        return {
            "scenario_valid": False,
            "entry_count": len(entry_rows),
            "abstention_count": abstentions,
            "total_net_pnl": None,
            "mean_pnl_per_event": None,
            "mean_pnl_per_trade": None,
            "total_capital_deployed": None,
            "return_on_deployed_capital": None,
            "win_rate": None,
            "maximum_drawdown": None,
            "worst_trade": None,
            "stage_metrics": {},
            "block_metrics": {},
        }

    chronological_rows = sorted(
        rows,
        key=lambda r: (
            _parse_utc(r["event_close_time_utc"], "scenario event close"),
            r["event_ticker"],
        ),
    )
    pnls = [_decimal(r["scenario_realized_pnl"], "scenario pnl") for r in chronological_rows]
    entry_pnls = [_decimal(r["scenario_realized_pnl"], "entry pnl") for r in entry_rows]
    capital = sum((_decimal(r["scenario_capital_deployed"], "capital") for r in entry_rows), Decimal("0"))
    total = sum(pnls, Decimal("0"))
    mean_event = total / Decimal(EXPECTED_TOTAL_EVENTS)
    mean_trade = total / Decimal(len(entry_rows)) if entry_rows else None
    roc = total / capital if capital > 0 else None
    win_rate = (
        Decimal(sum(p > 0 for p in entry_pnls)) / Decimal(len(entry_pnls))
        if entry_pnls else None
    )
    worst_trade = min(entry_pnls) if entry_pnls else None

    stage_metrics = {}
    for stage in DEVELOPMENT_STAGES:
        subset = [r for r in rows if r["stage"] == stage]
        stage_total = sum((_decimal(r["scenario_realized_pnl"], "stage pnl") for r in subset), Decimal("0"))
        stage_entries = sum(r["action"] == "ENTER" for r in subset)
        stage_metrics[stage] = {
            "event_count": len(subset),
            "entry_count": stage_entries,
            "total_net_pnl": _fmt(stage_total),
            "mean_pnl_per_event": _fmt(stage_total / Decimal(len(subset))),
        }

    block_metrics = {}
    for block in (f"B{i}" for i in range(BLOCK_COUNT)):
        subset = [r for r in rows if r["block_id"] == block]
        block_total = sum((_decimal(r["scenario_realized_pnl"], "block pnl") for r in subset), Decimal("0"))
        block_metrics[block] = {
            "event_count": len(subset),
            "entry_count": sum(r["action"] == "ENTER" for r in subset),
            "total_net_pnl": _fmt(block_total),
            "mean_pnl_per_event": _fmt(block_total / Decimal(len(subset))),
        }

    return {
        "scenario_valid": True,
        "entry_count": len(entry_rows),
        "abstention_count": abstentions,
        "total_net_pnl": _fmt(total),
        "mean_pnl_per_event": _fmt(mean_event),
        "mean_pnl_per_trade": _fmt(mean_trade),
        "total_capital_deployed": _fmt(capital),
        "return_on_deployed_capital": _fmt(roc),
        "win_rate": _fmt(win_rate),
        "maximum_drawdown": _fmt(_max_drawdown(pnls)),
        "worst_trade": _fmt(worst_trade),
        "stage_metrics": stage_metrics,
        "block_metrics": block_metrics,
    }


def _base_diagnostics(
    scenario_rows: Sequence[Mapping[str, str]], *, alpha: Decimal
) -> dict[str, Any]:
    rows = [
        r for r in scenario_rows
        if _decimal(r["alpha"], "alpha") == alpha
        and _decimal(r["stress_dollars"], "stress") == Decimal("0")
        and r["action"] == "ENTER"
    ]
    result = {}
    for dimension in ("side", "ttc_target_minutes", "structural_role"):
        values = sorted({r[dimension] for r in rows})
        dim = {}
        for value in values:
            subset = [r for r in rows if r[dimension] == value]
            total = sum((_decimal(r["scenario_realized_pnl"], "diagnostic pnl") for r in subset), Decimal("0"))
            dim[value] = {
                "entry_count": len(subset),
                "total_net_pnl": _fmt(total),
                "mean_net_pnl_per_trade": _fmt(total / Decimal(len(subset))),
            }
        result[dimension] = dim
    return result


def build_development_economic_evaluation(
    selection_rows: Sequence[Mapping[str, str]],
    outcome_map: Mapping[str, int],
) -> tuple[dict[str, Any], tuple[dict[str, str], ...], tuple[dict[str, str], ...]]:
    blocks = _block_map(selection_rows)
    eligible_rows = [
        r for r in selection_rows
        if _decimal(r["alpha"], "alpha") in ELIGIBLE_ALPHAS
    ]
    expected_eligible_rows = EXPECTED_TOTAL_EVENTS * len(ELIGIBLE_ALPHAS)
    if len(eligible_rows) != expected_eligible_rows:
        _error("eligible selection projection row count mismatch")

    scenario_rows: list[dict[str, str]] = []
    for alpha in ELIGIBLE_ALPHAS:
        alpha_rows = [r for r in eligible_rows if _decimal(r["alpha"], "alpha") == alpha]
        for stress in STRESSES:
            invalid_scenario = False
            staged: list[dict[str, str]] = []
            for row in alpha_rows:
                event = row["event_ticker"]
                action = row["action"]
                outcome = None
                if action == "ENTER":
                    market = row["market_ticker"]
                    outcome_key = (row["stage"], event, market)
                    if outcome_key not in outcome_map:
                        _error(f"selected market outcome missing: {outcome_key}")
                    outcome = int(outcome_map[outcome_key])
                base = {
                    "schema_version": "kxbtcd_candidate_e_reliability_shrinkage_event_pnl_scenario.v1",
                    "strategy_id": STRATEGY_ID,
                    "alpha": _fmt(alpha),
                    "stress_dollars": _fmt(stress),
                    "event_ticker": event,
                    "event_close_time_utc": row["event_close_time_utc"],
                    "block_id": blocks[event],
                    "stage": row["stage"],
                    "action": action,
                    "market_ticker": row.get("market_ticker", ""),
                    "structural_role": row.get("structural_role", ""),
                    "ttc_target_minutes": row.get("ttc_target_minutes", ""),
                    "side": row.get("side", ""),
                    "candidate_probability": row.get("candidate_probability", ""),
                    "market_midpoint_yes_probability": row.get("market_midpoint_yes_probability", ""),
                    "candidate_side_probability": row.get("candidate_side_probability", ""),
                    "adjusted_side_probability": row.get("adjusted_side_probability", ""),
                    "quoted_purchase_price": row.get("quoted_purchase_price", ""),
                    "quoted_standard_entry_fee": row.get("standard_entry_fee", ""),
                    "adjusted_net_edge_per_contract": row.get("adjusted_net_edge_per_contract", ""),
                    "outcome": "" if outcome is None else str(outcome),
                }
                if action == "ABSTAIN":
                    staged.append({
                        **base,
                        "side_payout": "",
                        "scenario_valid": "true",
                        "scenario_purchase_price": "",
                        "scenario_standard_entry_fee": "",
                        "scenario_capital_deployed": "0",
                        "scenario_realized_pnl": "0",
                    })
                    continue

                price = _unit(row["quoted_purchase_price"], "quoted purchase price") + stress
                valid = Decimal("0") <= price <= Decimal("1")
                if not valid:
                    invalid_scenario = True
                    staged.append({
                        **base,
                        "side_payout": "",
                        "scenario_valid": "false",
                        "scenario_purchase_price": _fmt(price),
                        "scenario_standard_entry_fee": "",
                        "scenario_capital_deployed": "",
                        "scenario_realized_pnl": "",
                    })
                    continue
                fee = standard_entry_fee(price)
                side = row["side"]
                if side == "YES":
                    payout = Decimal(outcome)
                elif side == "NO":
                    payout = Decimal(1 - outcome)
                else:
                    _error(f"invalid ENTER side {side!r}")
                pnl = payout - price - fee
                staged.append({
                    **base,
                    "side_payout": _fmt(payout),
                    "scenario_valid": "true",
                    "scenario_purchase_price": _fmt(price),
                    "scenario_standard_entry_fee": _fmt(fee),
                    "scenario_capital_deployed": _fmt(price + fee),
                    "scenario_realized_pnl": _fmt(pnl),
                })
            if invalid_scenario:
                # Fail the entire alpha/stress scenario closed.
                for row in staged:
                    row["scenario_valid"] = "false"
            scenario_rows.extend(staged)

    alpha_results: dict[str, Any] = {}
    score_rows: list[dict[str, str]] = []
    for alpha in ELIGIBLE_ALPHAS:
        stress_metrics = {
            _fmt(stress): _metric_summary(scenario_rows, alpha=alpha, stress=stress)
            for stress in STRESSES
        }
        base = stress_metrics["0"]
        plus1 = stress_metrics["0.01"]

        valid_gate_metrics = base["scenario_valid"] and plus1["scenario_valid"]
        if valid_gate_metrics:
            base_mean = _decimal(base["mean_pnl_per_event"], "base mean")
            plus1_mean = _decimal(plus1["mean_pnl_per_event"], "+1c mean")
            positive_blocks = sum(
                _decimal(base["block_metrics"][f"B{i}"]["mean_pnl_per_event"], "block mean") > 0
                for i in range(BLOCK_COUNT)
            )
            newest_positive = _decimal(base["block_metrics"]["B4"]["mean_pnl_per_event"], "B4 mean") > 0
            h3_mean = _decimal(base["stage_metrics"]["H3"]["mean_pnl_per_event"], "H3 mean")
            conditions = {
                "condition_base_pooled_positive": base_mean > 0,
                "condition_plus_1c_pooled_positive": plus1_mean > 0,
                "condition_at_least_4_of_5_blocks_positive": positive_blocks >= 4,
                "condition_newest_block_positive": newest_positive,
                "condition_h3_positive": h3_mean > 0,
            }
        else:
            positive_blocks = 0
            newest_positive = False
            h3_mean = Decimal("0")
            conditions = {
                "condition_base_pooled_positive": False,
                "condition_plus_1c_pooled_positive": False,
                "condition_at_least_4_of_5_blocks_positive": False,
                "condition_newest_block_positive": False,
                "condition_h3_positive": False,
            }
        gate_pass = all(conditions.values())
        alpha_key = _fmt(alpha)
        alpha_results[alpha_key] = {
            "alpha": alpha_key,
            "selection_eligible": True,
            "stress_metrics": stress_metrics,
            "base_diagnostics": _base_diagnostics(scenario_rows, alpha=alpha),
            "base_positive_block_count": positive_blocks,
            "base_newest_block_positive": newest_positive,
            "base_h3_mean_pnl_per_event": _fmt(h3_mean),
            **conditions,
            "development_gate_pass": gate_pass,
        }
        score_rows.append({
            "alpha": alpha_key,
            "entry_count": str(base["entry_count"]),
            "abstention_count": str(base["abstention_count"]),
            "base_mean_pnl_per_event": "" if base["mean_pnl_per_event"] is None else str(base["mean_pnl_per_event"]),
            "plus_1c_mean_pnl_per_event": "" if plus1["mean_pnl_per_event"] is None else str(plus1["mean_pnl_per_event"]),
            "base_positive_block_count": str(positive_blocks),
            "base_newest_block_positive": str(newest_positive).lower(),
            "base_h3_mean_pnl_per_event": _fmt(h3_mean),
            **{k: str(v).lower() for k, v in conditions.items()},
            "development_gate_pass": str(gate_pass).lower(),
        })

    passers = [
        alpha for alpha in ELIGIBLE_ALPHAS
        if alpha_results[_fmt(alpha)]["development_gate_pass"]
    ]
    if passers:
        # Highest +1c stressed mean P&L/event. Exact tie -> lower alpha.
        selected = sorted(
            passers,
            key=lambda a: (
                -_decimal(alpha_results[_fmt(a)]["stress_metrics"]["0.01"]["mean_pnl_per_event"], "+1 mean"),
                a,
            ),
        )[0]
        status = "PASS_SELECTED_ALPHA"
        selected_alpha: str | None = _fmt(selected)
    else:
        status = "FAIL_NO_ALPHA"
        selected_alpha = None

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "strategy_id": STRATEGY_ID,
        "strategy_v2_predeclaration_fingerprint": EXPECTED_STRATEGY_V2_FINGERPRINT,
        "opportunity_audit_fingerprint": EXPECTED_AUDIT_FINGERPRINT,
        "opportunity_audit_result_closeout_fingerprint": EXPECTED_AUDIT_CLOSEOUT_FINGERPRINT,
        "development_economics_predeclaration_fingerprint": EXPECTED_ECONOMICS_FINGERPRINT,
        "scope": {
            "event_count": EXPECTED_TOTAL_EVENTS,
            "stages": list(DEVELOPMENT_STAGES),
            "blocks": BLOCK_COUNT,
            "events_per_block": EVENTS_PER_BLOCK,
            "scored_alphas": [_fmt(a) for a in ELIGIBLE_ALPHAS],
            "alpha_0_25_scored": False,
            "alpha_1_scored": False,
        },
        "alpha_results": alpha_results,
        "selection": {
            "status": status,
            "selected_alpha": selected_alpha,
            "winner_metric": "+1c stressed pooled mean P&L per event among full-gate passers",
            "exact_tie_rule": "lower alpha",
        },
        "strategy_v1_reference": {
            "status": "FAIL_NO_THRESHOLD",
            "alpha_1_equivalent_zero_cent_base_mean_pnl_per_event": "-0.004836575875486381322957198444",
            "alpha_1_equivalent_zero_cent_plus_1c_mean_pnl_per_event": "-0.007972762645914396887159533074",
            "rescore_performed": False,
        },
        "safety": {
            "development_strategy_pnl_calculated": True,
            "alpha_0_25_outcome_scored": False,
            "alpha_1_outcome_rescored": False,
            "c1_c2_strategy_pnl_accessed": False,
            "c3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "orders_submitted": False,
            "paper_broker_used": False,
            "demo_execution_used": False,
            "real_execution_used": False,
            "historical_fill_claim": False,
            "profitability_guarantee_claim": False,
        },
    }
    evaluation["evaluation_fingerprint"] = canonical_sha256(evaluation)
    return evaluation, tuple(scenario_rows), tuple(score_rows)

"""Checkpoint 21N-S-B outcome-blind July 10 materialization result closeout.

This module validates the frozen S-B result without reading settlement outcomes
or calculating realized strategy P&L.  It also provides the reproducible
decision-book failure audit used to distinguish:
- verified-segment unavailability,
- genuinely one-sided books,
- crossed books,
- valid two-sided books.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping

CHECKPOINT_ID = "21N-S-B"
SCHEMA_VERSION = "kxbtcd_candidate_e_july10_outcome_blind_materialization_result_closeout.v1"
STRATEGY_ID = "kxbtcd_candidate_e_executable_convergence_liquidation_v1"

PARENT_CHECKPOINT_COMMIT = "e7c2e679aa5cafa2e44912ee95ac96ed0c16b1a6"
PARENT_RECEIPT_COMMIT = "a0aa0a9b263a3178cba56908b9edc543f12099d0"
S_A_IMPLEMENTATION_FINGERPRINT = "3a20d5ae9deec2e3563362bbafb9d9ac35f1965e126d07840caa0a4de28ef008"

MATERIALIZATION_RELATIVE_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_executable_convergence_liquidation_v1_outcome_blind_paths.json"
)
EXPECTED_MATERIALIZATION_SHA256 = "624dab514bfffbe1969b87bfa8d7a7bf63dfb14177666cc5d08029c056287f9a"

CLOSEOUT_RELATIVE_PATH = Path(
    "configs/kxbtcd_candidate_e_july10_outcome_blind_materialization_result_closeout.json"
)

EXPECTED_SOURCE_COUNTS = {
    "event_count": 4,
    "full_ladder_ticker_count": 623,
    "structural_ticker_count": 20,
    "btc_anchor_count": 24,
    "role_anchor_state_count": 120,
    "paid_delta_count": 5_644_964,
    "snapshot_count": 269_441,
    "pair_count": 268_818,
    "exact_pair_count": 266_034,
    "unreconciled_pair_count": 2_784,
}

EXPECTED_DECISION_STATUS_COUNTS = {
    "INVALID_TWO_SIDED_BOOK": 73,
    "SOURCE_UNAVAILABLE_DECISION_TIMESTAMP": 47,
}

EXPECTED_REFINED_BOOK_COUNTS = {
    "MISSING_YES_ASK": 33,
    "MISSING_YES_BID": 40,
    "SOURCE_UNAVAILABLE_DECISION_TIMESTAMP": 47,
    "CROSSED_TWO_SIDED_BOOK": 0,
    "VALID_TWO_SIDED_BOOK": 0,
    "EMPTY_BOTH_SIDES": 0,
}

EXPECTED_GAP_STATS = {
    "count": 47,
    "min_seconds": "4.250",
    "median_seconds": "199.314",
    "max_seconds": "1254.460",
    "lte_1_second": 0,
    "lte_10_seconds": 4,
    "lte_60_seconds": 8,
}


class OutcomeBlindMaterializationCloseoutError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise OutcomeBlindMaterializationCloseoutError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_fingerprint(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("result_closeout_fingerprint", None)
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def summarize_materialization(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision_counts = Counter(
        str(row["status"]) for row in payload.get("decision_states", [])
    )
    selections = payload.get("threshold_selections", [])
    selected_count = sum(row.get("selected_signal") is not None for row in selections)
    candidate_count = sum(
        len(row.get("signal_candidates", []))
        for row in payload.get("decision_states", [])
    )
    return {
        "structural_market_count": len(payload.get("structural_markets", [])),
        "decision_state_count": len(payload.get("decision_states", [])),
        "decision_status_counts": dict(sorted(decision_counts.items())),
        "signal_candidate_count": candidate_count,
        "threshold_selection_count": len(selections),
        "selected_signal_count": selected_count,
        "execution_scenario_count": len(payload.get("execution_scenarios", [])),
    }


def validate_materialization_artifact(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)
    path = repo / MATERIALIZATION_RELATIVE_PATH
    if not path.is_file():
        _fail(f"materialization missing: {path}")
    observed_hash = sha256_file(path)
    if observed_hash != EXPECTED_MATERIALIZATION_SHA256:
        _fail(
            "materialization SHA256 mismatch; "
            f"observed={observed_hash}, expected={EXPECTED_MATERIALIZATION_SHA256}"
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "kxbtcd_candidate_e_july10_outcome_blind_binding.v1":
        _fail("materialization schema mismatch")
    if payload.get("checkpoint_id") != "21N-S":
        _fail("materialization checkpoint mismatch")
    if payload.get("strategy_id") != STRATEGY_ID:
        _fail("strategy mismatch")
    if payload.get("source_counts") != EXPECTED_SOURCE_COUNTS:
        _fail("source counts mismatch")

    summary = summarize_materialization(payload)
    if summary["structural_market_count"] != 20:
        _fail("structural market count mismatch")
    if summary["decision_state_count"] != 120:
        _fail("decision state count mismatch")
    if summary["decision_status_counts"] != EXPECTED_DECISION_STATUS_COUNTS:
        _fail("decision status counts mismatch")
    if summary["signal_candidate_count"] != 0:
        _fail("signal candidates unexpectedly exist")
    if summary["threshold_selection_count"] != 20:
        _fail("threshold selection count mismatch")
    if summary["selected_signal_count"] != 0:
        _fail("a threshold unexpectedly selected a signal")
    if summary["execution_scenario_count"] != 0:
        _fail("execution scenarios unexpectedly exist")

    safety = payload.get("safety")
    if not isinstance(safety, Mapping):
        _fail("safety block missing")
    required_safety = {
        "outcomes_accessed": False,
        "strategy_pnl_calculated": False,
        "candidate_e_refit": False,
        "network_requests": 0,
        "predexon_paid_purchases": 0,
        "orders_placed": 0,
        "paper_broker": False,
        "demo_execution": False,
        "real_money_execution": False,
        "protected_reserve_accessed": False,
    }
    for key, expected in required_safety.items():
        if safety.get(key) != expected:
            _fail(f"safety invariant failed: {key}")
    return payload


def build_decision_book_failure_audit(repo_root: str | Path = ".") -> dict[str, Any]:
    """Reproduce the S-B decision-book classification from frozen outcome-blind inputs."""
    from .kxbtcd_candidate_e_july10_outcome_blind_binding import (
        PAID_TICKS_RELATIVE_PATH,
        build_structural_timelines,
        collect_paid_tickers,
        derive_structural_universe,
        iso_utc_to_epoch_ms,
        load_and_validate_btc_materialization,
        load_selected_paid_rows,
        validate_file_set_alignment,
    )

    repo = Path(repo_root)
    btc_rows = load_and_validate_btc_materialization(repo)
    paid_path = repo / PAID_TICKS_RELATIVE_PATH
    paid_tickers = collect_paid_tickers(paid_path)
    validate_file_set_alignment(repo_root=repo, paid_tickers=paid_tickers)

    structural = derive_structural_universe(paid_tickers)
    selected_tickers = [str(row["market_ticker"]) for row in structural]
    paid_rows = load_selected_paid_rows(paid_path, selected_tickers)
    timelines = build_structural_timelines(
        repo_root=repo,
        structural_rows=structural,
        paid_rows_by_ticker=paid_rows,
    )

    structural_by_event: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in structural:
        structural_by_event[str(row["event_ticker"])].append(row)

    overall: Counter[str] = Counter()
    by_event: dict[str, Counter[str]] = defaultdict(Counter)
    by_anchor: dict[int, Counter[str]] = defaultdict(Counter)
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    unavailable_gap_ms: list[int] = []

    for btc in btc_rows:
        event = str(btc["event_ticker"])
        ttc = int(btc["ttc_target_minutes"])
        decision_ms = iso_utc_to_epoch_ms(str(btc["decision_time_utc"]))

        for market in structural_by_event[event]:
            ticker = str(market["market_ticker"])
            role = str(market["structural_role"])
            timeline = timelines[ticker]
            segment = timeline.unique_segment_for_interval(decision_ms, decision_ms)

            if segment is None:
                status = "SOURCE_UNAVAILABLE_DECISION_TIMESTAMP"
                distances: list[int] = []
                for seg in timeline.segments:
                    if decision_ms < seg.start_timestamp_ms:
                        distances.append(seg.start_timestamp_ms - decision_ms)
                    elif decision_ms > seg.end_timestamp_ms:
                        distances.append(decision_ms - seg.end_timestamp_ms)
                    else:
                        distances.append(0)
                if distances:
                    unavailable_gap_ms.append(min(distances))
            else:
                state = segment.state_at(decision_ms)
                has_bid = bool(state.yes_bids)
                has_ask = bool(state.yes_asks)
                if not has_bid and not has_ask:
                    status = "EMPTY_BOTH_SIDES"
                elif not has_bid:
                    status = "MISSING_YES_BID"
                elif not has_ask:
                    status = "MISSING_YES_ASK"
                elif state.yes_bids[0].price > state.yes_asks[0].price:
                    status = "CROSSED_TWO_SIDED_BOOK"
                else:
                    status = "VALID_TWO_SIDED_BOOK"

            overall[status] += 1
            by_event[event][status] += 1
            by_anchor[ttc][status] += 1
            by_role[role][status] += 1

    for key in EXPECTED_REFINED_BOOK_COUNTS:
        overall.setdefault(key, 0)

    if dict(overall) != EXPECTED_REFINED_BOOK_COUNTS:
        _fail(
            "refined book counts mismatch; "
            f"observed={dict(overall)}, expected={EXPECTED_REFINED_BOOK_COUNTS}"
        )

    seconds = [value / 1000 for value in unavailable_gap_ms]
    if len(seconds) != EXPECTED_GAP_STATS["count"]:
        _fail("source-unavailable gap count mismatch")
    gap_stats = {
        "count": len(seconds),
        "min_seconds": f"{min(seconds):.3f}",
        "median_seconds": f"{median(seconds):.3f}",
        "max_seconds": f"{max(seconds):.3f}",
        "lte_1_second": sum(value <= 1000 for value in unavailable_gap_ms),
        "lte_10_seconds": sum(value <= 10000 for value in unavailable_gap_ms),
        "lte_60_seconds": sum(value <= 60000 for value in unavailable_gap_ms),
    }
    if gap_stats != EXPECTED_GAP_STATS:
        _fail(f"gap stats mismatch; observed={gap_stats}, expected={EXPECTED_GAP_STATS}")

    return {
        "overall": dict(sorted(overall.items())),
        "by_event": {
            event: dict(sorted(counts.items()))
            for event, counts in sorted(by_event.items())
        },
        "by_ttc_anchor": {
            str(ttc): dict(sorted(counts.items()))
            for ttc, counts in sorted(by_anchor.items(), reverse=True)
        },
        "by_structural_role": {
            role: dict(sorted(by_role[role].items()))
            for role in ("q10", "q30", "q50", "q70", "q90")
        },
        "source_unavailable_gap_stats": gap_stats,
    }


def build_closeout_document() -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "strategy_id": STRATEGY_ID,
        "parent_21n_s_a": {
            "checkpoint_commit": PARENT_CHECKPOINT_COMMIT,
            "receipt_commit": PARENT_RECEIPT_COMMIT,
            "binding_implementation_fingerprint": S_A_IMPLEMENTATION_FINGERPRINT,
        },
        "materialization": {
            "relative_path": MATERIALIZATION_RELATIVE_PATH.as_posix(),
            "sha256": EXPECTED_MATERIALIZATION_SHA256,
            "deterministic_rerun_sha256": EXPECTED_MATERIALIZATION_SHA256,
            "deterministic_rerun_match": True,
            "structural_market_count": 20,
            "decision_state_count": 120,
            "threshold_selection_count": 20,
            "execution_scenario_count": 0,
            "signal_candidate_count": 0,
            "decision_status_counts": EXPECTED_DECISION_STATUS_COUNTS,
        },
        "decision_book_failure_audit": {
            "overall": EXPECTED_REFINED_BOOK_COUNTS,
            "source_unavailable_gap_stats": EXPECTED_GAP_STATS,
            "crossed_book_count": 0,
            "valid_two_sided_book_count": 0,
        },
        "interpretation": {
            "evaluation_status": "NON_EVALUABLE_NO_VALID_TWO_SIDED_DECISION_STATE",
            "candidate_e_economic_result": "NOT_EVALUATED",
            "strategy_economic_result": "NOT_EVALUATED",
            "zero_execution_scenarios_means_zero_edge": False,
            "replay_normalization_failure_found": False,
            "settlement_outcomes_needed_for_this_sample": False,
            "reason": (
                "No frozen role-anchor state reached Candidate-E signal generation; "
                "therefore settlement labels cannot evaluate executable strategy economics."
            ),
            "threshold_or_strategy_tuning_authorized": False,
            "advancement_gate": "NONE_N_EQ_4_AND_ZERO_EVALUABLE_EXECUTION_STATES",
        },
        "next_phase": {
            "id": "21N-T",
            "name": "Prospective Read-Only Execution-Data Adequacy and Collection Design",
            "purpose": (
                "collect fresh synchronized full-ladder Kalshi books and BTC reference states "
                "at exact frozen anchors before any new economic evaluation"
            ),
            "authenticated_read_only_kalshi_websocket_permitted": True,
            "orders_demo_and_paper_execution_permitted": False,
            "candidate_e_refit_permitted": False,
            "july10_outcomes_should_remain_closed": True,
        },
        "safety": {
            "july10_outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "candidate_e_refit": False,
            "thresholds_changed": False,
            "strategy_rules_changed": False,
            "network_requests_during_materialization": 0,
            "new_predexon_purchases": 0,
            "orders_submitted": 0,
            "protected_reserve_accessed": False,
        },
    }
    document["result_closeout_fingerprint"] = canonical_fingerprint(document)
    return document


def validate_closeout_document(document: Mapping[str, Any]) -> None:
    expected = build_closeout_document()
    if dict(document) != expected:
        _fail(
            "result closeout document mismatch; "
            f"observed_fp={document.get('result_closeout_fingerprint')}, "
            f"expected_fp={expected['result_closeout_fingerprint']}"
        )


def validate_result_closeout(
    repo_root: str | Path = ".",
    *,
    recompute_book_audit: bool = False,
) -> Mapping[str, Any]:
    repo = Path(repo_root)
    validate_materialization_artifact(repo)
    closeout_path = repo / CLOSEOUT_RELATIVE_PATH
    if not closeout_path.is_file():
        _fail(f"result closeout missing: {closeout_path}")
    document = json.loads(closeout_path.read_text(encoding="utf-8"))
    validate_closeout_document(document)
    if recompute_book_audit:
        build_decision_book_failure_audit(repo)
    return document


__all__ = [
    "OutcomeBlindMaterializationCloseoutError",
    "SCHEMA_VERSION",
    "CHECKPOINT_ID",
    "EXPECTED_MATERIALIZATION_SHA256",
    "EXPECTED_REFINED_BOOK_COUNTS",
    "EXPECTED_GAP_STATS",
    "canonical_fingerprint",
    "summarize_materialization",
    "validate_materialization_artifact",
    "build_decision_book_failure_audit",
    "build_closeout_document",
    "validate_closeout_document",
    "validate_result_closeout",
]

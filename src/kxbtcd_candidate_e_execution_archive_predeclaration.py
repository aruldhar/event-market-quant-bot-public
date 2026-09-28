"""Checkpoint 21K-B1 reusable Candidate-E execution archive predeclaration.

Network-free. This module validates the frozen archive contract and can
recompute the exact 4,070-event / 20,236-market allow-list identity from the
already-exposed Candidate-E prediction artifacts.

It performs no API requests, no model fitting, no strategy P&L calculation,
and no execution.
"""
from __future__ import annotations

from pathlib import Path
import csv
import hashlib
import json
from typing import Any, Mapping

ARCHIVE_ID = "kxbtcd_candidate_e_reusable_execution_archive.v1"
CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
PARENT_STRATEGY_FINGERPRINT = "afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046"
EXPECTED_ALLOWLIST_FINGERPRINT = "85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1"
EXPECTED_ARCHIVE_FINGERPRINT = "4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea"
EXPECTED_EVENTS = 4070
EXPECTED_MARKETS = 20236
EXPECTED_ROWS = 118862

STAGE_SPECS = {
    "H1_OOF": ("data/derived/kxbtcd_candidate_e_h1_evaluation", "*_candidate_e_h1_oof_predictions.csv", 1070, 5334, 31656),
    "H2": ("data/derived/kxbtcd_candidate_e_h2_evaluation", "*_candidate_e_h2_predictions.csv", 750, 3750, 22354),
    "H3": ("data/derived/kxbtcd_candidate_e_h3_evaluation", "*_candidate_e_h3_predictions.csv", 750, 3750, 22409),
    "C1": ("data/derived/kxbtcd_candidate_e_c1_evaluation", "*_candidate_e_c1_predictions.csv", 500, 2491, 14887),
    "C2": ("data/derived/kxbtcd_candidate_e_c2_evaluation", "*_candidate_e_c2_predictions.csv", 500, 2441, 14007),
    "C3": ("data/derived/kxbtcd_candidate_e_c3_evaluation", "*_candidate_e_c3_predictions.csv", 500, 2470, 13549),
}

class ExecutionArchivePredeclarationError(RuntimeError):
    pass

def canonical_fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExecutionArchivePredeclarationError(f"JSON root must be object: {path}")
    return value

def recompute_allowlist(repository_root: str | Path = ".") -> tuple[list[dict[str, str]], dict[str, dict[str, int]]]:
    repo = Path(repository_root)
    allowlist: list[dict[str, str]] = []
    stats: dict[str, dict[str, int]] = {}
    all_events: set[str] = set()
    all_markets: set[str] = set()

    for stage, (root_text, pattern, expected_events, expected_markets, expected_rows) in STAGE_SPECS.items():
        root = repo / root_text
        matches = sorted(root.rglob(pattern))
        if len(matches) != 1:
            raise ExecutionArchivePredeclarationError(
                f"{stage} expected one prediction artifact, found {len(matches)}"
            )
        rows = 0
        events: set[str] = set()
        markets: set[str] = set()
        pairs: set[tuple[str, str]] = set()
        with matches[0].open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if (row.get("candidate_id") or "").strip() != CANDIDATE_ID:
                    continue
                rows += 1
                event = (row.get("event_ticker") or "").strip()
                market = (row.get("market_ticker") or "").strip()
                if not event or not market:
                    raise ExecutionArchivePredeclarationError(f"{stage} blank identity")
                events.add(event)
                markets.add(market)
                pairs.add((event, market))
        observed = (len(events), len(markets), rows)
        expected = (expected_events, expected_markets, expected_rows)
        if observed != expected:
            raise ExecutionArchivePredeclarationError(
                f"{stage} counts changed: observed={observed}, expected={expected}"
            )
        if all_events & events:
            raise ExecutionArchivePredeclarationError(f"{stage} cross-stage event overlap")
        if all_markets & markets:
            raise ExecutionArchivePredeclarationError(f"{stage} cross-stage market overlap")
        all_events.update(events)
        all_markets.update(markets)
        stats[stage] = {"events": len(events), "markets": len(markets), "rows": rows}
        for event, market in sorted(pairs):
            allowlist.append({
                "stage": stage,
                "event_ticker": event,
                "market_ticker": market,
            })

    if len(all_events) != EXPECTED_EVENTS or len(all_markets) != EXPECTED_MARKETS:
        raise ExecutionArchivePredeclarationError("aggregate allowlist counts changed")
    if sum(v["rows"] for v in stats.values()) != EXPECTED_ROWS:
        raise ExecutionArchivePredeclarationError("aggregate prediction row count changed")
    return allowlist, stats

def validate_predeclaration(
    config_path: str | Path = "configs/kxbtcd_candidate_e_execution_archive_v1.json",
    *,
    repository_root: str | Path = ".",
    verify_allowlist: bool = True,
) -> str:
    repo = Path(repository_root)
    path = Path(config_path)
    if not path.is_absolute():
        path = repo / path
    doc = read_json(path)
    if doc.get("archive_id") != ARCHIVE_ID:
        raise ExecutionArchivePredeclarationError("archive_id changed")
    if doc.get("parent_strategy", {}).get("strategy_predeclaration_fingerprint") != PARENT_STRATEGY_FINGERPRINT:
        raise ExecutionArchivePredeclarationError("parent strategy fingerprint changed")
    stored = doc.get("archive_predeclaration_fingerprint")
    if stored != EXPECTED_ARCHIVE_FINGERPRINT:
        raise ExecutionArchivePredeclarationError("archive fingerprint field changed")
    payload = {k: v for k, v in doc.items() if k != "archive_predeclaration_fingerprint"}
    if canonical_fingerprint(payload) != EXPECTED_ARCHIVE_FINGERPRINT:
        raise ExecutionArchivePredeclarationError("archive canonical fingerprint mismatch")
    allow = doc.get("allowlist", {})
    if (
        allow.get("unique_event_count"),
        allow.get("unique_market_count"),
        allow.get("prediction_row_count"),
        allow.get("allowlist_fingerprint"),
    ) != (EXPECTED_EVENTS, EXPECTED_MARKETS, EXPECTED_ROWS, EXPECTED_ALLOWLIST_FINGERPRINT):
        raise ExecutionArchivePredeclarationError("allowlist contract changed")
    safety = doc.get("safety", {})
    if safety != {
        "read_only": True,
        "orders": False,
        "cancellations": False,
        "transfers": False,
        "paper_broker": False,
        "demo_execution": False,
        "real_money_execution": False,
    }:
        raise ExecutionArchivePredeclarationError("safety contract changed")
    if doc.get("collection_scope", {}).get("strategy_pnl_scoring_authorized") is not False:
        raise ExecutionArchivePredeclarationError("P&L scoring became authorized")
    if doc.get("reserve_policy", {}).get("reserve_access_allowed") is not False:
        raise ExecutionArchivePredeclarationError("reserve access became authorized")
    if verify_allowlist:
        rows, _ = recompute_allowlist(repo)
        observed_fp = canonical_fingerprint(rows)
        if observed_fp != EXPECTED_ALLOWLIST_FINGERPRINT:
            raise ExecutionArchivePredeclarationError(
                f"allowlist fingerprint mismatch: {observed_fp}"
            )
    return EXPECTED_ARCHIVE_FINGERPRINT

#!/usr/bin/env python3
"""Validate the frozen Checkpoint-21N-C development FAIL closeout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_EVAL = "8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc"
CONFIG = Path("configs/kxbtcd_candidate_e_quoted_entry_hold_v1_development_result_closeout.json")
FILES = {
    "evaluation": "development_economic_evaluation.json",
    "event_pnl_scenarios": "development_event_pnl_scenarios.csv",
    "threshold_scores": "development_threshold_scores.csv",
    "receipt": "development_economic_receipt.json",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def no_selected_threshold(value: object) -> bool:
    """Canonical 21N-B encodes no winner as either JSON null or empty text."""
    return value in (None, "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(CONFIG))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent
    config_path = repo / args.config
    doc = json.loads(config_path.read_text(encoding="utf-8"))
    assert doc["schema_version"] == "kxbtcd_candidate_e_quoted_entry_hold_v1_development_result_closeout.v1"
    assert doc["development_evaluation_fingerprint"] == EXPECTED_EVAL
    assert doc["status"] == "FAIL_NO_THRESHOLD"
    assert doc["development_passed"] is False
    assert no_selected_threshold(doc["selected_threshold"])
    assert doc["scientific_consequence"]["quoted_entry_hold_v1_rejected"] is True
    assert doc["scientific_consequence"]["c1_c2_strategy_pnl_authorized"] is False
    assert doc["safety"]["c1_c2_strategy_pnl_accessed"] is False
    assert doc["safety"]["c3_accessed"] is False
    assert doc["safety"]["protected_reserve_accessed"] is False
    assert doc["safety"]["orders_submitted"] is False
    supplied = doc["development_result_closeout_fingerprint"]
    copy = dict(doc)
    copy.pop("development_result_closeout_fingerprint")
    assert supplied == canonical_sha256(copy)

    result_dir = repo / doc["result_directory"]
    hashes = doc["result_file_sha256s"]
    for key, filename in FILES.items():
        path = result_dir / filename
        assert path.is_file(), f"missing frozen local result artifact: {path}"
        assert sha256_file(path) == hashes[key], f"hash mismatch: {key}"
    evaluation = json.loads((result_dir / FILES["evaluation"]).read_text(encoding="utf-8"))
    receipt = json.loads((result_dir / FILES["receipt"]).read_text(encoding="utf-8"))
    assert evaluation["evaluation_fingerprint"] == EXPECTED_EVAL
    assert receipt["evaluation_fingerprint"] == EXPECTED_EVAL
    assert evaluation["selection"]["status"] == "FAIL_NO_THRESHOLD"
    assert no_selected_threshold(evaluation["selection"]["selected_threshold"])
    three = evaluation["threshold_results"]["0.03"]
    assert three["gate_conditions"]["newest_block_positive"] is False
    assert three["gate_conditions"]["h3_positive"] is False
    assert three["development_gate_pass"] is False
    print("Checkpoint 21N-C development result validation: PASS")
    print(f"evaluation_fingerprint={EXPECTED_EVAL}")
    print(f"development_result_closeout_fingerprint={supplied}")
    print("status=FAIL_NO_THRESHOLD")
    print("selected_threshold=NONE")
    print("c1_c2_strategy_pnl_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

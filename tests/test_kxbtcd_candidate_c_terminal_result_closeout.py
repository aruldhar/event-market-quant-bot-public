from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_c_terminal_result_closeout import (
    DOC_PATHS,
    FAILED_TERMINAL_RUN_ID,
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_FINAL_MODEL_FINGERPRINT,
    FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
    FROZEN_SPLIT_FINGERPRINT,
    FROZEN_TERMINAL_EVALUATION_FINGERPRINT,
    FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT,
    MARKER,
    TERMINAL_SUMMARY_FIELDS,
    TerminalResultCloseoutError,
    apply_documentation,
    validate_terminal_result,
)


def canonical_sha(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def make_repo(tmp_path: Path):
    for path in DOC_PATHS:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {path.name}\n", encoding="utf-8")

    summary = {
        "schema_version": "kxbtcd_candidate_c_terminal_summary.v1",
        "candidate_id": "kxbtcd_market_spread_interaction_logistic.v1",
        "terminal_evaluation_fingerprint": FROZEN_TERMINAL_EVALUATION_FINGERPRINT,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "locked_test_event_count": "64",
        "locked_test_row_count": "1014",
        "locked_test_market_label_count": "304",
        "raw_midpoint_event_weighted_log_loss": "0.052191564366640519",
        "candidate_c_event_weighted_log_loss": "0.068502780828836138",
        "delta_log_loss_raw_minus_candidate_c": "-0.016311216462195618",
        "raw_midpoint_event_weighted_brier": "0.014139546080841911",
        "candidate_c_event_weighted_brier": "0.014602932515903819",
        "delta_brier_raw_minus_candidate_c": "-0.000463386435061908",
        "primary_rule": (
            "candidate_c_event_weighted_log_loss_strictly_less_than_"
            "raw_midpoint_event_weighted_log_loss"
        ),
        "tie_rule": "fail",
        "terminal_gate_passed": "false",
        "locked_test_permanently_exposed": "true",
        "model_refit_performed": "false",
        "model_retuned": "false",
        "model_recalibrated": "false",
        "execution_enabled": "false",
        "orders_placed": "0",
    }
    assert set(summary) == set(TERMINAL_SUMMARY_FIELDS)
    result_fp = canonical_sha(summary)

    result = dict(summary)
    result.update(
        {
            "terminal_result_fingerprint": result_fp,
            "transport_amendment_fingerprint": FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT,
            "live_market_requests": 295,
            "historical_fallback_requests": 103,
            "new_market_labels": 295,
            "resume_recovered_outcomes": 9,
            "resume_source_manifest": (
                f"data/manifests/2026/08/15/{FAILED_TERMINAL_RUN_ID}.json"
            ),
            "authentication_used": False,
            "model_refit_performed": False,
            "model_retuned": False,
            "model_recalibrated": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
    )
    run_id = "collect_kxbtcd_candidate_c_locked_test_20260815T225546640797Z_54081035"
    manifest = {
        "schema_version": "collection_run_manifest.v2",
        "run_id": run_id,
        "collector": {"name": "collect_kxbtcd_candidate_c_locked_test"},
        "status": "completed",
        "arguments": {
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
            "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
            "terminal_evaluation_fingerprint": FROZEN_TERMINAL_EVALUATION_FINGERPRINT,
            "transport_amendment_fingerprint": FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT,
            "transport_repair_mode": True,
            "partition_scope": "locked_test_only",
            "primary_metric": "event_weighted_log_loss",
            "tie_rule": "fail",
            "resume_source_manifest": (
                f"data/manifests/2026/08/15/{FAILED_TERMINAL_RUN_ID}.json"
            ),
        },
        "result": result,
    }
    manifest_path = tmp_path / "terminal.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    attempt_path = (
        tmp_path
        / "data/analysis/kxbtcd_candidate_c_terminal_evaluation/terminal_test_attempt.json"
    )
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    attempt_path.write_text(
        json.dumps(
            {
                "status": "terminal_evaluation_completed",
                "locked_test_permanently_exposed": True,
                "terminal_evaluation_fingerprint": FROZEN_TERMINAL_EVALUATION_FINGERPRINT,
                "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
                "result_fingerprint": result_fp,
                "latest_manifest": f"data/manifests/2026/08/15/{run_id}.json",
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_validate_terminal_fail_and_apply_docs_idempotently(tmp_path):
    manifest = make_repo(tmp_path)
    result = validate_terminal_result(manifest, repository_root=tmp_path)
    assert result.gate_passed is False
    assert result.recovered_labels == 9
    assert result.new_labels == 295

    updated = apply_documentation(result, repository_root=tmp_path)
    assert set(updated) == set(DOC_PATHS)
    for path in DOC_PATHS:
        assert MARKER in (tmp_path / path).read_text(encoding="utf-8")

    assert apply_documentation(result, repository_root=tmp_path) == ()


def test_rejects_attempt_to_record_terminal_pass(tmp_path):
    manifest = make_repo(tmp_path)
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["result"]["terminal_gate_passed"] = "true"
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(TerminalResultCloseoutError):
        validate_terminal_result(manifest, repository_root=tmp_path)

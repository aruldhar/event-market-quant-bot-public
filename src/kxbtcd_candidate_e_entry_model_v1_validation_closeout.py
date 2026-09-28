from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "kxbtcd_candidate_e_entry_residual_logistic.v1"
CHECKPOINT_ID = "21M"
CLOSEOUT_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_result_closeout.v1"

PARENT_COMMIT = "953ac548eb9d881ea23c77fcf37f9d0723ac665d"
ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT = (
    "8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7"
)
VALIDATION_RESUME_REPAIR_FINGERPRINT = (
    "fee1063a637c99749e47d67bbb553a480d3e72037be1cb9015b26b67f2275aed"
)
DEVELOPMENT_FREEZE_FINGERPRINT = (
    "a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e"
)
VALIDATION_PREPARATION_FINGERPRINT = (
    "25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22"
)
VALIDATION_EVALUATION_FINGERPRINT = (
    "15a6557736204ca58039906434f8b7e83bca719f14cd0a3b4c9b9094e42ce033"
)
VALIDATION_RECEIPT_FINGERPRINT = (
    "5e37a7abab6065414be00761ac79e09e853e587ab3ccf153e9f5a74081b11e2a"
)
SELECTED_LAMBDA = 0.01

EXPECTED_METRICS = {
    "validation_events": 1000,
    "validation_rows": 28894,
    "candidate_e_event_equal_log_loss": 0.0518981214127418,
    "model2_event_equal_log_loss": 0.051982434232278454,
    "candidate_e_minus_model2_log_loss": -8.431281953665687e-05,
    "candidate_e_event_equal_brier": 0.015171565220600291,
    "model2_event_equal_brier": 0.01519915292120419,
    "candidate_e_minus_model2_brier": -2.7587700603898604e-05,
    "median_event_candidate_e_minus_model2_log_loss": 2.3452135462756008e-05,
    "block_log_loss_win_count": 1,
    "newest_block_log_loss_win": False,
    "validation_passed": False,
}

RESULT_FILES = {
    "scored_rows": "validation_scored_rows.csv",
    "event_scores": "validation_event_scores.csv",
    "block_scores": "validation_block_scores.csv",
    "summary": "validation_summary.json",
    "receipt": "validation_receipt.json",
}


class CloseoutError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise CloseoutError(message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _error(f"expected JSON object: {path}")
    return value


def write_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(target)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _same_float(actual: Any, expected: float, field: str) -> None:
    try:
        number = float(actual)
    except (TypeError, ValueError) as exc:
        raise CloseoutError(f"{field} is not numeric") from exc
    if not math.isclose(number, expected, rel_tol=0.0, abs_tol=0.0):
        _error(f"{field} changed: {number!r} != {expected!r}")


def validate_summary(summary: Mapping[str, Any]) -> None:
    if summary.get("model_id") != MODEL_ID:
        _error("validation summary model id changed")
    if summary.get("development_freeze_fingerprint") != DEVELOPMENT_FREEZE_FINGERPRINT:
        _error("development freeze fingerprint changed")
    if summary.get("validation_preparation_fingerprint") != VALIDATION_PREPARATION_FINGERPRINT:
        _error("validation preparation fingerprint changed")
    if (
        summary.get("validation_implementation_fingerprint")
        != ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT
    ):
        _error("validation implementation fingerprint changed")
    if summary.get("validation_evaluation_fingerprint") != VALIDATION_EVALUATION_FINGERPRINT:
        _error("validation evaluation fingerprint changed")
    _same_float(summary.get("selected_lambda"), SELECTED_LAMBDA, "selected_lambda")

    for field, expected in EXPECTED_METRICS.items():
        actual = summary.get(field)
        if isinstance(expected, bool):
            if actual is not expected:
                _error(f"{field} changed")
        elif isinstance(expected, int):
            if int(actual) != expected:
                _error(f"{field} changed")
        else:
            _same_float(actual, expected, field)

    conditions = summary.get("gate_conditions")
    if not isinstance(conditions, Mapping):
        _error("validation gate conditions missing")
    expected_conditions = {
        "pooled_model2_log_loss_strictly_better": False,
        "pooled_model2_brier_not_worse": False,
        "at_least_four_of_five_block_log_loss_wins": False,
        "newest_block_log_loss_win": False,
        "median_event_candidate_e_minus_model2_log_loss_positive": True,
    }
    if dict(conditions) != expected_conditions:
        _error("validation gate-condition pattern changed")

    for field in (
        "profitability_claim",
        "strategy_v1_pnl_calculated",
        "c3_opened_for_model2",
        "protected_reserve_accessed",
        "execution_enabled",
    ):
        if summary.get(field) is not False:
            _error(f"summary safety flag {field} is not false")


def validate_receipt(
    receipt: Mapping[str, Any],
    *,
    result_dir: str | Path,
) -> None:
    if receipt.get("model_id") != MODEL_ID:
        _error("validation receipt model id changed")
    if (
        receipt.get("validation_implementation_fingerprint")
        != ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT
    ):
        _error("receipt implementation fingerprint changed")
    if receipt.get("validation_preparation_fingerprint") != VALIDATION_PREPARATION_FINGERPRINT:
        _error("receipt preparation fingerprint changed")
    if receipt.get("development_freeze_fingerprint") != DEVELOPMENT_FREEZE_FINGERPRINT:
        _error("receipt development fingerprint changed")
    if receipt.get("validation_evaluation_fingerprint") != VALIDATION_EVALUATION_FINGERPRINT:
        _error("receipt evaluation fingerprint changed")
    if receipt.get("validation_receipt_fingerprint") != VALIDATION_RECEIPT_FINGERPRINT:
        _error("receipt fingerprint changed")
    if receipt.get("validation_passed") is not False:
        _error("receipt no longer records validation FAIL")

    for field, expected in (
        ("c1_c2_outcomes_opened_for_model2", True),
        ("c3_opened_for_model2", False),
        ("protected_reserve_accessed", False),
        ("strategy_v1_pnl_calculated", False),
        ("execution_enabled", False),
    ):
        if receipt.get(field) is not expected:
            _error(f"receipt safety/exposure flag {field} changed")

    hashes = receipt.get("output_sha256s")
    if not isinstance(hashes, Mapping):
        _error("receipt output hash map missing")
    directory = Path(result_dir)
    expected_map = {
        "scored_rows": sha256_file(directory / RESULT_FILES["scored_rows"]),
        "event_scores": sha256_file(directory / RESULT_FILES["event_scores"]),
        "block_scores": sha256_file(directory / RESULT_FILES["block_scores"]),
        "summary": sha256_file(directory / RESULT_FILES["summary"]),
    }
    if dict(hashes) != dict(sorted(expected_map.items())):
        _error("receipt output hashes do not match result files")


def validate_attempt(
    attempt: Mapping[str, Any],
    *,
    result_dir: str | Path,
) -> None:
    if attempt.get("model_id") != MODEL_ID:
        _error("attempt model id changed")
    if attempt.get("status") != "COMPLETE":
        _error("attempt is not COMPLETE")
    if attempt.get("c1_c2_outcomes_opened_for_model2") is not True:
        _error("attempt does not preserve C1/C2 exposure")
    if (
        attempt.get("validation_implementation_fingerprint")
        != ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT
    ):
        _error("attempt implementation fingerprint changed")
    if attempt.get("validation_preparation_fingerprint") != VALIDATION_PREPARATION_FINGERPRINT:
        _error("attempt preparation fingerprint changed")
    if attempt.get("validation_evaluation_fingerprint") != VALIDATION_EVALUATION_FINGERPRINT:
        _error("attempt evaluation fingerprint changed")
    if attempt.get("validation_receipt_fingerprint") != VALIDATION_RECEIPT_FINGERPRINT:
        _error("attempt receipt fingerprint changed")
    if attempt.get("validation_passed") is not False:
        _error("attempt no longer records validation FAIL")
    if Path(str(attempt.get("output_dir", ""))).resolve() != Path(result_dir).resolve():
        _error("attempt output directory changed")
    for field in (
        "c3_opened_for_model2",
        "protected_reserve_accessed",
        "strategy_v1_pnl_calculated",
        "execution_enabled",
    ):
        if attempt.get(field) is not False:
            _error(f"attempt safety flag {field} is not false")


def validate_resume_repair_freeze(document: Mapping[str, Any]) -> None:
    if (
        document.get("validation_resume_repair_fingerprint")
        != VALIDATION_RESUME_REPAIR_FINGERPRINT
    ):
        _error("resume-repair fingerprint changed")
    if (
        document.get("original_validation_implementation_fingerprint")
        != ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT
    ):
        _error("resume-repair original implementation fingerprint changed")
    if document.get("c1_c2_outcomes_already_opened_for_model2") is not True:
        _error("resume-repair no longer records C1/C2 exposure")
    for field in (
        "c3_opened_for_model2",
        "protected_reserve_accessed",
        "strategy_v1_pnl_calculated",
        "execution_enabled",
    ):
        if document.get(field) is not False:
            _error(f"resume-repair safety flag {field} is not false")


def build_closeout(
    *,
    result_dir: str | Path,
    attempt_path: str | Path,
    implementation_freeze_path: str | Path,
) -> dict[str, Any]:
    directory = Path(result_dir)
    missing = [
        name for name in RESULT_FILES.values()
        if not (directory / name).is_file()
    ]
    if missing:
        _error(f"validation result files missing: {missing}")

    summary = read_json(directory / RESULT_FILES["summary"])
    receipt = read_json(directory / RESULT_FILES["receipt"])
    attempt = read_json(attempt_path)
    repair = read_json(implementation_freeze_path)

    validate_summary(summary)
    validate_receipt(receipt, result_dir=directory)
    validate_attempt(attempt, result_dir=directory)
    validate_resume_repair_freeze(repair)

    result_hashes = {
        key: sha256_file(directory / name)
        for key, name in RESULT_FILES.items()
    }

    payload: dict[str, Any] = {
        "schema_version": CLOSEOUT_SCHEMA,
        "checkpoint_id": CHECKPOINT_ID,
        "model_id": MODEL_ID,
        "closeout_parent_commit": PARENT_COMMIT,
        "status": "REJECTED_VALIDATION_FAIL",
        "selected_lambda": SELECTED_LAMBDA,
        "development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "validation_preparation_fingerprint": VALIDATION_PREPARATION_FINGERPRINT,
        "original_validation_implementation_fingerprint":
            ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT,
        "validation_resume_repair_fingerprint":
            VALIDATION_RESUME_REPAIR_FINGERPRINT,
        "validation_evaluation_fingerprint": VALIDATION_EVALUATION_FINGERPRINT,
        "validation_receipt_fingerprint": VALIDATION_RECEIPT_FINGERPRINT,
        "metrics": {
            field: summary[field]
            for field in (
                "validation_events",
                "validation_rows",
                "candidate_e_event_equal_log_loss",
                "model2_event_equal_log_loss",
                "candidate_e_minus_model2_log_loss",
                "candidate_e_event_equal_brier",
                "model2_event_equal_brier",
                "candidate_e_minus_model2_brier",
                "median_event_candidate_e_minus_model2_log_loss",
                "block_log_loss_win_count",
                "newest_block",
                "newest_block_log_loss_win",
            )
        },
        "gate_conditions": dict(summary["gate_conditions"]),
        "validation_passed": False,
        "result_file_sha256s": dict(sorted(result_hashes.items())),
        "attempt_sha256": sha256_file(attempt_path),
        "implementation_freeze_sha256": sha256_file(implementation_freeze_path),
        "receipt_source_sha256s": dict(sorted(receipt["source_sha256s"].items())),
        "receipt_output_sha256s": dict(sorted(receipt["output_sha256s"].items())),
        "scientific_consequence": {
            "model2_v1_rejected": True,
            "retune_on_c1_c2_prohibited": True,
            "rescore_on_c1_c2_prohibited": True,
            "c3_remains_sealed_for_model2_v1": True,
            "successor_requires_separate_predeclaration": True,
        },
        "c1_c2_outcomes_opened_for_model2": True,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "strategy_v1_pnl_calculated": False,
        "execution_enabled": False,
        "profitability_claim": False,
    }
    payload["validation_result_closeout_fingerprint"] = canonical_sha256(payload)
    return payload


def validate_closeout(
    document: Mapping[str, Any],
    *,
    result_dir: str | Path,
    attempt_path: str | Path,
    implementation_freeze_path: str | Path,
) -> None:
    expected = build_closeout(
        result_dir=result_dir,
        attempt_path=attempt_path,
        implementation_freeze_path=implementation_freeze_path,
    )
    if dict(document) != expected:
        _error("validation result closeout differs from deterministic derivation")

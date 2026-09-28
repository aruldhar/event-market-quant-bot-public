from __future__ import annotations

import pytest

import src.kxbtcd_candidate_e_entry_model_v1_validation as module


def _minimal_preparation_freeze() -> dict:
    return {
        "schema_version":
            "kxbtcd_candidate_e_entry_model_v1_validation_preparation_freeze.v1",
        "model_id": module.MODEL_ID,
        "validation_preparation_fingerprint":
            module.VALIDATION_PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": module.FEATURE_ROWS_FINGERPRINT,
        "validation_offset_rows_fingerprint": module.OFFSET_ROWS_FINGERPRINT,
        "validation_event_map_fingerprint": module.EVENT_MAP_FINGERPRINT,
        "candidate_probability_endpoint_rows": module.EXPECTED_ENDPOINT_ROWS,
        "candidate_e_baseline": {
            "historical_prediction_csv_rows_read": False,
        },
        "c1_c2_outcome_rows_read_for_model2": False,
        "validation_scores_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "strategy_v1_pnl_calculated": False,
        "execution_enabled": False,
    }


def test_preparation_validator_reads_nested_historical_prediction_flag():
    document = _minimal_preparation_freeze()
    assert "historical_prediction_csv_rows_read" not in document
    module.validate_preparation_freeze(document)


def test_preparation_validator_rejects_nested_true():
    document = _minimal_preparation_freeze()
    document["candidate_e_baseline"]["historical_prediction_csv_rows_read"] = True
    with pytest.raises(module.ValidationEvaluationError):
        module.validate_preparation_freeze(document)


def test_preparation_validator_rejects_missing_candidate_baseline():
    document = _minimal_preparation_freeze()
    del document["candidate_e_baseline"]
    with pytest.raises(module.ValidationEvaluationError):
        module.validate_preparation_freeze(document)


def _repaired_impl_hashes():
    values = dict(module.ORIGINAL_IMPLEMENTATION_SHA256S)
    values["src/kxbtcd_candidate_e_entry_model_v1_validation.py"] = "a" * 64
    return values


def test_resume_repair_allows_only_validation_runtime_to_change():
    document = module.build_validation_resume_repair_freeze(
        implementation_sha256s=_repaired_impl_hashes(),
        dependency_sha256s=module.ORIGINAL_DEPENDENCY_SHA256S,
    )
    assert (
        document["validation_implementation_fingerprint"]
        == module.ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT
    )
    assert document["repair_scope"]["model_formula_changed"] is False
    assert document["attempt_resume_contract"]["fresh_attempt_prohibited"] is True


def test_resume_repair_rejects_other_implementation_change():
    hashes = _repaired_impl_hashes()
    hashes["evaluate_kxbtcd_candidate_e_entry_model_v1_validation.py"] = "b" * 64
    with pytest.raises(module.ValidationEvaluationError):
        module.build_validation_resume_repair_freeze(
            implementation_sha256s=hashes,
            dependency_sha256s=module.ORIGINAL_DEPENDENCY_SHA256S,
        )


def test_resume_repair_rejects_dependency_change():
    dependencies = dict(module.ORIGINAL_DEPENDENCY_SHA256S)
    dependencies["src/kxbtcd_candidate_e_entry_model_v1.py"] = "c" * 64
    with pytest.raises(module.ValidationEvaluationError):
        module.build_validation_resume_repair_freeze(
            implementation_sha256s=_repaired_impl_hashes(),
            dependency_sha256s=dependencies,
        )


def test_resume_repair_document_validates_deterministically():
    hashes = _repaired_impl_hashes()
    document = module.build_validation_resume_repair_freeze(
        implementation_sha256s=hashes,
        dependency_sha256s=module.ORIGINAL_DEPENDENCY_SHA256S,
    )
    module.validate_implementation_freeze_document(
        document,
        implementation_sha256s=hashes,
        dependency_sha256s=module.ORIGINAL_DEPENDENCY_SHA256S,
    )


def test_original_freeze_contract_still_derives_original_fingerprint():
    original = module.build_implementation_freeze(
        implementation_sha256s=module.ORIGINAL_IMPLEMENTATION_SHA256S,
        dependency_sha256s=module.ORIGINAL_DEPENDENCY_SHA256S,
    )
    assert (
        original["validation_implementation_fingerprint"]
        == module.ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT
    )

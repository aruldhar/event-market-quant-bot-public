from __future__ import annotations

from pathlib import Path

import pytest

import src.kxbtcd_candidate_e_entry_model_v1_development as dev
from src.kxbtcd_candidate_e_entry_model_v1 import MODEL_ID
from src.kxbtcd_candidate_e_entry_model_v1_materialization import (
    FEATURE_FIELDS,
    FREEZE_SCHEMA_VERSION,
)


def _freeze() -> dict:
    return {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "model_id": MODEL_ID,
        "preparation_fingerprint": dev.EXPECTED_PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": dev.EXPECTED_FEATURE_ROWS_FINGERPRINT,
        "development_event_map_fingerprint": dev.EXPECTED_EVENT_MAP_FINGERPRINT,
        "outcomes_in_feature_rows": False,
        "strategy_v1_pnl_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "execution_enabled": False,
        "prepared_output_sha256s": {"feature_rows": "feature-hash"},
        "source_file_sha256s": {
            "h1_predictions": "h1-hash",
            "h2_predictions": "h2-hash",
            "h3_predictions": "h3-hash",
        },
        "implementation_sha256s": {
            "src/kxbtcd_candidate_e_entry_model_v1.py": dev.PREPARATION_FROZEN_CORE_SHA256,
        },
    }


def _feature_row() -> dict[str, str]:
    return {field: "placeholder" for field in FEATURE_FIELDS}


def _paths(tmp_path: Path) -> tuple[Path, dict[str, Path], Path]:
    feature = tmp_path / "features.csv"
    h1 = tmp_path / "h1.csv"
    h2 = tmp_path / "h2.csv"
    h3 = tmp_path / "h3.csv"
    core = tmp_path / "src" / "kxbtcd_candidate_e_entry_model_v1.py"
    core.parent.mkdir(parents=True)
    for path in (feature, h1, h2, h3, core):
        path.write_text("x\n", encoding="utf-8")
    return feature, {"H1_OOF": h1, "H2": h2, "H3": h3}, tmp_path


def _install_nonhash_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "validate_feature_rows", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        dev,
        "canonical_rows_fingerprint",
        lambda rows: dev.EXPECTED_FEATURE_ROWS_FINGERPRINT,
    )


def test_hash_chain_requires_original_freeze_and_exact_repaired_current_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    feature, labels, repo_root = _paths(tmp_path)
    _install_nonhash_stubs(monkeypatch)

    hashes = {
        str(feature): "feature-hash",
        str(labels["H1_OOF"]): "h1-hash",
        str(labels["H2"]): "h2-hash",
        str(labels["H3"]): "h3-hash",
        str(repo_root / "src" / "kxbtcd_candidate_e_entry_model_v1.py"):
            dev.ACCEPTED_POST_OUTCOME_CORE_SHA256,
    }
    monkeypatch.setattr(dev, "sha256_file", lambda path: hashes[str(Path(path))])

    dev.validate_preparation_binding(
        [_feature_row()],
        _freeze(),
        feature_rows_path=feature,
        label_source_paths=labels,
        repo_root=repo_root,
    )


def test_hash_chain_rejects_rewritten_preparation_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    feature, labels, repo_root = _paths(tmp_path)
    _install_nonhash_stubs(monkeypatch)

    freeze = _freeze()
    freeze["implementation_sha256s"]["src/kxbtcd_candidate_e_entry_model_v1.py"] = (
        dev.ACCEPTED_POST_OUTCOME_CORE_SHA256
    )

    hashes = {
        str(feature): "feature-hash",
        str(labels["H1_OOF"]): "h1-hash",
        str(labels["H2"]): "h2-hash",
        str(labels["H3"]): "h3-hash",
        str(repo_root / "src" / "kxbtcd_candidate_e_entry_model_v1.py"):
            dev.ACCEPTED_POST_OUTCOME_CORE_SHA256,
    }
    monkeypatch.setattr(dev, "sha256_file", lambda path: hashes[str(Path(path))])

    with pytest.raises(
        dev.CandidateEEntryDevelopmentError,
        match="original accepted pre-outcome hash",
    ):
        dev.validate_preparation_binding(
            [_feature_row()],
            freeze,
            feature_rows_path=feature,
            label_source_paths=labels,
            repo_root=repo_root,
        )


def test_hash_chain_rejects_any_unapproved_future_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    feature, labels, repo_root = _paths(tmp_path)
    _install_nonhash_stubs(monkeypatch)

    hashes = {
        str(feature): "feature-hash",
        str(labels["H1_OOF"]): "h1-hash",
        str(labels["H2"]): "h2-hash",
        str(labels["H3"]): "h3-hash",
        str(repo_root / "src" / "kxbtcd_candidate_e_entry_model_v1.py"):
            "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    }
    monkeypatch.setattr(dev, "sha256_file", lambda path: hashes[str(Path(path))])

    with pytest.raises(
        dev.CandidateEEntryDevelopmentError,
        match="accepted D-021M-05 repaired implementation",
    ):
        dev.validate_preparation_binding(
            [_feature_row()],
            _freeze(),
            feature_rows_path=feature,
            label_source_paths=labels,
            repo_root=repo_root,
        )

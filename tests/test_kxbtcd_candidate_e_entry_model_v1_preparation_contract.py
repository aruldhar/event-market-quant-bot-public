from __future__ import annotations

import json
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1 import (
    MODEL_ID,
    build_development_event_map,
    canonical_rows_fingerprint,
)
from src.kxbtcd_candidate_e_entry_model_v1_materialization import (
    EVENT_MAP_FIELDS,
    FEATURE_FIELDS,
    build_preparation_freeze,
    read_csv,
    sha256_file,
    write_csv,
)


def _rows():
    common = {
        "schema_version": "kxbtcd_candidate_e_entry_model_v1_feature_row.v1",
        "model_id": MODEL_ID,
        "structural_role": "q50",
        "ttc_target_minutes": 55,
        "candidate_probability": 0.5,
        "r_5m": 1.0,
        "spread_t": 0.02,
        "mid_move_1m": 0.01,
        "spread_change_1m": 0.001,
        "bid_range_1m": 0.03,
        "ask_range_1m": 0.04,
        "log1p_volume_1m": 1.0,
        "log1p_open_interest": 2.0,
        "log1p_trade_count_5m": 0.5,
        "log1p_contracts_5m": 0.8,
        "taker_imbalance_5m": 0.1,
    }
    result = []
    for i, (stage, date) in enumerate((
        ("H1_OOF", "2025-01-01T00:00:00Z"),
        ("H2", "2025-01-02T00:00:00Z"),
        ("H3", "2025-01-03T00:00:00Z"),
    )):
        result.append({
            **common,
            "stage": stage,
            "state_id": f"s{i}",
            "event_ticker": f"E{i}",
            "event_close_time_utc": date,
            "market_ticker": f"M{i}",
            "decision_time_utc": date,
            "r_5m": 1.0 + i,
        })
    return result


def test_preparation_freeze_binds_source_and_implementation_hashes_without_outcomes(tmp_path: Path):
    rows = _rows()
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    impl = tmp_path / "impl.py"
    impl.write_text("x = 1\n", encoding="utf-8")
    freeze = build_preparation_freeze(
        rows,
        event_map,
        source_files={"synthetic": source},
        implementation_sha256s={"impl.py": __import__("hashlib").sha256(impl.read_bytes()).hexdigest()},
        enforce_frozen_counts=False,
    )
    assert freeze["model_id"] == MODEL_ID
    assert freeze["outcomes_in_feature_rows"] is False
    assert freeze["strategy_v1_pnl_calculated"] is False
    assert freeze["c3_opened_for_model2"] is False
    assert freeze["protected_reserve_accessed"] is False
    assert len(freeze["preparation_fingerprint"]) == 64
    json.dumps(freeze, sort_keys=True)


def test_row_fingerprints_survive_required_csv_round_trip(tmp_path: Path):
    rows = _rows()
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    features_path = tmp_path / "features.csv"
    event_map_path = tmp_path / "event_map.csv"
    write_csv(features_path, FEATURE_FIELDS, rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)

    persisted_features = read_csv(features_path)
    persisted_event_map = read_csv(event_map_path)
    assert canonical_rows_fingerprint(rows) == canonical_rows_fingerprint(persisted_features)
    assert canonical_rows_fingerprint(event_map, key="event_ticker") == canonical_rows_fingerprint(
        persisted_event_map, key="event_ticker"
    )


def test_preparation_freeze_binds_persisted_output_bytes(tmp_path: Path):
    rows = _rows()
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    features_path = tmp_path / "features.csv"
    event_map_path = tmp_path / "event_map.csv"
    write_csv(features_path, FEATURE_FIELDS, rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)

    freeze = build_preparation_freeze(
        rows,
        event_map,
        source_files={"synthetic": source},
        implementation_sha256s={"synthetic.py": "0" * 64},
        prepared_output_files={
            "feature_rows": features_path,
            "development_event_map": event_map_path,
        },
        enforce_frozen_counts=False,
    )
    assert freeze["prepared_output_sha256s"] == {
        "development_event_map": sha256_file(event_map_path),
        "feature_rows": sha256_file(features_path),
    }


def test_independent_validator_rederives_persisted_synthetic_preparation(tmp_path: Path):
    from validate_kxbtcd_candidate_e_entry_model_v1_preparation import validate_preparation_artifacts

    rows = _rows()
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    features_path = tmp_path / "features.csv"
    event_map_path = tmp_path / "event_map.csv"
    freeze_path = tmp_path / "freeze.json"
    write_csv(features_path, FEATURE_FIELDS, rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)
    freeze = build_preparation_freeze(
        rows,
        event_map,
        source_files={"synthetic": source},
        implementation_sha256s={"synthetic.py": "0" * 64},
        prepared_output_files={
            "feature_rows": features_path,
            "development_event_map": event_map_path,
        },
        enforce_frozen_counts=False,
    )
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = validate_preparation_artifacts(
        features_path,
        event_map_path,
        freeze_path,
        enforce_frozen_counts=False,
    )
    assert result["feature_rows"] == 3
    assert result["events"] == 3


def test_independent_validator_rejects_prepared_csv_byte_tamper(tmp_path: Path):
    from validate_kxbtcd_candidate_e_entry_model_v1_preparation import validate_preparation_artifacts

    rows = _rows()
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    features_path = tmp_path / "features.csv"
    event_map_path = tmp_path / "event_map.csv"
    freeze_path = tmp_path / "freeze.json"
    write_csv(features_path, FEATURE_FIELDS, rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)
    freeze = build_preparation_freeze(
        rows,
        event_map,
        source_files={"synthetic": source},
        implementation_sha256s={"synthetic.py": "0" * 64},
        prepared_output_files={
            "feature_rows": features_path,
            "development_event_map": event_map_path,
        },
        enforce_frozen_counts=False,
    )
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    features_path.write_text(features_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with __import__("pytest").raises(RuntimeError, match="prepared-output SHA-256 mismatch"):
        validate_preparation_artifacts(
            features_path,
            event_map_path,
            freeze_path,
            enforce_frozen_counts=False,
        )

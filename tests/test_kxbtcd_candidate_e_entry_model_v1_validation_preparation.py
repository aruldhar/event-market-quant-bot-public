from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_entry_model_v1_validation_preparation import (
    CHAMPION,
    ValidationPreparationError,
    build_validation_event_map,
    build_validation_offset_rows,
    read_preoutcome_csv_strict,
    reconstruct_candidate_logit,
    reconstruct_candidate_probability,
)

def _base_feature(event: str, stage: str, close: str, state: str):
    return {
        "schema_version": "kxbtcd_candidate_e_entry_model_v1_feature_row.v1",
        "model_id": "kxbtcd_candidate_e_entry_residual_logistic.v1",
        "stage": stage,
        "state_id": state,
        "event_ticker": event,
        "event_close_time_utc": close,
        "market_ticker": f"MKT-{state}",
        "structural_role": "q50",
        "ttc_target_minutes": 55,
        "decision_time_utc": close,
        "candidate_probability": 0.5,
        "r_5m": 0.0,
        "spread_t": 0.02,
        "mid_move_1m": 0.0,
        "spread_change_1m": 0.0,
        "bid_range_1m": 0.0,
        "ask_range_1m": 0.0,
        "log1p_volume_1m": 0.0,
        "log1p_open_interest": 0.0,
        "log1p_trade_count_5m": 0.0,
        "log1p_contracts_5m": 0.0,
        "taker_imbalance_5m": 0.0,
    }

def test_stage_native_candidate_probability_matches_formula():
    for stage in ("C1", "C2"):
        beta = CHAMPION[stage]["beta_distance"]
        p = reconstruct_candidate_probability(
            stage=stage,
            q_market=0.5,
            d_btc=10.0,
            beta_distance=beta,
        )
        expected = 1.0 / (1.0 + math.exp(-(beta * 10.0)))
        assert p == pytest.approx(expected, rel=0.0, abs=1e-15)

def test_extreme_finite_logit_preserves_historical_probability_endpoint_without_clipping():
    beta = CHAMPION["C2"]["beta_distance"]
    q_market = 0.97
    d_btc = 2367.581470249295
    logit = reconstruct_candidate_logit(
        stage="C2", q_market=q_market, d_btc=d_btc, beta_distance=beta
    )
    probability = reconstruct_candidate_probability(
        stage="C2", q_market=q_market, d_btc=d_btc, beta_distance=beta
    )
    assert logit == pytest.approx(37.87469998298248, rel=0.0, abs=1e-12)
    assert math.isfinite(logit)
    assert probability == 1.0
    assert logit > math.log(math.nextafter(1.0, 0.0) / (1.0 - math.nextafter(1.0, 0.0)))


def test_wrong_stage_beta_fails_closed():
    with pytest.raises(ValidationPreparationError):
        reconstruct_candidate_probability(
            stage="C1",
            q_market=0.5,
            d_btc=10.0,
            beta_distance=CHAMPION["C2"]["beta_distance"],
        )

def test_duplicate_preoutcome_columns_must_agree(tmp_path: Path):
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "event_ticker", "market_ticker", "structural_role",
            "ttc_target_minutes", "stage", "block_id", "stage", "block_id"
        ])
        writer.writerow(["E", "M", "q50", "55", "C1", "B0", "C1", "B0"])
    rows = read_preoutcome_csv_strict(path, expected_stage="C1")
    assert rows[0]["stage"] == "C1"
    assert rows[0]["block_id"] == "B0"

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "event_ticker", "market_ticker", "structural_role",
            "ttc_target_minutes", "stage", "block_id", "stage", "block_id"
        ])
        writer.writerow(["E", "M", "q50", "55", "C1", "B0", "C2", "B0"])
    with pytest.raises(ValidationPreparationError):
        read_preoutcome_csv_strict(path, expected_stage="C1")

def test_preoutcome_reader_rejects_outcome_field(tmp_path: Path):
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "event_ticker", "market_ticker", "structural_role",
            "ttc_target_minutes", "stage", "block_id", "stage", "block_id",
            "outcome"
        ])
        writer.writerow(["E", "M", "q50", "55", "C1", "B0", "C1", "B0", "1"])
    with pytest.raises(ValidationPreparationError):
        read_preoutcome_csv_strict(path, expected_stage="C1")

def test_cli_has_no_prediction_outcome_or_c3_input_surface():
    text = Path(
        "prepare_kxbtcd_candidate_e_entry_model_v1_validation.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in ("--predictions", "--outcomes", "--c3", "--reserve", "--pnl"):
        assert forbidden not in text

def test_event_blocks_are_global_chronological(monkeypatch):
    import src.kxbtcd_candidate_e_entry_model_v1_validation_preparation as module

    monkeypatch.setattr(module, "EXPECTED_STAGE_EVENT_COUNTS", {"C1": 5, "C2": 5})
    monkeypatch.setattr(module, "EXPECTED_STAGE_ROW_COUNTS", {"C1": 5, "C2": 5})
    monkeypatch.setattr(module, "EXPECTED_VALIDATION_EVENTS", 10)
    monkeypatch.setattr(module, "EXPECTED_VALIDATION_ROWS", 10)
    monkeypatch.setattr(module, "VALIDATION_BLOCKS", ("V0", "V1", "V2", "V3", "V4"))
    monkeypatch.setattr(module, "EVENTS_PER_VALIDATION_BLOCK", 2)

    rows = []
    for index in range(10):
        stage = "C1" if index < 5 else "C2"
        rows.append(
            _base_feature(
                f"E{index:02d}",
                stage,
                f"2025-01-{index+1:02d}T00:00:00Z",
                f"S{index:02d}",
            )
        )
    event_map = build_validation_event_map(rows)
    assert [row["validation_block"] for row in event_map] == [
        "V0", "V0", "V1", "V1", "V2", "V2", "V3", "V3", "V4", "V4"
    ]

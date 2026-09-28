from __future__ import annotations

from copy import deepcopy
import math

import pytest

from src.kxbtcd_candidate_e_entry_model_v1 import (
    CANDIDATE_E_ID,
    canonical_rows_fingerprint,
)
from src.kxbtcd_candidate_e_entry_model_v1_materialization import (
    CandidateEEntryMaterializationError,
    H1_PREDICTION_SCHEMA,
    H2_PREDICTION_SCHEMA,
    H3_PREDICTION_SCHEMA,
    materialize_development_features,
)


def _fixture():
    stages = (
        ("H1_OOF", "H1", H1_PREDICTION_SCHEMA, "2025-01-01T01:00:00Z", "E1", "M1", "q10", 55, 0.6),
        ("H2", "H2", H2_PREDICTION_SCHEMA, "2025-01-02T01:00:00Z", "E2", "M2", "q50", 50, 0.7),
        ("H3", "H3", H3_PREDICTION_SCHEMA, "2025-01-03T01:00:00Z", "E3", "M3", "q90", 45, 0.4),
    )
    preoutcome = []
    predictions = {"H1_OOF": [], "H2": [], "H3": []}
    allowlist = []
    candles = []
    trades = []
    for stage, source_stage, schema, decision, event, market, role, ttc, probability in stages:
        state = f"{event}|{market}|TTC{ttc}|{role}"
        day = int(event[1:])
        end_ts = 1735693200 + (day - 1) * 86400  # exact scheduled minute in base fixture
        preoutcome.append(
            {
                "stage": source_stage,
                "event_ticker": event,
                "market_ticker": market,
                "structural_role": role,
                "ttc_target_minutes": str(ttc),
                "decision_target_utc": decision,
                "kalshi_quote_end_period_ts": str(end_ts),
                "kalshi_quote_staleness_seconds": "0",
                "event_close_time_utc": f"2025-01-0{day}T02:00:00Z",
                "yes_bid": "0.41",
                "yes_ask": "0.46",
                "r_5m": str(10.0 * day),
            }
        )
        predictions[stage].append(
            {
                "schema_version": schema,
                "candidate_id": CANDIDATE_E_ID,
                "state_id": state,
                "event_ticker": event,
                "market_ticker": market,
                "candidate_probability": str(probability),
                "outcome": "1",  # must be ignored by feature materialization
            }
        )
        allowlist.append({"stage": stage, "event_ticker": event, "market_ticker": market})
        candles.append(
            {
                "stage": stage,
                "event_ticker": event,
                "market_ticker": market,
                "end_period_ts": str(end_ts),
                "yes_bid_open_dollars": "0.39",
                "yes_bid_low_dollars": "0.38",
                "yes_bid_high_dollars": "0.42",
                "yes_bid_close_dollars": "0.41",
                "yes_ask_open_dollars": "0.45",
                "yes_ask_low_dollars": "0.43",
                "yes_ask_high_dollars": "0.47",
                "yes_ask_close_dollars": "0.46",
                "volume_fp": "9",
                "open_interest_fp": "99",
            }
        )
    # H1 strict-window trades: exactly -300s must be excluded; -299 and t are included.
    trades.extend(
        [
            {
                "stage": "H1_OOF",
                "event_ticker": "E1",
                "market_ticker": "M1",
                "trade_id": "old_boundary",
                "created_time": "2025-01-01T00:55:00Z",
                "count_fp": "100",
                "taker_outcome_side": "yes",
            },
            {
                "stage": "H1_OOF",
                "event_ticker": "E1",
                "market_ticker": "M1",
                "trade_id": "inside_yes",
                "created_time": "2025-01-01T00:55:01Z",
                "count_fp": "3",
                "taker_outcome_side": "yes",
            },
            {
                "stage": "H1_OOF",
                "event_ticker": "E1",
                "market_ticker": "M1",
                "trade_id": "at_decision_no",
                "created_time": "2025-01-01T01:00:00Z",
                "count_fp": "1",
                "taker_outcome_side": "no",
            },
        ]
    )
    return preoutcome, predictions, allowlist, candles, trades


def _materialize(fixture):
    preoutcome, predictions, allowlist, candles, trades = fixture
    return materialize_development_features(
        preoutcome_rows=preoutcome,
        h1_prediction_rows=predictions["H1_OOF"],
        h2_prediction_rows=predictions["H2"],
        h3_prediction_rows=predictions["H3"],
        archive_allowlist_rows=allowlist,
        candle_rows=candles,
        trade_rows=trades,
        enforce_frozen_counts=False,
    )


def test_exact_frozen_feature_formulas_and_trade_window():
    rows = _materialize(_fixture())
    h1 = next(row for row in rows if row["stage"] == "H1_OOF")
    assert h1["spread_t"] == pytest.approx(0.05)
    assert h1["mid_move_1m"] == pytest.approx(((0.41 + 0.46) - (0.39 + 0.45)) / 2)
    assert h1["spread_change_1m"] == pytest.approx((0.46 - 0.41) - (0.45 - 0.39))
    assert h1["bid_range_1m"] == pytest.approx(0.04)
    assert h1["ask_range_1m"] == pytest.approx(0.04)
    assert h1["log1p_volume_1m"] == pytest.approx(math.log1p(9))
    assert h1["log1p_open_interest"] == pytest.approx(math.log1p(99))
    assert h1["log1p_trade_count_5m"] == pytest.approx(math.log1p(2))
    assert h1["log1p_contracts_5m"] == pytest.approx(math.log1p(4))
    assert h1["taker_imbalance_5m"] == pytest.approx((3 - 1) / 4)
    assert "outcome" not in h1


def test_prediction_outcomes_cannot_change_materialized_features_or_fingerprint():
    fixture = _fixture()
    baseline = _materialize(fixture)
    altered = deepcopy(fixture)
    for stage_rows in altered[1].values():
        for row in stage_rows:
            row["outcome"] = "0" if row["outcome"] == "1" else "1"
    changed = _materialize(altered)
    assert baseline == changed
    assert canonical_rows_fingerprint(baseline) == canonical_rows_fingerprint(changed)


def test_missing_exact_frozen_quote_candle_fails_closed_without_nearest_or_imputation():
    fixture = _fixture()
    fixture[3].pop(1)
    with pytest.raises(CandidateEEntryMaterializationError, match="no exact one-minute candle"):
        _materialize(fixture)


def test_sixty_second_stale_frozen_quote_timestamp_is_reconstructed_exactly():
    fixture = _fixture()
    # H1 decision remains 01:00, but Candidate E's frozen Kalshi quote came from
    # the exact 00:59 candle with the permitted 60-second staleness.
    fixture[0][0]["kalshi_quote_end_period_ts"] = str(1735693140)
    fixture[0][0]["kalshi_quote_staleness_seconds"] = "60"
    fixture[3][0]["end_period_ts"] = str(1735693140)
    # Add a different decision-minute candle to prove the materializer does not
    # silently switch to it.
    decision_candle = dict(fixture[3][0])
    decision_candle["end_period_ts"] = str(1735693200)
    decision_candle["yes_bid_open_dollars"] = "0.10"
    decision_candle["yes_bid_low_dollars"] = "0.10"
    decision_candle["yes_bid_high_dollars"] = "0.10"
    decision_candle["yes_bid_close_dollars"] = "0.10"
    decision_candle["yes_ask_open_dollars"] = "0.20"
    decision_candle["yes_ask_low_dollars"] = "0.20"
    decision_candle["yes_ask_high_dollars"] = "0.20"
    decision_candle["yes_ask_close_dollars"] = "0.20"
    fixture[3].append(decision_candle)

    rows = _materialize(fixture)
    h1 = next(row for row in rows if row["stage"] == "H1_OOF")
    assert h1["spread_t"] == pytest.approx(0.05)
    assert h1["mid_move_1m"] == pytest.approx(((0.41 + 0.46) - (0.39 + 0.45)) / 2)
    # Trade aggregation still uses the scheduled decision time, so the trade at
    # exactly 01:00 remains included.
    assert h1["log1p_trade_count_5m"] == pytest.approx(math.log1p(2))


def test_frozen_quote_timestamp_after_decision_fails_closed():
    fixture = _fixture()
    fixture[0][0]["kalshi_quote_end_period_ts"] = str(1735693260)
    fixture[0][0]["kalshi_quote_staleness_seconds"] = "-60"
    with pytest.raises(CandidateEEntryMaterializationError, match="after decision timestamp"):
        _materialize(fixture)


def test_frozen_quote_staleness_must_equal_timestamp_difference():
    fixture = _fixture()
    fixture[0][0]["kalshi_quote_staleness_seconds"] = "60"
    with pytest.raises(CandidateEEntryMaterializationError, match="staleness mismatch"):
        _materialize(fixture)


def test_frozen_candidate_e_quote_must_match_exact_archive_candle_close():
    fixture = _fixture()
    fixture[3][0]["yes_bid_close_dollars"] = "0.40"
    with pytest.raises(CandidateEEntryMaterializationError, match="does not match exact archive candle close"):
        _materialize(fixture)


def test_duplicate_trade_identity_fails_closed():
    fixture = _fixture()
    fixture[4].append(dict(fixture[4][1]))
    with pytest.raises(CandidateEEntryMaterializationError, match="duplicate trade identity"):
        _materialize(fixture)


def test_unrecognized_archive_stage_is_rejected_as_protected_or_out_of_contract():
    fixture = _fixture()
    fixture[2][0]["stage"] = "PROTECTED_RESERVE"
    with pytest.raises(CandidateEEntryMaterializationError, match="unrecognized/protected stage"):
        _materialize(fixture)


def test_h1_rejected_momentum_predictions_are_ignored():
    fixture = _fixture()
    rejected = dict(fixture[1]["H1_OOF"][0])
    rejected["candidate_id"] = "kxbtcd_btc_distance_momentum_offset_logistic.v1"
    rejected["candidate_probability"] = "0.99"
    fixture[1]["H1_OOF"].append(rejected)
    rows = _materialize(fixture)
    h1 = next(row for row in rows if row["stage"] == "H1_OOF")
    assert h1["candidate_probability"] == pytest.approx(0.6)


def test_trade_stage_event_identity_mismatch_fails_closed():
    fixture = _fixture()
    fixture[4][1]["event_ticker"] = "WRONG_EVENT"
    with pytest.raises(CandidateEEntryMaterializationError, match="stage/event identity mismatch"):
        _materialize(fixture)


def test_decision_timestamp_must_be_exact_minute_boundary():
    fixture = _fixture()
    fixture[0][0]["decision_target_utc"] = "2025-01-01T01:00:01Z"
    with pytest.raises(CandidateEEntryMaterializationError, match="exact minute boundary"):
        _materialize(fixture)


def test_independent_validator_rematerializes_from_bound_sources(tmp_path):
    import csv
    import json
    from pathlib import Path

    from src.kxbtcd_candidate_e_entry_model_v1 import build_development_event_map
    from src.kxbtcd_candidate_e_entry_model_v1_materialization import (
        EVENT_MAP_FIELDS,
        FEATURE_FIELDS,
        IMPLEMENTATION_FILES,
        build_preparation_freeze,
        sha256_file,
        write_csv,
    )
    from validate_kxbtcd_candidate_e_entry_model_v1_preparation import (
        validate_preparation_artifacts,
    )

    fixture = _fixture()
    rows = _materialize(fixture)
    event_map = build_development_event_map(rows, enforce_frozen_counts=False)
    preoutcome, predictions, allowlist, candles, trades = fixture

    def write_input(path: Path, source_rows):
        fields = list(source_rows[0])
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(source_rows)

    sources = {
        "preoutcome": tmp_path / "preoutcome.csv",
        "h1_predictions": tmp_path / "h1.csv",
        "h2_predictions": tmp_path / "h2.csv",
        "h3_predictions": tmp_path / "h3.csv",
        "archive_allowlist": tmp_path / "allowlist.csv",
        "archive_candles": tmp_path / "candles.csv",
        "archive_trades": tmp_path / "trades.csv",
    }
    write_input(sources["preoutcome"], preoutcome)
    write_input(sources["h1_predictions"], predictions["H1_OOF"])
    write_input(sources["h2_predictions"], predictions["H2"])
    write_input(sources["h3_predictions"], predictions["H3"])
    write_input(sources["archive_allowlist"], allowlist)
    write_input(sources["archive_candles"], candles)
    write_input(sources["archive_trades"], trades)

    features_path = tmp_path / "features.csv"
    event_map_path = tmp_path / "event_map.csv"
    freeze_path = tmp_path / "freeze.json"
    write_csv(features_path, FEATURE_FIELDS, rows)
    write_csv(event_map_path, EVENT_MAP_FIELDS, event_map)

    root = Path(__file__).resolve().parents[1]
    implementation_hashes = {
        relative: sha256_file(root / relative) for relative in IMPLEMENTATION_FILES
    }
    freeze = build_preparation_freeze(
        rows,
        event_map,
        source_files=sources,
        implementation_sha256s=implementation_hashes,
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
        source_files=sources,
        implementation_root=root,
        enforce_frozen_counts=False,
    )
    assert result["feature_rows"] == 3
    assert result["events"] == 3

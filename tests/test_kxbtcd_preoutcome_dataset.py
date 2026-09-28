from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import unittest

from src.btc_state_feature_contract import STATE_SCHEMA_VERSION, contract_fingerprint
from src.kxbtcd_chronological_split_contract import build_chronological_split
from src.kxbtcd_preoutcome_dataset import (
    CANDIDATE_B_FEATURE_NAMES,
    CANDIDATE_B_MODEL_ID,
    DATASET_ROW_FIELDS,
    FORBIDDEN_PREOUTCOME_FIELDS,
    L2_PENALTY_GRID,
    KxbtcdPreoutcomeDatasetError,
    build_preoutcome_dataset,
    candidate_b_spec_fingerprint,
    candidate_b_specification,
    candidate_b_transforms,
    candidate_b_validation_gate,
    dataset_design_fingerprint,
    select_candidate_b_lambda,
    validate_dataset_contract,
)


def _event(ticker: str, close_time: str, primitive: str):
    return {
        "event_ticker": ticker,
        "close_time_utc": close_time,
        "settlement_regime_id": "brti_60s_simple_mean_untrimmed",
        "settlement_primitive_ids": [primitive],
        "source_lineage_refs": [f"raw:event:{ticker}"],
    }


def frozen_split():
    old_events = []
    old_tickers = []
    old_primitives = []
    for i in range(20):
        ticker = f"OLD-{i:02d}"
        primitive = f"old-primitive-{i:02d}"
        old_tickers.append(ticker)
        old_primitives.append(primitive)
        old_events.append(
            _event(ticker, f"2025-12-{i+1:02d}T12:00:00Z", primitive)
        )

    candidate_dates = (
        "2026-01-06T12:00:00Z",
        "2026-01-13T12:00:00Z",
        "2026-01-20T12:00:00Z",
        "2026-01-27T12:00:00Z",
        "2026-02-03T12:00:00Z",
    )
    candidates = [
        _event(f"NEW-{i}", close_time, f"new-primitive-{i}")
        for i, close_time in enumerate(candidate_dates)
    ]
    return build_chronological_split(
        [*old_events, *candidates],
        checkpoint10_event_tickers=old_tickers,
        checkpoint10_primitive_ids=old_primitives,
    )


def _split_row(rows, event_ticker: str):
    return next(row for row in rows if row["event_ticker"] == event_ticker)


def valid_state(
    event_ticker: str = "NEW-0",
    *,
    state_id: str = "state-1",
    market_ticker: str = "NEW-0-MKT-100K",
    strike: str = "100000",
    q: str = "0.50",
    quality: str = "usable",
):
    rows = frozen_split()
    split = _split_row(rows, event_ticker)
    close = datetime.fromisoformat(split["close_time_utc"].replace("Z", "+00:00"))
    as_of = close - timedelta(hours=1)
    bid = Decimal(q) - Decimal("0.01")
    ask = Decimal(q) + Decimal("0.01")
    raw_id = f"raw:kalshi:{state_id}"
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_id": state_id,
        "product_head": "KXBTCD",
        "state_view": "historical_reconstructed",
        "as_of_utc": as_of.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of_local_monotonic_ns": 123456,
        "alignment_epoch_id": "epoch-1",
        "state_quality": quality,
        "clock_health_status": "unresolved",
        "raw_observation_refs": [raw_id],
        "btc_features": [],
        "source_age_seconds_by_source": {"kalshi.kxbtcd": "0.2"},
        "product_context": {
            "event_ticker": event_ticker,
            "market_ticker": market_ticker,
            "settlement_regime_id": "brti_60s_simple_mean_untrimmed",
            "strike_dollars": strike,
            "time_to_close_seconds": "3600",
            "yes_bid": str(bid),
            "yes_ask": str(ask),
            "midpoint": q,
            "spread": "0.02",
        },
    }


class KxbtcdPreoutcomeDatasetTests(unittest.TestCase):
    def test_contract_is_valid_and_candidate_b_is_model_only_specification(self):
        validate_dataset_contract()
        spec = candidate_b_specification()
        self.assertEqual(spec["model_id"], CANDIDATE_B_MODEL_ID)
        self.assertEqual(spec["external_btc_state_features"], [])
        self.assertFalse(spec["locked_test_outcomes_opened"])
        self.assertFalse(spec["execution_authorized"])
        self.assertEqual(
            tuple(item["name"] for item in spec["learned_features"]),
            CANDIDATE_B_FEATURE_NAMES,
        )

    def test_candidate_b_fingerprint_and_dataset_design_fingerprint_are_stable(self):
        self.assertEqual(
            candidate_b_spec_fingerprint(),
            "e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3",
        )
        self.assertEqual(
            dataset_design_fingerprint(),
            "adc0e6a05ec6a61c114a7d49cb0ad5e271321fe0e8c3c80b76fed81b98025286",
        )

    def test_candidate_b_has_exact_frozen_lambda_grid(self):
        self.assertEqual(
            candidate_b_specification()["regularization"]["lambda_grid"],
            [str(value) for value in L2_PENALTY_GRID],
        )

    def test_transforms_are_zero_at_fixed_reference_values(self):
        transformed = candidate_b_transforms("0.5", "100000", "0")
        self.assertEqual(transformed["market_logit"], "0")
        self.assertEqual(transformed["strike_log_ratio"], "0")
        self.assertEqual(transformed["time_log1p_hours"], "0")

    def test_market_logit_clipping_is_predeclared(self):
        transformed = candidate_b_transforms("1", "100000", "3600")
        self.assertEqual(transformed["q_market"], "1")
        self.assertEqual(transformed["q_market_clipped_for_logit"], "0.999")
        self.assertTrue(Decimal(transformed["market_logit"]).is_finite())

    def test_builder_materializes_train_validation_and_locked_test_preoutcome_rows(self):
        split = frozen_split()
        states = [
            valid_state("NEW-0", state_id="train", market_ticker="TRAIN-MKT"),
            valid_state("NEW-3", state_id="validation", market_ticker="VAL-MKT"),
            valid_state("NEW-4", state_id="test", market_ticker="TEST-MKT"),
        ]
        result = build_preoutcome_dataset(states, split)
        self.assertEqual({row["partition"] for row in result.rows}, {"train", "validation", "locked_test"})
        self.assertEqual(result.summary["locked_test_label_count"], 0)
        self.assertFalse(result.summary["model_fit_performed"])

    def test_live_first_seen_state_is_rejected_from_offline_historical_dataset(self):
        state = valid_state()
        state["state_view"] = "live_first_seen"
        with self.assertRaisesRegex(KxbtcdPreoutcomeDatasetError, "historical_reconstructed"):
            build_preoutcome_dataset([state], frozen_split())

    def test_dataset_rows_are_outcome_blind(self):
        result = build_preoutcome_dataset([valid_state()], frozen_split())
        self.assertEqual(set(result.rows[0]), set(DATASET_ROW_FIELDS))
        self.assertFalse(FORBIDDEN_PREOUTCOME_FIELDS.intersection(result.rows[0]))

    def test_exact_market_ticker_is_carried_into_dataset(self):
        result = build_preoutcome_dataset(
            [valid_state(market_ticker="KXBTCD-EXACT-CONTRACT")], frozen_split()
        )
        self.assertEqual(result.rows[0]["market_ticker"], "KXBTCD-EXACT-CONTRACT")

    def test_state_contract_fingerprint_is_carried(self):
        result = build_preoutcome_dataset([valid_state()], frozen_split())
        self.assertEqual(result.rows[0]["state_contract_fingerprint"], contract_fingerprint())

    def test_event_row_weights_sum_to_one(self):
        states = [
            valid_state(state_id="a", market_ticker="MKT-A", strike="99000", q="0.6"),
            valid_state(state_id="b", market_ticker="MKT-B", strike="100000", q="0.5"),
            valid_state(state_id="c", market_ticker="MKT-C", strike="101000", q="0.4"),
        ]
        result = build_preoutcome_dataset(states, frozen_split())
        total = sum(Decimal(row["event_row_weight"]) for row in result.rows)
        self.assertAlmostEqual(float(total), 1.0, places=12)

    def test_blocked_state_is_audited_but_cannot_enter_dataset(self):
        state = valid_state(quality="blocked_stale_data")
        with self.assertRaisesRegex(KxbtcdPreoutcomeDatasetError, "no modeling-eligible"):
            build_preoutcome_dataset([state], frozen_split())

        good = valid_state(state_id="good", market_ticker="GOOD")
        result = build_preoutcome_dataset([good, state], frozen_split())
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(len(result.exclusions), 1)
        self.assertIn("state_quality:blocked_stale_data", result.exclusions[0]["exclusion_reasons"])

    def test_checkpoint10_quarantine_state_is_audited_not_modeled(self):
        good = valid_state(state_id="good", market_ticker="GOOD")
        old = valid_state("OLD-00", state_id="old", market_ticker="OLD-MKT")
        result = build_preoutcome_dataset([good, old], frozen_split())
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.exclusions[0]["partition"], "quarantine")
        self.assertIn("checkpoint10_event_quarantine", result.exclusions[0]["exclusion_reasons"])

    def test_unknown_event_fails_closed(self):
        state = valid_state()
        state["product_context"]["event_ticker"] = "NOT-IN-SPLIT"
        with self.assertRaisesRegex(KxbtcdPreoutcomeDatasetError, "absent from frozen split"):
            build_preoutcome_dataset([state], frozen_split())

    def test_duplicate_state_id_fails_closed(self):
        first = valid_state(state_id="duplicate", market_ticker="MKT-A")
        second = valid_state(state_id="duplicate", market_ticker="MKT-B")
        with self.assertRaisesRegex(KxbtcdPreoutcomeDatasetError, "duplicate state_id"):
            build_preoutcome_dataset([first, second], frozen_split())

    def test_time_to_close_must_match_event_close(self):
        state = valid_state()
        state["product_context"]["time_to_close_seconds"] = "1200"
        with self.assertRaisesRegex(KxbtcdPreoutcomeDatasetError, "disagrees with event close"):
            build_preoutcome_dataset([state], frozen_split())

    def test_outcome_field_in_input_state_is_rejected(self):
        state = valid_state()
        state["outcome"] = 1
        with self.assertRaises(KxbtcdPreoutcomeDatasetError):
            build_preoutcome_dataset([state], frozen_split())

    def test_dataset_fingerprint_is_deterministic_for_input_order(self):
        states = [
            valid_state(state_id="a", market_ticker="MKT-A", strike="99000"),
            valid_state(state_id="b", market_ticker="MKT-B", strike="101000"),
        ]
        forward = build_preoutcome_dataset(states, frozen_split())
        reverse = build_preoutcome_dataset(list(reversed(states)), frozen_split())
        self.assertEqual(forward.summary["dataset_fingerprint"], reverse.summary["dataset_fingerprint"])

    def test_lambda_selection_uses_validation_loss_and_stronger_regularization_on_exact_tie(self):
        scores = {
            "0.01": "0.20",
            "0.1": "0.19",
            "1": "0.19",
            "10": "0.25",
        }
        self.assertEqual(select_candidate_b_lambda(scores), Decimal("1"))

    def test_lambda_selection_rejects_partial_grid(self):
        with self.assertRaisesRegex(KxbtcdPreoutcomeDatasetError, "exactly the frozen lambda grid"):
            select_candidate_b_lambda({"0.1": "0.2"})

    def test_validation_gate_requires_strict_log_loss_improvement(self):
        self.assertTrue(
            candidate_b_validation_gate(
                raw_midpoint_event_weighted_log_loss="0.10",
                candidate_b_event_weighted_log_loss="0.099",
            )
        )
        self.assertFalse(
            candidate_b_validation_gate(
                raw_midpoint_event_weighted_log_loss="0.10",
                candidate_b_event_weighted_log_loss="0.10",
            )
        )

    def test_candidate_b_dataset_does_not_materialize_external_btc_features(self):
        state = valid_state()
        state["btc_features"] = [
            {
                "feature_id": "coinbase.btcusd.return_300s",
                "source_id": "coinbase.public_ws.btcusd",
                "instrument_id": "BTC-USD",
                "feature_class": "return",
                "value": "0.001",
                "source_observation_refs": [state["raw_observation_refs"][0]],
                "lookback_seconds": 300,
                "lead_lag_seconds": None,
            }
        ]
        result = build_preoutcome_dataset([state], frozen_split())
        self.assertFalse(any("coinbase" in field for field in result.rows[0]))
        self.assertEqual(candidate_b_specification()["external_btc_state_features"], [])


if __name__ == "__main__":
    unittest.main()

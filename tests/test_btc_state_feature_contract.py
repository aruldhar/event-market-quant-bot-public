from __future__ import annotations

import copy
import unittest

from src.btc_state_feature_contract import (
    BtcStateFeatureContractError,
    DECISION_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    MODEL_OUTPUT_SCHEMA_VERSION,
    RAW_OBSERVATION_REF_SCHEMA_VERSION,
    STATE_SCHEMA_VERSION,
    contract_fingerprint,
    validate_model_output,
    validate_product_label,
    validate_raw_observation_ref,
    validate_research_decision,
    validate_schema_contract,
    validate_state_for_live_causal_use,
    validate_state_for_model_use,
    validate_synchronized_state,
)


RAW_ID = "raw:coinbase:1"


def valid_raw_ref():
    return {
        "schema_version": RAW_OBSERVATION_REF_SCHEMA_VERSION,
        "raw_observation_id": RAW_ID,
        "source_id": "coinbase.public_ws.btcusd",
        "instrument_id": "BTC-USD",
        "source_session_id": "coinbase-session-1",
        "source_sequence_or_message_id": "123",
        "source_event_time_utc": "2026-08-14T05:00:00Z",
        "relay_or_publication_time_utc": None,
        "local_receive_utc": "2026-08-14T05:00:00.120000Z",
        "local_receive_monotonic_ns": 1000,
        "raw_payload_reference": "data/raw/coinbase/example.jsonl#1",
        "raw_payload_sha256": "a" * 64,
    }


def valid_feature():
    return {
        "feature_id": "coinbase.btcusd.return_300s",
        "source_id": "coinbase.public_ws.btcusd",
        "instrument_id": "BTC-USD",
        "feature_class": "return",
        "value": "0.0012",
        "source_observation_refs": [RAW_ID],
        "lookback_seconds": 300,
        "lead_lag_seconds": None,
    }


def valid_kxbtcd_state():
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_id": "state:kxbtcd:1",
        "product_head": "KXBTCD",
        "state_view": "live_first_seen",
        "as_of_utc": "2026-08-14T05:00:01Z",
        "as_of_local_monotonic_ns": 2000,
        "alignment_epoch_id": "epoch-1",
        "state_quality": "usable",
        "clock_health_status": "unresolved",
        "raw_observation_refs": [RAW_ID],
        "btc_features": [valid_feature()],
        "source_age_seconds_by_source": {"coinbase.public_ws.btcusd": "0.88"},
        "product_context": {
            "event_ticker": "KXBTCD-EXAMPLE",
            "market_ticker": "KXBTCD-EXAMPLE-120000",
            "settlement_regime_id": "brti_60s_simple_mean_untrimmed",
            "strike_dollars": "120000",
            "time_to_close_seconds": "3600",
            "yes_bid": "0.61",
            "yes_ask": "0.63",
            "midpoint": "0.62",
            "spread": "0.02",
        },
    }


class BtcStateFeatureContractTests(unittest.TestCase):
    def test_schema_contract_and_fingerprint_are_stable(self):
        validate_schema_contract()
        fingerprint = contract_fingerprint()
        self.assertEqual(
            fingerprint,
            "2739be9af27200a4a2ca8d189bc93d2f3d3349f6b3524f6b919e632fcf9d3668",
        )
        self.assertEqual(fingerprint, contract_fingerprint())

    def test_valid_raw_observation_ref(self):
        validate_raw_observation_ref(valid_raw_ref())

    def test_valid_kxbtcd_state_and_model_use(self):
        state = valid_kxbtcd_state()
        validate_synchronized_state(state)
        validate_state_for_model_use(state)


    def test_historical_reconstructed_state_is_model_usable_but_not_live_causal(self):
        state = valid_kxbtcd_state()
        state["state_view"] = "historical_reconstructed"
        validate_state_for_model_use(state)
        with self.assertRaisesRegex(BtcStateFeatureContractError, "live-causal"):
            validate_state_for_live_causal_use(state)

    def test_unknown_state_view_fails_closed(self):
        state = valid_kxbtcd_state()
        state["state_view"] = "pretend_live"
        with self.assertRaisesRegex(BtcStateFeatureContractError, "state_view"):
            validate_synchronized_state(state)

    def test_kxbtcd_market_ticker_is_mandatory(self):
        state = valid_kxbtcd_state()
        del state["product_context"]["market_ticker"]
        with self.assertRaisesRegex(BtcStateFeatureContractError, "market_ticker"):
            validate_synchronized_state(state)

    def test_kxbtcd_strike_is_mandatory(self):
        state = valid_kxbtcd_state()
        del state["product_context"]["strike_dollars"]
        with self.assertRaisesRegex(BtcStateFeatureContractError, "strike_dollars"):
            validate_synchronized_state(state)

    def test_kxbtcd_time_to_close_is_mandatory(self):
        state = valid_kxbtcd_state()
        del state["product_context"]["time_to_close_seconds"]
        with self.assertRaisesRegex(BtcStateFeatureContractError, "time_to_close_seconds"):
            validate_synchronized_state(state)

    def test_state_requires_raw_lineage(self):
        state = valid_kxbtcd_state()
        state["raw_observation_refs"] = []
        with self.assertRaisesRegex(BtcStateFeatureContractError, "must not be empty"):
            validate_synchronized_state(state)

    def test_feature_requires_source_identity(self):
        state = valid_kxbtcd_state()
        state["btc_features"][0]["source_id"] = ""
        with self.assertRaisesRegex(BtcStateFeatureContractError, "source_id"):
            validate_synchronized_state(state)

    def test_feature_raw_refs_must_exist_in_state_lineage(self):
        state = valid_kxbtcd_state()
        state["btc_features"][0]["source_observation_refs"] = ["raw:missing"]
        with self.assertRaisesRegex(BtcStateFeatureContractError, "absent from state lineage"):
            validate_synchronized_state(state)

    def test_future_or_label_feature_is_rejected(self):
        state = valid_kxbtcd_state()
        state["btc_features"][0]["feature_id"] = "coinbase.btcusd.forward_return_300s"
        with self.assertRaisesRegex(BtcStateFeatureContractError, "future/label"):
            validate_synchronized_state(state)

    def test_cross_layer_state_field_is_rejected(self):
        state = valid_kxbtcd_state()
        state["settled_yes"] = 1
        with self.assertRaises(BtcStateFeatureContractError):
            validate_synchronized_state(state)

    def test_blocked_state_fails_closed_for_model_use(self):
        state = valid_kxbtcd_state()
        state["state_quality"] = "blocked_stale_data"
        validate_synchronized_state(state)
        with self.assertRaisesRegex(BtcStateFeatureContractError, "not usable"):
            validate_state_for_model_use(state)

    def test_subsecond_lead_lag_is_blocked(self):
        state = valid_kxbtcd_state()
        state["btc_features"][0].update(
            {
                "feature_id": "coinbase_vs_kraken.lead_lag_250ms",
                "feature_class": "lead_lag",
                "lookback_seconds": None,
                "lead_lag_seconds": "0.25",
            }
        )
        with self.assertRaisesRegex(BtcStateFeatureContractError, "sub-second lead/lag"):
            validate_synchronized_state(state)

    def test_slow_contemporaneous_return_is_allowed_with_unresolved_clock_health(self):
        state = valid_kxbtcd_state()
        self.assertEqual(state["clock_health_status"], "unresolved")
        validate_state_for_model_use(state)

    def test_quote_consistency_is_fail_closed(self):
        state = valid_kxbtcd_state()
        state["product_context"]["midpoint"] = "0.70"
        with self.assertRaisesRegex(BtcStateFeatureContractError, "midpoint"):
            validate_synchronized_state(state)

    def test_kxbtcd_label_is_separate_and_binary(self):
        label = {
            "schema_version": LABEL_SCHEMA_VERSION,
            "label_id": "label:1",
            "product_head": "KXBTCD",
            "label_type": "kxbtcd_settled_yes",
            "value": 1,
            "label_source": "kalshi.finalized_market_result",
            "raw_observation_refs": ["raw:kalshi:result:1"],
            "product_context": {
                "event_ticker": "KXBTCD-EXAMPLE",
                "market_ticker": "KXBTCD-EXAMPLE-120000",
                "settlement_primitive_id": "primitive-1",
                "settlement_regime_id": "brti_60s_simple_mean_untrimmed",
            },
        }
        validate_product_label(label)
        label["value"] = "0.5"
        with self.assertRaisesRegex(BtcStateFeatureContractError, "0 or 1"):
            validate_product_label(label)

    def test_kxbtcd_model_output_probability_is_bounded(self):
        output = {
            "schema_version": MODEL_OUTPUT_SCHEMA_VERSION,
            "model_output_id": "pred:1",
            "product_head": "KXBTCD",
            "state_id": "state:kxbtcd:1",
            "model_id": "baseline",
            "model_version": "v1",
            "output_type": "p_yes",
            "value": "0.63",
            "created_at_utc": "2026-08-14T05:00:01Z",
            "training_window_id": "train-window-1",
        }
        validate_model_output(output)
        output["value"] = "1.01"
        with self.assertRaisesRegex(BtcStateFeatureContractError, r"\[0, 1\]"):
            validate_model_output(output)

    def test_research_decision_cannot_be_order_action(self):
        decision = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "decision_id": "decision:1",
            "product_head": "KXBTCD",
            "state_id": "state:kxbtcd:1",
            "economics_id": "econ:1",
            "policy_id": "research-policy-v1",
            "decision": "no_signal",
            "blocked_reasons": [],
        }
        validate_research_decision(decision)
        bad = copy.deepcopy(decision)
        bad["decision"] = "place_order"
        with self.assertRaisesRegex(BtcStateFeatureContractError, "prohibited"):
            validate_research_decision(bad)


if __name__ == "__main__":
    unittest.main()

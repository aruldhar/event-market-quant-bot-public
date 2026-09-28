from __future__ import annotations

from datetime import datetime, timezone
import unittest

from src.btc_state_feature_contract import (
    BtcStateFeatureContractError,
    validate_state_for_live_causal_use,
    validate_state_for_model_use,
)
from src.kxbtcd_chronological_split_contract import (
    SPLIT_ROW_SCHEMA_VERSION,
    TARGET_REGIME_ID,
    design_fingerprint as split_design_fingerprint,
)
from src.kxbtcd_preoutcome_materialization import (
    CONSERVATIVE_MODERN_START_UTC,
    MATERIALIZATION_CONTRACT_VERSION,
    MAX_EVENTS_PER_UTC_WEEK,
    STRUCTURAL_QUANTILES,
    TIME_TO_CLOSE_ANCHORS_SECONDS,
    KxbtcdPreoutcomeMaterializationError,
    build_historical_reconstructed_state,
    materialization_definition,
    materialization_fingerprint,
    select_anchor_observation,
    select_structural_markets,
    select_weekly_events,
    validate_materialization_contract,
)


def split_row(event: str, close: str, week: str, *, partition: str = "train", eligible=True):
    return {
        "schema_version": SPLIT_ROW_SCHEMA_VERSION,
        "experiment_family_id": "kxbtcd_market_context_probability_baseline.v1",
        "design_fingerprint": split_design_fingerprint(),
        "split_fingerprint": "split-fixture",
        "event_ticker": event,
        "close_time_utc": close,
        "utc_week_start": week,
        "settlement_regime_id": TARGET_REGIME_ID,
        "settlement_primitive_ids": [f"primitive:{event}"],
        "source_lineage_refs": [f"raw:event:{event}"],
        "partition": partition,
        "embargoed": not eligible,
        "eligible_for_modeling": eligible,
        "exclusion_reason": "" if eligible else "boundary_embargo_24h",
    }


def market(event: str, index: int):
    return {
        "event_ticker": event,
        "market_ticker": f"{event}-M{index}",
        "strike_type": "greater",
        "strike_dollars": str(90000 + 1000 * index),
        "source_lineage_refs": [f"raw:market:{event}:{index}"],
    }


def quote(end_ts: int, *, valid=True, q="0.50", raw_id=None):
    qv = float(q)
    bid = qv - 0.01
    ask = qv + 0.01
    return {
        "end_period_ts": end_ts,
        "valid_quote_observation": valid,
        "yes_bid": f"{bid:.2f}",
        "yes_ask": f"{ask:.2f}",
        "midpoint": f"{qv:.2f}",
        "spread": "0.02",
        "raw_observation_id": raw_id or f"raw:quote:{end_ts}",
    }


class KxbtcdPreoutcomeMaterializationTests(unittest.TestCase):
    def test_materialization_contract_is_valid_and_outcome_blind(self):
        validate_materialization_contract()
        definition = materialization_definition()
        self.assertFalse(definition["outcomes_materialized"])
        self.assertFalse(definition["model_fit_performed"])
        self.assertFalse(definition["execution_authorized"])
        self.assertFalse(definition["historical_live_causality_claim"])
        self.assertEqual(MATERIALIZATION_CONTRACT_VERSION, "kxbtcd_preoutcome_materialization.v3")
        self.assertEqual(
            definition["regime_frame"]["conservative_modern_start_utc"],
            CONSERVATIVE_MODERN_START_UTC,
        )
        self.assertFalse(definition["regime_frame"]["unsampled_event_semantics_claimed_proven"])
        self.assertTrue(
            definition["regime_frame"]["selected_event_full_ladder_semantic_validation_required"]
        )

    def test_materialization_fingerprint_is_stable(self):
        self.assertEqual(
            materialization_fingerprint(),
            "f9a2459f81b1bb90e1ff55d099e837cb47c78c6586195759d55b5029d676bdb5",
        )

    def test_weekly_event_selection_is_bounded_and_deterministic(self):
        week = "2026-01-05T00:00:00Z"
        rows = [
            split_row(f"E{i}", f"2026-01-{6+i:02d}T12:00:00Z", week)
            for i in range(6)
        ]
        forward = select_weekly_events(rows)
        reverse = select_weekly_events(list(reversed(rows)))
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward), MAX_EVENTS_PER_UTC_WEEK)
        self.assertEqual(len({row["utc_week_start"] for row in forward}), 1)

    def test_weekly_selection_ignores_embargoed_or_quarantined_rows(self):
        week = "2026-01-05T00:00:00Z"
        rows = [
            split_row("GOOD", "2026-01-06T12:00:00Z", week),
            split_row("BLOCKED", "2026-01-07T12:00:00Z", week, eligible=False),
        ]
        selected = select_weekly_events(rows)
        self.assertEqual([row["event_ticker"] for row in selected], ["GOOD"])

    def test_forbidden_outcome_field_in_split_input_fails_closed(self):
        row = split_row("E", "2026-01-06T12:00:00Z", "2026-01-05T00:00:00Z")
        row["outcome"] = 1
        with self.assertRaises(KxbtcdPreoutcomeMaterializationError):
            select_weekly_events([row])

    def test_structural_market_selection_returns_five_predeclared_positions(self):
        rows = [market("E", i) for i in range(10)]
        selected = select_structural_markets(rows, event_ticker="E")
        self.assertEqual(len(selected), 5)
        self.assertEqual(
            [row["structural_quantile"] for row in selected],
            [str(value) for value in STRUCTURAL_QUANTILES],
        )
        self.assertEqual([row["structural_role"] for row in selected], ["q10", "q30", "q50", "q70", "q90"])

    def test_structural_selection_is_independent_of_input_order(self):
        rows = [market("E", i) for i in range(10)]
        forward = select_structural_markets(rows, event_ticker="E")
        reverse = select_structural_markets(list(reversed(rows)), event_ticker="E")
        self.assertEqual(forward, reverse)

    def test_structural_selection_requires_five_distinct_greater_markets(self):
        with self.assertRaisesRegex(KxbtcdPreoutcomeMaterializationError, "at least 5"):
            select_structural_markets([market("E", i) for i in range(4)], event_ticker="E")
        rows = [market("E", i) for i in range(5)]
        rows[0]["strike_type"] = "less"
        with self.assertRaisesRegex(KxbtcdPreoutcomeMaterializationError, "strike_type='greater'"):
            select_structural_markets(rows, event_ticker="E")

    def test_anchor_selection_never_uses_future_quote(self):
        close = "2026-01-10T16:00:00Z"
        close_ts = int(datetime(2026, 1, 10, 16, tzinfo=timezone.utc).timestamp())
        anchor = 3300
        target = close_ts - anchor
        rows = [
            quote(target - 60, q="0.40"),
            quote(target, q="0.50"),
            quote(target + 1, q="0.90"),
        ]
        selected = select_anchor_observation(rows, close_time_utc=close, anchor_seconds=anchor)
        self.assertEqual(selected["selected_end_period_ts"], target)
        self.assertEqual(selected["midpoint"], "0.5")

    def test_anchor_selection_allows_at_most_sixty_seconds_staleness(self):
        close = "2026-01-10T16:00:00Z"
        close_ts = int(datetime(2026, 1, 10, 16, tzinfo=timezone.utc).timestamp())
        target = close_ts - 3300
        self.assertIsNotNone(
            select_anchor_observation([quote(target - 60)], close_time_utc=close, anchor_seconds=3300)
        )
        self.assertIsNone(
            select_anchor_observation([quote(target - 61)], close_time_utc=close, anchor_seconds=3300)
        )

    def test_anchor_selection_can_use_previous_valid_quote_when_target_quote_invalid(self):
        close = "2026-01-10T16:00:00Z"
        close_ts = int(datetime(2026, 1, 10, 16, tzinfo=timezone.utc).timestamp())
        target = close_ts - 1800
        selected = select_anchor_observation(
            [quote(target, valid=False), quote(target - 60, valid=True, q="0.44")],
            close_time_utc=close,
            anchor_seconds=1800,
        )
        self.assertEqual(selected["staleness_seconds"], 60)
        self.assertEqual(selected["midpoint"], "0.44")

    def test_only_frozen_time_to_close_anchors_are_allowed(self):
        self.assertEqual(
            TIME_TO_CLOSE_ANCHORS_SECONDS,
            (3300, 3000, 2700, 2400, 2100, 1800),
        )
        with self.assertRaisesRegex(KxbtcdPreoutcomeMaterializationError, "frozen anchor"):
            select_anchor_observation([], close_time_utc="2026-01-10T16:00:00Z", anchor_seconds=1234)

    def test_historical_state_is_offline_model_usable_but_not_live_causal(self):
        selected_market = select_structural_markets(
            [market("E", i) for i in range(10)], event_ticker="E"
        )[2]
        close = "2026-01-10T16:00:00Z"
        close_ts = int(datetime(2026, 1, 10, 16, tzinfo=timezone.utc).timestamp())
        target = close_ts - 3300
        selected_anchor = select_anchor_observation(
            [quote(target, q="0.52", raw_id="raw:historical:1")],
            close_time_utc=close,
            anchor_seconds=3300,
        )
        state = build_historical_reconstructed_state(
            selected_market=selected_market,
            selected_anchor=selected_anchor,
            close_time_utc=close,
            raw_receive_monotonic_ns=999,
            alignment_epoch_id="historical-run-1",
        )
        self.assertEqual(state["state_view"], "historical_reconstructed")
        self.assertEqual(state["product_context"]["time_to_close_seconds"], "3300")
        self.assertIn(selected_market["source_lineage_refs"][0], state["raw_observation_refs"])
        self.assertIn("raw:historical:1", state["raw_observation_refs"])
        validate_state_for_model_use(state)
        with self.assertRaises(BtcStateFeatureContractError):
            validate_state_for_live_causal_use(state)

    def test_selected_state_uses_actual_candle_time_not_nominal_anchor(self):
        selected_market = select_structural_markets(
            [market("E", i) for i in range(10)], event_ticker="E"
        )[2]
        close = "2026-01-10T16:00:00Z"
        close_ts = int(datetime(2026, 1, 10, 16, tzinfo=timezone.utc).timestamp())
        target = close_ts - 3300
        selected_anchor = select_anchor_observation(
            [quote(target - 60, q="0.52")], close_time_utc=close, anchor_seconds=3300
        )
        state = build_historical_reconstructed_state(
            selected_market=selected_market,
            selected_anchor=selected_anchor,
            close_time_utc=close,
            raw_receive_monotonic_ns=999,
            alignment_epoch_id="historical-run-1",
        )
        self.assertEqual(state["product_context"]["time_to_close_seconds"], "3360")


if __name__ == "__main__":
    unittest.main()

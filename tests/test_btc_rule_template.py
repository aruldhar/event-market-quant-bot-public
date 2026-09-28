from __future__ import annotations

import hashlib
import json
import unittest

from src.btc_rule_template import (
    BtcRuleTemplateError,
    extract_market_from_exact_raw_record,
    observed_regime_transitions,
    parse_rule_semantics,
    select_all_event_representatives,
    select_temporal_representatives,
    summarize_rule_regimes,
    validate_sample,
    validate_signature_stability,
    measurement_end_utc,
    settlement_primitive_id,
    validate_all_ladder_cluster_semantics,
)


KXBTC_60_TRIM_PRIMARY = (
    "If the average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
    "before 2 PM EST, excluding the top 20% and bottom 20% of values is between "
    "87750-87999.99 at 2 PM EST on Dec 24, 2024, then the market resolves to Yes."
)
KXBTC_60_TRIM_SECONDARY = (
    "The Contract is settled by taking an average of the sixty seconds of CF Benchmarks' "
    "Bitcoin Real-Time Index (BRTI) before 2 PM EST, excluding the top 20% and bottom 20% of values."
)
KXBTC_60_TRIM_BELOW_PRIMARY = (
    "If the average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
    "before 2 PM EST, excluding the top 20% and bottom 20% of values is below 87750 "
    "at 2 PM EST on Dec 24, 2024, then the market resolves to Yes."
)
KXBTC_60_TRIM_ABOVE_PRIMARY = (
    "If the average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
    "before 2 PM EST, excluding the top 20% and bottom 20% of values is above 88249.99 "
    "at 2 PM EST on Dec 24, 2024, then the market resolves to Yes."
)
KXBTC_300_TRIM_PRIMARY = (
    "If the price of Bitcoin is between 62500-62999.99 at 5 PM EDT on Oct 31, 2024, "
    "then the market resolves to Yes."
)
KXBTC_300_TRIM_SECONDARY = (
    "The Contract is settled by taking an average of the five minutes of CF Benchmarks' "
    "Bitcoin Real-Time Index (BRTI) before 5 PM EDT, excluding the top 20% and bottom 20% of values."
)
KXBTC_60_SIMPLE_PRIMARY = (
    "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
    "before 2 PM EST is between 77750-77999.99 at 2 PM EST on Dec 3, 2025, "
    "then the market resolves to Yes."
)
SIMPLE_SECONDARY = (
    "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase "
    "may help guide your decision, the price used to determine this market is based on CF Benchmarks' "
    "corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are "
    "collected. The official and final value is the average of these prices."
)
KXBTCD_60_TRIM_PRIMARY = (
    "If the average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
    "before 8 PM EST, excluding the top 20% and bottom 20% of values is above 100249.99 "
    "at 8 PM EST on Dec 19, 2024, then the market resolves to Yes."
)
KXBTCD_60_TRIM_SECONDARY = (
    "The Contract is settled by taking an average of the sixty seconds of CF Benchmarks' "
    "Bitcoin Real-Time Index (BRTI) before 8 PM EST, excluding the top 20% and bottom 20% of values."
)

KXBTC_60_TRIM_MODERN_SECONDARY = (
    "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase "
    "may help guide your decision, the price used to determine this market is based on CF Benchmarks' "
    "corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices arecollected. "
    "The official and final value is the average of these prices, excluding the top 20% (12) and bottom "
    "20% (12) of collected prices."
)

KXBTCD_60_SIMPLE_PRIMARY = (
    "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
    "before 5 PM EST is above 57999.99 at 5 PM EST on Feb 8, 2026, "
    "then the market resolves to Yes."
)


class RuleParserTests(unittest.TestCase):
    def test_kxbtc_five_minute_trimmed_regime(self):
        sig, clock, date = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_300_TRIM_PRIMARY,
            rules_secondary=KXBTC_300_TRIM_SECONDARY,
        )
        self.assertEqual(sig.window_seconds, 300)
        self.assertEqual(sig.statistic, "trimmed_mean")
        self.assertEqual(sig.trim_top_pct, 20)
        self.assertEqual(sig.payoff_relation, "between")
        self.assertEqual(clock, "5 pm edt")
        self.assertEqual(date, "Oct 31, 2024")

    def test_kxbtc_sixty_second_trimmed_regime(self):
        sig, clock, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_60_TRIM_PRIMARY,
            rules_secondary=KXBTC_60_TRIM_SECONDARY,
        )
        self.assertEqual(sig.window_seconds, 60)
        self.assertEqual(sig.statistic, "trimmed_mean")
        self.assertEqual(sig.regime_id, "brti_60s_trimmed_mean_trim20_20_between")
        self.assertEqual(clock, "2 pm est")

    def test_kxbtc_tail_relations_share_measurement_semantics(self):
        below, _, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_60_TRIM_BELOW_PRIMARY,
            rules_secondary=KXBTC_60_TRIM_SECONDARY,
            expected_relation="below",
        )
        between, _, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_60_TRIM_PRIMARY,
            rules_secondary=KXBTC_60_TRIM_SECONDARY,
            expected_relation="between",
        )
        above, _, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_60_TRIM_ABOVE_PRIMARY,
            rules_secondary=KXBTC_60_TRIM_SECONDARY,
            expected_relation="above",
        )
        self.assertEqual(below.payoff_relation, "below")
        self.assertEqual(between.payoff_relation, "between")
        self.assertEqual(above.payoff_relation, "above")
        self.assertEqual(
            (below.window_seconds, below.statistic, below.trim_top_pct, below.trim_bottom_pct),
            (between.window_seconds, between.statistic, between.trim_top_pct, between.trim_bottom_pct),
        )
        self.assertEqual(
            (above.window_seconds, above.statistic, above.trim_top_pct, above.trim_bottom_pct),
            (between.window_seconds, between.statistic, between.trim_top_pct, between.trim_bottom_pct),
        )

    def test_kxbtc_sixty_second_trimmed_modern_secondary_wording(self):
        sig, clock, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=(
                "If the average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) "
                "before 5 PM EST, excluding the top 20% and bottom 20% of values is between "
                "99750-100249.99 at 5 PM EST on Feb 6, 2025, then the market resolves to Yes."
            ),
            rules_secondary=KXBTC_60_TRIM_MODERN_SECONDARY,
        )
        self.assertEqual(sig.window_seconds, 60)
        self.assertEqual(sig.statistic, "trimmed_mean")
        self.assertEqual(sig.trim_top_pct, 20)
        self.assertEqual(sig.trim_bottom_pct, 20)
        self.assertEqual(sig.regime_id, "brti_60s_trimmed_mean_trim20_20_between")
        self.assertEqual(clock, "5 pm est")

    def test_modern_trimmed_secondary_wrong_percentage_fails_closed(self):
        with self.assertRaises(BtcRuleTemplateError):
            parse_rule_semantics(
                series_ticker="KXBTC",
                rules_primary=KXBTC_60_TRIM_PRIMARY,
                rules_secondary=KXBTC_60_TRIM_MODERN_SECONDARY.replace("top 20% (12)", "top 25% (15)"),
            )

    def test_kxbtc_sixty_second_simple_regime(self):
        sig, clock, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_60_SIMPLE_PRIMARY,
            rules_secondary=SIMPLE_SECONDARY,
        )
        self.assertEqual(sig.window_seconds, 60)
        self.assertEqual(sig.statistic, "simple_mean")
        self.assertEqual(sig.trim_top_pct, 0)
        self.assertEqual(sig.trim_bottom_pct, 0)
        self.assertEqual(clock, "2 pm est")

    def test_kxbtcd_trimmed_and_simple_are_distinct_regimes(self):
        old, _, _ = parse_rule_semantics(
            series_ticker="KXBTCD",
            rules_primary=KXBTCD_60_TRIM_PRIMARY,
            rules_secondary=KXBTCD_60_TRIM_SECONDARY,
        )
        new, _, _ = parse_rule_semantics(
            series_ticker="KXBTCD",
            rules_primary=KXBTCD_60_SIMPLE_PRIMARY,
            rules_secondary=SIMPLE_SECONDARY,
        )
        self.assertNotEqual(old, new)
        self.assertEqual(old.payoff_relation, "above")
        self.assertEqual(new.payoff_relation, "above")

    def test_dynamic_time_and_strike_do_not_change_simple_signature(self):
        a, _, _ = parse_rule_semantics(
            series_ticker="KXBTCD",
            rules_primary=KXBTCD_60_SIMPLE_PRIMARY,
            rules_secondary=SIMPLE_SECONDARY,
        )
        b, _, _ = parse_rule_semantics(
            series_ticker="KXBTCD",
            rules_primary=(
                KXBTCD_60_SIMPLE_PRIMARY
                .replace("5 PM EST", "1 PM EDT")
                .replace("57999.99", "123456.78")
                .replace("Feb 8, 2026", "Aug 1, 2026")
            ),
            rules_secondary=SIMPLE_SECONDARY,
        )
        self.assertEqual(a, b)

    def test_unrecognized_window_fails_closed(self):
        with self.assertRaises(BtcRuleTemplateError):
            parse_rule_semantics(
                series_ticker="KXBTC",
                rules_primary=KXBTC_300_TRIM_PRIMARY,
                rules_secondary=KXBTC_300_TRIM_SECONDARY.replace("five minutes", "ten minutes"),
            )

    def test_clock_disagreement_fails_closed(self):
        with self.assertRaises(BtcRuleTemplateError):
            parse_rule_semantics(
                series_ticker="KXBTC",
                rules_primary=KXBTC_300_TRIM_PRIMARY,
                rules_secondary=KXBTC_300_TRIM_SECONDARY.replace("5 PM EDT", "6 PM EDT"),
            )


class TemporalSelectionTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for i in range(5):
            rows.extend([
                {
                    "series_ticker": "KXBTC",
                    "event_ticker": f"E{i}",
                    "ticker": f"M{i}B",
                    "close_time": f"2026-01-0{i+1}T00:00:00Z",
                },
                {
                    "series_ticker": "KXBTC",
                    "event_ticker": f"E{i}",
                    "ticker": f"M{i}A",
                    "close_time": f"2026-01-0{i+1}T00:00:00Z",
                },
            ])
        return rows

    def test_selects_one_market_from_every_sampled_event(self):
        picked = select_all_event_representatives(self._rows(), series_ticker="KXBTC")
        self.assertEqual(len(picked), 5)
        self.assertEqual([row["ticker"] for _, row in picked], [f"M{i}A" for i in range(5)])

    def test_selects_distinct_early_middle_late_events(self):
        picked = select_temporal_representatives(self._rows(), series_ticker="KXBTC")
        self.assertEqual(
            [(label, row["event_ticker"]) for label, row in picked],
            [("early", "E0"), ("middle", "E2"), ("late", "E4")],
        )


class RawLineageTests(unittest.TestCase):
    def test_extracts_market_only_from_exact_raw_request(self):
        records = [
            {
                "request": {"request_id": "r1"},
                "response": {
                    "status_code": 200,
                    "body_text": json.dumps({"markets": [{"ticker": "M1"}, {"ticker": "M2"}]}),
                },
            },
            {
                "request": {"request_id": "r2"},
                "response": {"status_code": 200, "body_text": json.dumps({"markets": [{"ticker": "M1"}]})},
            },
        ]
        market = extract_market_from_exact_raw_record(records, raw_request_id="r1", market_ticker="M2")
        self.assertEqual(market["ticker"], "M2")

    def test_missing_exact_raw_request_fails_closed(self):
        with self.assertRaises(BtcRuleTemplateError):
            extract_market_from_exact_raw_record([], raw_request_id="missing", market_ticker="M")

    def test_validate_sample_reports_exact_offending_rule_context(self):
        bad_primary = KXBTC_60_SIMPLE_PRIMARY.replace("sixty seconds", "ninety seconds")
        row = {
            "ticker": "M-BAD",
            "event_ticker": "E-BAD",
            "close_time": "2025-12-03T19:00:00Z",
            "raw_source": "kalshi_public_rest",
            "raw_session_id": "s",
            "raw_request_id": "r",
            "route_tier": "historical",
            "strike_type": "between",
            "rules_primary_sha256": hashlib.sha256(bad_primary.encode()).hexdigest(),
            "rules_secondary_sha256": hashlib.sha256(SIMPLE_SECONDARY.encode()).hexdigest(),
        }
        with self.assertRaises(BtcRuleTemplateError) as caught:
            validate_sample(
                series_ticker="KXBTC",
                sample_position="event_007",
                derived_row=row,
                raw_market={
                    "ticker": "M-BAD",
                    "event_ticker": "E-BAD",
                    "rules_primary": bad_primary,
                    "rules_secondary": SIMPLE_SECONDARY,
                },
            )
        message = str(caught.exception)
        self.assertIn("ticker=M-BAD", message)
        self.assertIn("event=E-BAD", message)
        self.assertIn("position=event_007", message)
        self.assertIn("RULES_PRIMARY:", message)
        self.assertIn("ninety seconds", message)
        self.assertIn("RULES_SECONDARY:", message)

    def test_validate_sample_checks_hash_lineage(self):
        row = {
            "ticker": "M",
            "event_ticker": "E",
            "close_time": "2024-10-31T21:00:00Z",
            "raw_source": "kalshi_public_rest",
            "raw_session_id": "s",
            "raw_request_id": "r",
            "route_tier": "historical",
            "strike_type": "between",
            "rules_primary_sha256": hashlib.sha256(KXBTC_300_TRIM_PRIMARY.encode()).hexdigest(),
            "rules_secondary_sha256": hashlib.sha256(KXBTC_300_TRIM_SECONDARY.encode()).hexdigest(),
        }
        sample = validate_sample(
            series_ticker="KXBTC",
            sample_position="event_001",
            derived_row=row,
            raw_market={
                "ticker": "M",
                "event_ticker": "E",
                "rules_primary": KXBTC_300_TRIM_PRIMARY,
                "rules_secondary": KXBTC_300_TRIM_SECONDARY,
            },
        )
        self.assertEqual(sample.signature.window_seconds, 300)
        self.assertNotIn("result", sample.as_json())


class RegimeSummaryTests(unittest.TestCase):
    def _sample(self, *, event: str, close: str, primary: str, secondary: str):
        row = {
            "ticker": f"M-{event}",
            "event_ticker": event,
            "close_time": close,
            "raw_source": "kalshi_public_rest",
            "raw_session_id": "s",
            "raw_request_id": f"r-{event}",
            "route_tier": "historical",
            "strike_type": "between",
            "rules_primary_sha256": hashlib.sha256(primary.encode()).hexdigest(),
            "rules_secondary_sha256": hashlib.sha256(secondary.encode()).hexdigest(),
        }
        return validate_sample(
            series_ticker="KXBTC",
            sample_position=event,
            derived_row=row,
            raw_market={
                "ticker": f"M-{event}",
                "event_ticker": event,
                "rules_primary": primary,
                "rules_secondary": secondary,
            },
        )

    def test_multiple_regimes_are_reported_not_collapsed(self):
        old = self._sample(
            event="E1",
            close="2024-10-31T21:00:00Z",
            primary=KXBTC_300_TRIM_PRIMARY,
            secondary=KXBTC_300_TRIM_SECONDARY,
        )
        mid = self._sample(
            event="E2",
            close="2024-12-24T19:00:00Z",
            primary=KXBTC_60_TRIM_PRIMARY,
            secondary=KXBTC_60_TRIM_SECONDARY,
        )
        new = self._sample(
            event="E3",
            close="2025-12-03T19:00:00Z",
            primary=KXBTC_60_SIMPLE_PRIMARY,
            secondary=SIMPLE_SECONDARY,
        )
        regimes = summarize_rule_regimes([old, mid, new])
        self.assertEqual(len(regimes), 3)
        transitions = observed_regime_transitions([old, mid, new])
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[0]["last_observed_from_event_ticker"], "E1")
        self.assertEqual(transitions[0]["first_observed_to_event_ticker"], "E2")

    def test_stability_still_fails_when_regimes_differ(self):
        old = self._sample(
            event="E1",
            close="2024-10-31T21:00:00Z",
            primary=KXBTC_300_TRIM_PRIMARY,
            secondary=KXBTC_300_TRIM_SECONDARY,
        )
        new = self._sample(
            event="E2",
            close="2025-12-03T19:00:00Z",
            primary=KXBTC_60_SIMPLE_PRIMARY,
            secondary=SIMPLE_SECONDARY,
        )
        with self.assertRaises(BtcRuleTemplateError):
            validate_signature_stability([old, new])

    def test_cross_series_regime_summary_fails_closed(self):
        old = self._sample(
            event="E1",
            close="2024-10-31T21:00:00Z",
            primary=KXBTC_300_TRIM_PRIMARY,
            secondary=KXBTC_300_TRIM_SECONDARY,
        )
        other = old.__class__(**{**old.__dict__, "series_ticker": "KXBTCD"})
        with self.assertRaises(BtcRuleTemplateError):
            summarize_rule_regimes([old, other])


class ClusterSemanticTests(unittest.TestCase):
    def _row(self, *, ticker, event, close, request_id, cluster_id, primary, secondary, strike_type="between"):
        return {
            "series_ticker": "KXBTC",
            "ticker": ticker,
            "event_ticker": event,
            "close_time": close,
            "raw_source": "kalshi_public_rest",
            "raw_session_id": "s",
            "raw_request_id": request_id,
            "route_tier": "historical",
            "strike_type": strike_type,
            "rules_primary_sha256": hashlib.sha256(primary.encode()).hexdigest(),
            "rules_secondary_sha256": hashlib.sha256(secondary.encode()).hexdigest(),
            "settlement_cluster_id": cluster_id,
        }

    def _raw(self, request_id, markets):
        return {
            "request": {"request_id": request_id},
            "response": {"status_code": 200, "body_text": json.dumps({"markets": markets})},
        }

    def test_explicit_est_rule_clock_maps_to_close_utc(self):
        self.assertEqual(
            measurement_end_utc(measurement_clock_label="5 PM EST", settlement_date_label="Dec 3, 2025"),
            "2025-12-03T22:00:00Z",
        )

    def test_explicit_edt_rule_clock_maps_to_close_utc(self):
        self.assertEqual(
            measurement_end_utc(measurement_clock_label="2 PM EDT", settlement_date_label="Jul 30, 2026"),
            "2026-07-30T18:00:00Z",
        )

    def test_primitive_id_depends_on_measurement_end(self):
        sig, _, _ = parse_rule_semantics(
            series_ticker="KXBTC",
            rules_primary=KXBTC_60_SIMPLE_PRIMARY,
            rules_secondary=SIMPLE_SECONDARY,
        )
        a = settlement_primitive_id(signature=sig, measurement_end_utc_value="2025-12-03T19:00:00Z")
        b = settlement_primitive_id(signature=sig, measurement_end_utc_value="2025-12-03T20:00:00Z")
        self.assertNotEqual(a, b)

    def test_all_kxbtc_payoff_shapes_in_event_resolve_to_one_primitive(self):
        p_below = KXBTC_60_TRIM_BELOW_PRIMARY
        p_between = KXBTC_60_TRIM_PRIMARY
        p_above = KXBTC_60_TRIM_ABOVE_PRIMARY
        rows = [
            self._row(ticker="M0", event="E", close="2024-12-24T19:00:00Z", request_id="r", cluster_id="c", primary=p_below, secondary=KXBTC_60_TRIM_SECONDARY, strike_type="less"),
            self._row(ticker="M1", event="E", close="2024-12-24T19:00:00Z", request_id="r", cluster_id="c", primary=p_between, secondary=KXBTC_60_TRIM_SECONDARY, strike_type="between"),
            self._row(ticker="M2", event="E", close="2024-12-24T19:00:00Z", request_id="r", cluster_id="c", primary=p_above, secondary=KXBTC_60_TRIM_SECONDARY, strike_type="greater"),
        ]
        raw = [self._raw("r", [
            {"ticker":"M0","event_ticker":"E","rules_primary":p_below,"rules_secondary":KXBTC_60_TRIM_SECONDARY},
            {"ticker":"M1","event_ticker":"E","rules_primary":p_between,"rules_secondary":KXBTC_60_TRIM_SECONDARY},
            {"ticker":"M2","event_ticker":"E","rules_primary":p_above,"rules_secondary":KXBTC_60_TRIM_SECONDARY},
        ])]
        result = validate_all_ladder_cluster_semantics(rows, raw, series_tickers=("KXBTC",))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].market_count, 3)
        self.assertEqual(result[0].regime_id, "brti_60s_trimmed_mean_trim20_20")
        self.assertEqual(result[0].payoff_relations, ("above", "below", "between"))
        self.assertNotIn("payoff_relation", result[0].as_json()["measurement_signature"])


    def test_missing_strike_type_uses_unique_primary_rule_relation(self):
        row = self._row(
            ticker="M", event="E", close="2024-12-24T19:00:00Z", request_id="r",
            cluster_id="c", primary=KXBTC_60_TRIM_PRIMARY, secondary=KXBTC_60_TRIM_SECONDARY,
            strike_type="",
        )
        raw = [self._raw("r", [{
            "ticker":"M", "event_ticker":"E",
            "rules_primary":KXBTC_60_TRIM_PRIMARY,
            "rules_secondary":KXBTC_60_TRIM_SECONDARY,
        }])]
        result = validate_all_ladder_cluster_semantics([row], raw, series_tickers=("KXBTC",))
        self.assertEqual(result[0].payoff_relations, ("between",))

    def test_raw_strike_type_must_agree_with_primary_rule_relation(self):
        row = self._row(
            ticker="M", event="E", close="2024-12-24T19:00:00Z", request_id="r",
            cluster_id="c", primary=KXBTC_60_TRIM_PRIMARY, secondary=KXBTC_60_TRIM_SECONDARY,
            strike_type="",
        )
        raw = [self._raw("r", [{
            "ticker":"M", "event_ticker":"E", "strike_type":"less",
            "rules_primary":KXBTC_60_TRIM_PRIMARY,
            "rules_secondary":KXBTC_60_TRIM_SECONDARY,
        }])]
        with self.assertRaises(BtcRuleTemplateError):
            validate_all_ladder_cluster_semantics([row], raw, series_tickers=("KXBTC",))

    def test_strike_type_must_match_supported_payoff_relation(self):
        row = self._row(
            ticker="M", event="E", close="2024-12-24T19:00:00Z", request_id="r",
            cluster_id="c", primary=KXBTC_60_TRIM_PRIMARY, secondary=KXBTC_60_TRIM_SECONDARY,
            strike_type="custom",
        )
        raw = [self._raw("r", [{"ticker":"M","event_ticker":"E","rules_primary":KXBTC_60_TRIM_PRIMARY,"rules_secondary":KXBTC_60_TRIM_SECONDARY}])]
        with self.assertRaises(BtcRuleTemplateError):
            validate_all_ladder_cluster_semantics([row], raw, series_tickers=("KXBTC",))

    def test_event_with_mixed_regimes_fails_closed(self):
        p_trim = KXBTC_60_TRIM_PRIMARY
        p_simple = KXBTC_60_SIMPLE_PRIMARY.replace("Dec 3, 2025", "Dec 24, 2024")
        rows = [
            self._row(ticker="M1", event="E", close="2024-12-24T19:00:00Z", request_id="r", cluster_id="c", primary=p_trim, secondary=KXBTC_60_TRIM_SECONDARY),
            self._row(ticker="M2", event="E", close="2024-12-24T19:00:00Z", request_id="r", cluster_id="c", primary=p_simple, secondary=SIMPLE_SECONDARY),
        ]
        raw = [self._raw("r", [
            {"ticker":"M1","event_ticker":"E","rules_primary":p_trim,"rules_secondary":KXBTC_60_TRIM_SECONDARY},
            {"ticker":"M2","event_ticker":"E","rules_primary":p_simple,"rules_secondary":SIMPLE_SECONDARY},
        ])]
        with self.assertRaises(BtcRuleTemplateError):
            validate_all_ladder_cluster_semantics(rows, raw, series_tickers=("KXBTC",))

    def test_rule_clock_mismatch_with_derived_close_fails_closed(self):
        row = self._row(ticker="M", event="E", close="2024-12-24T20:00:00Z", request_id="r", cluster_id="c", primary=KXBTC_60_TRIM_PRIMARY, secondary=KXBTC_60_TRIM_SECONDARY)
        raw = [self._raw("r", [{"ticker":"M","event_ticker":"E","rules_primary":KXBTC_60_TRIM_PRIMARY,"rules_secondary":KXBTC_60_TRIM_SECONDARY}])]
        with self.assertRaises(BtcRuleTemplateError):
            validate_all_ladder_cluster_semantics([row], raw, series_tickers=("KXBTC",))


if __name__ == "__main__":
    unittest.main()

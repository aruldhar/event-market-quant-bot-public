from __future__ import annotations

from datetime import datetime, timedelta, timezone
import random
import unittest

from src.kxbtcd_chronological_split_contract import (
    CHECKPOINT10_SOURCE_EVENT_COUNT,
    EMBARGO_HOURS,
    EVENT_UNIT_FIELDS,
    EXPERIMENT_FAMILY_ID,
    FORBIDDEN_PREOUTCOME_FIELDS,
    KxbtcdChronologicalSplitError,
    PARTITIONS,
    SPLIT_ROW_FIELDS,
    build_chronological_split,
    design_fingerprint,
    frozen_split_contract,
    partition_week_counts,
    split_summary,
    utc_week_start,
    validate_split_contract,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event(index: int, close_dt: datetime, *, primitive: str | None = None) -> dict[str, object]:
    return {
        "event_ticker": f"NEW-{index:04d}",
        "close_time_utc": _iso(close_dt),
        "settlement_regime_id": "brti_60s_simple_mean_untrimmed",
        "settlement_primitive_ids": [primitive or f"primitive-new-{index:04d}"],
        "source_lineage_refs": [f"raw-ref-{index:04d}"],
    }


def _quarantine() -> tuple[list[str], list[str]]:
    return (
        [f"OLD-{i:02d}" for i in range(CHECKPOINT10_SOURCE_EVENT_COUNT)],
        [f"primitive-old-{i:02d}" for i in range(CHECKPOINT10_SOURCE_EVENT_COUNT)],
    )


def _weekly_universe(weeks: int = 25, per_week: int = 2) -> list[dict[str, object]]:
    monday = datetime(2026, 2, 23, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    idx = 0
    for week in range(weeks):
        for offset_hours in (1, 48)[:per_week]:
            rows.append(_event(idx, monday + timedelta(weeks=week, hours=offset_hours)))
            idx += 1
    return rows


class KxbtcdChronologicalSplitContractTests(unittest.TestCase):
    def test_contract_validates_and_is_distinct_from_checkpoint10(self) -> None:
        validate_split_contract()
        self.assertEqual(
            design_fingerprint(),
            "fc3d7303afb259fc7b39a2657240835a0dd4a4c1b7a7c7b99bbf258f162f3cd4",
        )
        self.assertEqual(
            frozen_split_contract()["experiment_family_id"],
            EXPERIMENT_FAMILY_ID,
        )
        self.assertNotEqual(
            frozen_split_contract()["checkpoint10_quarantine"]["experiment_id"],
            EXPERIMENT_FAMILY_ID,
        )

    def test_preoutcome_schemas_forbid_labels_outputs_economics_and_decisions(self) -> None:
        self.assertFalse(FORBIDDEN_PREOUTCOME_FIELDS.intersection(EVENT_UNIT_FIELDS))
        self.assertFalse(FORBIDDEN_PREOUTCOME_FIELDS.intersection(SPLIT_ROW_FIELDS))

    def test_event_with_label_field_is_rejected(self) -> None:
        event = _weekly_universe(5, 1)[0]
        event["label"] = 1
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "forbidden pre-outcome"):
            build_chronological_split(
                [event, *_weekly_universe(5, 1)[1:]],
                checkpoint10_event_tickers=q_events,
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_checkpoint10_quarantine_requires_all_twenty_source_events(self) -> None:
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "exactly 20"):
            build_chronological_split(
                _weekly_universe(),
                checkpoint10_event_tickers=q_events[:-1],
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_checkpoint10_event_and_primitive_overlap_are_quarantined(self) -> None:
        events = _weekly_universe()
        q_events, q_primitives = _quarantine()
        events[0]["event_ticker"] = q_events[0]
        events[1]["settlement_primitive_ids"] = [q_primitives[0]]
        rows = build_chronological_split(
            events,
            checkpoint10_event_tickers=q_events,
            checkpoint10_primitive_ids=q_primitives,
        )
        by_ticker = {row["event_ticker"]: row for row in rows}
        self.assertEqual(by_ticker[q_events[0]]["partition"], "quarantine")
        self.assertEqual(by_ticker[q_events[0]]["exclusion_reason"], "checkpoint10_event_quarantine")
        primitive_row = next(
            row for row in rows if q_primitives[0] in row["settlement_primitive_ids"] and row["event_ticker"] != q_events[0]
        )
        self.assertEqual(primitive_row["partition"], "quarantine")
        self.assertEqual(primitive_row["exclusion_reason"], "checkpoint10_primitive_quarantine")

    def test_25_week_split_is_15_5_5(self) -> None:
        self.assertEqual(partition_week_counts(25), (15, 5, 5))

    def test_whole_utc_weeks_never_cross_partitions(self) -> None:
        q_events, q_primitives = _quarantine()
        rows = build_chronological_split(
            _weekly_universe(25, 2),
            checkpoint10_event_tickers=q_events,
            checkpoint10_primitive_ids=q_primitives,
        )
        partitions_by_week: dict[str, set[str]] = {}
        for row in rows:
            if row["partition"] in PARTITIONS:
                partitions_by_week.setdefault(row["utc_week_start"], set()).add(row["partition"])
        self.assertTrue(partitions_by_week)
        self.assertTrue(all(len(parts) == 1 for parts in partitions_by_week.values()))
        self.assertEqual(
            {part: sum(1 for parts in partitions_by_week.values() if part in parts) for part in PARTITIONS},
            {"train": 15, "validation": 5, "locked_test": 5},
        )

    def test_first_24_hours_of_validation_and_locked_test_are_embargoed(self) -> None:
        q_events, q_primitives = _quarantine()
        rows = build_chronological_split(
            _weekly_universe(25, 2),
            checkpoint10_event_tickers=q_events,
            checkpoint10_primitive_ids=q_primitives,
        )
        for partition in ("validation", "locked_test"):
            partition_rows = [row for row in rows if row["partition"] == partition]
            first_week = min(row["utc_week_start"] for row in partition_rows)
            first_week_dt = datetime.fromisoformat(first_week.replace("Z", "+00:00"))
            early = [
                row
                for row in partition_rows
                if datetime.fromisoformat(row["close_time_utc"].replace("Z", "+00:00"))
                < first_week_dt + timedelta(hours=EMBARGO_HOURS)
            ]
            late = [
                row
                for row in partition_rows
                if datetime.fromisoformat(row["close_time_utc"].replace("Z", "+00:00"))
                >= first_week_dt + timedelta(hours=EMBARGO_HOURS)
            ]
            self.assertTrue(early)
            self.assertTrue(late)
            self.assertTrue(all(row["embargoed"] for row in early))
            self.assertTrue(all(not row["eligible_for_modeling"] for row in early))
            self.assertTrue(all(not row["embargoed"] for row in late))

    def test_locked_test_is_latest_chronological_block(self) -> None:
        q_events, q_primitives = _quarantine()
        rows = build_chronological_split(
            _weekly_universe(),
            checkpoint10_event_tickers=q_events,
            checkpoint10_primitive_ids=q_primitives,
        )
        max_validation = max(row["close_time_utc"] for row in rows if row["partition"] == "validation")
        min_test = min(row["close_time_utc"] for row in rows if row["partition"] == "locked_test")
        self.assertLess(max_validation, min_test)

    def test_same_primitive_cannot_leak_across_partitions(self) -> None:
        events = _weekly_universe(25, 1)
        events[0]["settlement_primitive_ids"] = ["shared-primitive"]
        events[-1]["settlement_primitive_ids"] = ["shared-primitive"]
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "primitive leakage"):
            build_chronological_split(
                events,
                checkpoint10_event_tickers=q_events,
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_input_order_does_not_change_split_or_fingerprint(self) -> None:
        events = _weekly_universe()
        q_events, q_primitives = _quarantine()
        forward = build_chronological_split(
            events,
            checkpoint10_event_tickers=q_events,
            checkpoint10_primitive_ids=q_primitives,
        )
        shuffled = list(events)
        random.Random(42).shuffle(shuffled)
        reordered = build_chronological_split(
            shuffled,
            checkpoint10_event_tickers=list(reversed(q_events)),
            checkpoint10_primitive_ids=list(reversed(q_primitives)),
        )
        self.assertEqual(forward, reordered)
        self.assertEqual(forward[0]["split_fingerprint"], reordered[0]["split_fingerprint"])

    def test_duplicate_event_ticker_is_rejected(self) -> None:
        events = _weekly_universe()
        events.append(dict(events[0]))
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "duplicate event_ticker"):
            build_chronological_split(
                events,
                checkpoint10_event_tickers=q_events,
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_non_utc_close_time_is_rejected(self) -> None:
        events = _weekly_universe()
        events[0]["close_time_utc"] = "2026-02-23T01:00:00-05:00"
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "timezone-aware UTC"):
            build_chronological_split(
                events,
                checkpoint10_event_tickers=q_events,
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_wrong_settlement_regime_is_rejected(self) -> None:
        events = _weekly_universe()
        events[0]["settlement_regime_id"] = "legacy_or_unknown"
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "outside frozen settlement regime"):
            build_chronological_split(
                events,
                checkpoint10_event_tickers=q_events,
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_too_few_weeks_fail_closed(self) -> None:
        q_events, q_primitives = _quarantine()
        with self.assertRaisesRegex(KxbtcdChronologicalSplitError, "at least 5"):
            build_chronological_split(
                _weekly_universe(4, 1),
                checkpoint10_event_tickers=q_events,
                checkpoint10_primitive_ids=q_primitives,
            )

    def test_utc_week_starts_monday_midnight(self) -> None:
        self.assertEqual(
            utc_week_start("2026-08-14T07:30:00Z"),
            "2026-08-10T00:00:00Z",
        )

    def test_split_summary_is_outcome_blind_and_counts_eligible_rows(self) -> None:
        q_events, q_primitives = _quarantine()
        rows = build_chronological_split(
            _weekly_universe(),
            checkpoint10_event_tickers=q_events,
            checkpoint10_primitive_ids=q_primitives,
        )
        summary = split_summary(rows)
        self.assertEqual(summary["unique_week_counts"], {"train": 15, "validation": 5, "locked_test": 5})
        self.assertGreater(summary["embargoed_event_count"], 0)
        self.assertEqual(summary["design_fingerprint"], design_fingerprint())
        self.assertTrue(summary["split_fingerprint"])


if __name__ == "__main__":
    unittest.main()

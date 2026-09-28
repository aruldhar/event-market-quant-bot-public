from __future__ import annotations

from collections import Counter
import math

import pytest

from src.kxbtcd_candidate_e_entry_model_v1 import event_equal_weights


def test_event_equal_weights_accept_real_development_scale_without_false_precision_failure():
    """Regression for the 2,570-event / 76,419-row Checkpoint-21M failure.

    The scientific weight formula is unchanged: every event has total mass 1/E,
    split equally across that event's rows.  The function's invariant check must
    not reject a correct vector merely because ordinary sequential float summation
    accumulates more than 1e-12 rounding error at this scale.
    """
    event_count = 2570
    total_rows = 76419
    base_rows_per_event = total_rows // event_count  # 29
    remainder = total_rows - base_rows_per_event * event_count  # 1889

    rows: list[dict[str, str]] = []
    for index in range(event_count):
        count = base_rows_per_event + (1 if index < remainder else 0)
        event = f"E{index:04d}"
        rows.extend({"event_ticker": event} for _ in range(count))

    weights = event_equal_weights(rows)

    assert len(weights) == total_rows
    assert math.fsum(weights) == 1.0

    row_counts = Counter(row["event_ticker"] for row in rows)
    offsets: dict[str, list[float]] = {}
    for row, weight in zip(rows, weights):
        offsets.setdefault(row["event_ticker"], []).append(weight)

    expected_event_mass = 1.0 / event_count
    for event in ("E0000", f"E{remainder - 1:04d}", f"E{remainder:04d}", f"E{event_count - 1:04d}"):
        assert len(offsets[event]) == row_counts[event]
        assert math.fsum(offsets[event]) == pytest.approx(expected_event_mass, rel=0.0, abs=1e-18)

from decimal import Decimal

import pytest

from src.predexon_segment_safe_replay import (
    apply_delta,
    build_verified_segments,
    mismatch_count,
    reconcile_pair,
    sequence_reset,
)


def snap(ts, seq, bids, asks, source="websocket"):
    return {
        "timestamp": ts,
        "sequence": seq,
        "source": source,
        "yes_bids": [{"price": str(p), "size": str(q)} for p, q in bids],
        "yes_asks": [{"price": str(p), "size": str(q)} for p, q in asks],
    }


def row(ts, seq, price, delta, side):
    return {
        "timestamp": ts,
        "sequence": seq,
        "price_dollars": str(price),
        "delta_fp": str(delta),
        "side": side,
    }


def test_no_side_maps_to_complementary_yes_ask():
    bids = {}
    asks = {Decimal("0.22"): Decimal("350")}
    apply_delta(bids, asks, row(1, 1, "0.78", "-100", "no"))
    assert asks[Decimal("0.22")] == Decimal("250")


def test_paid_delta_negative_size_fails_closed_without_epsilon_repair():
    bids = {Decimal("0.14"): Decimal("1")}
    asks = {}
    with pytest.raises(ValueError, match="negative resting size"):
        apply_delta(bids, asks, row(1, 1, "0.14", "-1.0000000001", "yes"))


def test_epsilon_ignores_snapshot_float_serialization_noise():
    actual = {Decimal("0.71"): Decimal("353.13")}
    expected = {Decimal("0.71"): Decimal("353.1300000000001")}
    assert mismatch_count(actual, expected) == 0


def test_adjacent_replay_allows_partial_end_timestamp_batch():
    a = snap(1000, 10, [(14, "434.25"), (11, "3500")], [(21, "1550"), (22, "350")])
    b = snap(1143, 11, [(14, "433.25"), (11, "3500")], [(21, "1550"), (22, "350")])
    rows = [
        row(1143, 100, "0.14", "-1", "yes"),
        row(1143, 101, "0.11", "1", "yes"),
        row(1143, 102, "0.78", "-100", "no"),
        row(1143, 103, "0.79", "100", "no"),
    ]
    result = reconcile_pair(a, b, rows)
    assert result.exact
    assert result.end_cut == 1


def test_sequence_decrease_is_detected_as_diagnostic_metadata():
    a = snap(1000, 39655, [], [])
    b = snap(2000, 130, [], [])
    assert sequence_reset(a, b)


def test_exact_sequence_decrease_does_not_cut_segment():
    s0 = snap(1000, 1000, [(14, "10")], [(15, "20")], source="live_early")
    s1 = snap(1100, 5, [(14, "9")], [(15, "20")], source="websocket")
    rows01 = [row(1100, 100, "0.14", "-1", "yes")]

    segments, results = build_verified_segments([s0, s1], [rows01])

    assert sequence_reset(s0, s1)
    assert results[0].exact
    assert len(segments) == 1
    assert segments[0].start_snapshot_index == 0
    assert segments[0].end_snapshot_index == 1
    assert segments[0].pair_count == 1
    assert segments[0].exact_pair_count == 1
    assert segments[0].boundary_reason == "end_of_evidence"


def test_unreconciled_sequence_decrease_cuts_segment_because_replay_fails():
    s0 = snap(1000, 10, [(14, "10")], [(15, "20")])
    s1 = snap(1100, 11, [(14, "9")], [(15, "20")])
    s2 = snap(2000, 1, [(13, "5")], [(14, "8")])

    rows01 = [row(1100, 100, "0.14", "-1", "yes")]
    rows12 = []

    segments, results = build_verified_segments([s0, s1, s2], [rows01, rows12])

    assert results[0].exact
    assert sequence_reset(s1, s2)
    assert not results[1].exact
    assert len(segments) == 2
    assert segments[0].start_snapshot_index == 0
    assert segments[0].end_snapshot_index == 1
    assert segments[0].boundary_reason == "unreconciled_adjacent_snapshot_pair"
    assert segments[1].start_snapshot_index == 2


def test_unreconciled_pair_ends_segment_without_sequence_decrease():
    s0 = snap(1000, 10, [(14, "10")], [(15, "20")])
    s1 = snap(1100, 11, [(14, "7")], [(15, "20")])

    segments, results = build_verified_segments([s0, s1], [[]])

    assert not sequence_reset(s0, s1)
    assert not results[0].exact
    assert segments[0].boundary_reason == "unreconciled_adjacent_snapshot_pair"

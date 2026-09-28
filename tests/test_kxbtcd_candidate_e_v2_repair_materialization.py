from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_v2_disk_timeline import DiskTimeline
from src.kxbtcd_candidate_e_v2_repair_materialization import (
    RepairMaterializationError,
    build_repair_timeline,
    build_repaired_edge_specs,
    compose_snapshot_order,
    edge_overrides,
    paid_row_key,
    selected_rows_for_cuts,
    validate_repair_cache,
)


def snap(ts, size="1"):
    return {
        "timestamp": ts,
        "sequence": ts,
        "source": "synthetic",
        "yes_bids": [{"price": "50", "size": size}],
        "yes_asks": [],
    }


def report(failed):
    return {
        "remaining_unreconciled_pairs": [
            {"pair_index": i, "start_timestamp_ms": 0, "end_timestamp_ms": 0, "result": {}}
            for i in failed
        ]
    }


def repair(*, rid="R1", context, addressed, order, cuts, kind="quarantine"):
    return {
        "source": "TEST",
        "ticker": "M1",
        "repair_id": rid,
        "kind": kind,
        "original_context_snapshot_indices": context,
        "original_failed_pair_indices_addressed": addressed,
        "required_snapshot_order_original_indices": order,
        "required_cut_chain": cuts,
        "quarantined_snapshot_indices": sorted(set(context) - set(order)),
    }


def test_compose_snapshot_order_quarantine():
    r = repair(context=[0, 1, 2, 3, 4], addressed=[1, 2],
               order=[0, 1, 3, 4], cuts=[0, 0, 0, 0])
    assert compose_snapshot_order(5, [r]) == [0, 1, 3, 4]
    assert set(edge_overrides([r])) == {(0, 1), (1, 3), (3, 4)}


def test_repair_context_may_not_hide_undeclared_failed_pair():
    snaps = [snap(0), snap(10), snap(20, "2"), snap(30), snap(40)]
    r = repair(context=[0, 1, 2, 3, 4], addressed=[1],
               order=[0, 1, 3, 4], cuts=[0, 0, 0, 0])
    with pytest.raises(RepairMaterializationError, match="undeclared/omitted"):
        build_repaired_edge_specs(
            snapshots=snaps, paid_rows=[], precision_report=report([1, 2]), repairs=[r]
        )


def test_quarantine_bridge_reconstructs_and_removes_two_failed_boundaries(tmp_path):
    snaps = [snap(0), snap(10), snap(20, "2"), snap(30), snap(40)]
    r = repair(context=[0, 1, 2, 3, 4], addressed=[1, 2],
               order=[0, 1, 3, 4], cuts=[0, 0, 0, 0])
    path = tmp_path / "cache.sqlite"
    audit = build_repair_timeline(
        path=path,
        ticker="M1",
        snapshots=snaps,
        paid_rows=[],
        identity={"ticker": "M1"},
        precision_report=report([1, 2]),
        repairs=[r],
        repair_plan_sha256="synthetic",
    )
    assert audit["original_failed_pairs_addressed"] == [1, 2]
    assert audit["remaining_unreconciled_pair_count"] == 0
    assert audit["quarantined_snapshot_indices"] == [2]
    tl = DiskTimeline(path)
    try:
        assert validate_repair_cache(tl, expected_plan_sha256="synthetic") == audit
        assert len(tl.segments) == 1
        assert tl.segments[0].start_timestamp_ms == 0
        assert tl.segments[0].end_timestamp_ms == 40
    finally:
        tl.close()


def test_unrepaired_failure_remains_hard_boundary(tmp_path):
    snaps = [snap(0), snap(10, "2"), snap(20)]
    path = tmp_path / "cache.sqlite"
    audit = build_repair_timeline(
        path=path,
        ticker="M1",
        snapshots=snaps,
        paid_rows=[],
        identity={"ticker": "M1"},
        precision_report=report([0, 1]),
        repairs=[],
        repair_plan_sha256="synthetic",
    )
    assert audit["remaining_unreconciled_pair_indices"] == [0, 1]
    tl = DiskTimeline(path)
    try:
        assert len(tl.segments) == 3
        assert tl.unique_segment_for_interval(0, 20) is None
    finally:
        tl.close()


def test_wrong_pinned_cut_fails_exact_endpoint_reconstruction(tmp_path):
    # One +1 delta at t=0 changes size 1 -> 2. Correct same-time cut would
    # include that row; the pinned zero-length cut must fail closed.
    snaps = [
        {"timestamp": 0, "sequence": 0, "source": "s",
         "yes_bids": [{"price": "50", "size": "1"}], "yes_asks": []},
        {"timestamp": 0, "sequence": 1, "source": "s",
         "yes_bids": [{"price": "50", "size": "2"}], "yes_asks": []},
    ]
    rows = [{"ticker": "M1", "timestamp": 0, "sequence": 1,
             "source_row_number_1based": 1,
             "side": "yes", "price_dollars": "0.5", "delta_fp": "1"}]
    r = repair(context=[0, 1], addressed=[0], order=[0, 1],
               cuts=[0, 0], kind="ordering")
    with pytest.raises(RepairMaterializationError, match="does not exactly reconstruct"):
        build_repair_timeline(
            path=tmp_path / "bad.sqlite",
            ticker="M1",
            snapshots=snaps,
            paid_rows=rows,
            identity={"ticker": "M1"},
            precision_report=report([0]),
            repairs=[r],
            repair_plan_sha256="synthetic",
        )


def test_same_timestamp_sequence_uses_original_source_row_as_final_tiebreak():
    snaps = [
        {"timestamp": 0, "sequence": 0, "source": "s",
         "yes_bids": [{"price": "50", "size": "1"}], "yes_asks": []},
        {"timestamp": 0, "sequence": 1, "source": "s",
         "yes_bids": [{"price": "50", "size": "1"}], "yes_asks": []},
    ]
    late = {"ticker": "M1", "timestamp": 0, "sequence": 1,
            "source_row_number_1based": 20, "side": "yes",
            "price_dollars": "0.5", "delta_fp": "-1"}
    early = {"ticker": "M1", "timestamp": 0, "sequence": 1,
             "source_row_number_1based": 10, "side": "yes",
             "price_dollars": "0.5", "delta_fp": "1"}
    assert paid_row_key(early) < paid_row_key(late)
    selected = selected_rows_for_cuts(
        snaps[0], snaps[1], [late, early], start_cut=0, end_cut=2
    )
    assert [r["source_row_number_1based"] for r in selected] == [10, 20]

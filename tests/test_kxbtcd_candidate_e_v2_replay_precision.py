from contextlib import closing
from copy import deepcopy
from decimal import Decimal as D
import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_v2_replay_precision import (
    normalize_snapshots, precision_audit, build_precision_timeline,
    validate_paid_quantities, validate_precision_cache,
)
from src.kxbtcd_candidate_e_v2_disk_timeline import DiskTimeline, build_disk_timeline
from src.kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import V2QuantityTransportAmendmentError
from src.predexon_segment_safe_replay import apply_delta, snapshot_book, mismatch_count

FIXTURE = Path(__file__).parent / "fixtures/candidate_e_25ms_replay_precision.json"


def snap(ts, size="2", seq=1):
    return {"timestamp": ts, "sequence": seq,
            "yes_bids": [{"price": "40", "size": size}],
            "yes_asks": [{"price": "60", "size": "3"}]}


def delta(ts, size="1", seq=1):
    return {"timestamp": ts, "sequence": seq, "side": "yes",
            "price_dollars": "0.40", "delta_fp": size}


def test_actual_25ms_boundary_and_both_adjacent_controls(tmp_path):
    data = json.loads(FIXTURE.read_text())
    snapshots, rows = data["snapshots"], data["paid_rows"]
    untouched = deepcopy(snapshots)
    normalized, report = precision_audit(ticker=data["ticker"], snapshots=snapshots, paid_rows=rows)
    assert snapshots == untouched
    assert report["before"]["exact_pair_count"] == 2
    assert report["after"]["exact_pair_count"] == 3
    assert report["after"]["unreconciled_pair_count"] == 0
    assert report["after"]["excluded_gap_ms"] == 0
    assert len(report["changed_pairs"]) == 1
    pair = report["changed_pairs"][0]
    assert pair["pair_index"] == 1
    assert pair["end_timestamp_ms"] - pair["start_timestamp_ms"] == 25
    assert pair["before"]["total_mismatches"] == -1
    assert pair["after"]["total_mismatches"] == 0
    assert pair["after"]["start_cut"] == pair["after"]["end_cut"] == 1
    path = tmp_path / "real_boundary.sqlite"
    build_precision_timeline(path=path, ticker=data["ticker"], snapshots=snapshots,
                             paid_rows=rows, identity={"test": True})
    with closing(DiskTimeline(path)) as timeline:
        assert len(timeline.segments) == 1
        assert timeline.unique_segment_for_interval(1783699571887, 1783699571912) is not None
        assert validate_precision_cache(timeline) == report
        for state in timeline.segments[0].states:
            for level in (*state.yes_bids, *state.yes_asks):
                assert level.quantity >= 0 and level.quantity % D("0.01") == 0


def test_actual_nine_cuts_are_valid_but_only_one_reconciles_exactly():
    data = json.loads(FIXTURE.read_text())
    snapshots,_ = normalize_snapshots(data["snapshots"])
    left,right = snapshots[1:3]
    rows = data["paid_rows"]
    start = [r for r in rows if r["timestamp"] == left["timestamp"]]
    middle = [r for r in rows if left["timestamp"] < r["timestamp"] < right["timestamp"]]
    end = [r for r in rows if r["timestamp"] == right["timestamp"]]
    assert len(start) == len(end) == 2
    target_bids,target_asks = snapshot_book(right)
    exact = []
    for start_cut in range(3):
        for end_cut in range(3):
            bids,asks = snapshot_book(left)
            for row in [*start[start_cut:],*middle,*end[:end_cut]]:
                apply_delta(bids,asks,row)
            if not mismatch_count(bids,target_bids,epsilon=D(0)) and not mismatch_count(asks,target_asks,epsilon=D(0)):
                exact.append((start_cut,end_cut))
    assert exact == [(1,1)]


@pytest.mark.parametrize("value", ["-1e-14", "NaN", "Infinity", "1.001", "1.0000000011"])
def test_bad_snapshot_quantity_fails_closed(value):
    with pytest.raises((ValueError, V2QuantityTransportAmendmentError)):
        normalize_snapshots([snap(0, value)])


@pytest.mark.parametrize("value,expected", [("24.99999999999998", "25.00"),
    ("1.000000001", "1.00"), ("0.999999999", "1.00"), ("185.26999999999998", "185.27")])
def test_exact_tolerance_and_cent_grid(value, expected):
    snapshots, audit = normalize_snapshots([snap(0, value)])
    assert snapshots[0]["yes_bids"][0]["size"] == expected
    assert audit["levels_normalized"] == 1


def test_positive_zero_residue_removed_but_negative_rejected():
    snapshots, audit = normalize_snapshots([snap(0, "1e-14")])
    assert snapshots[0]["yes_bids"] == []
    assert audit["zero_levels_removed"] == 1


@pytest.mark.parametrize("value", ["-0.00000000001", "1.001", "NaN", "Infinity"])
def test_paid_delta_never_rounded(value):
    with pytest.raises(ValueError):
        validate_paid_quantities([delta(1, value)])


def test_actual_negative_update_still_rejected():
    bids = {D("0.40"): D("25")}
    with pytest.raises(ValueError, match="negative resting"):
        apply_delta(bids, {}, delta(1, "-25.01"))
    assert bids == {D("0.40"): D("25")}


@pytest.mark.parametrize("snapshots,rows", [
    ([snap(0), snap(10,"3",2)], [delta(5)]),
    ([snap(0), snap(10,"3",2), snap(20,"99",3), snap(30,"100",4)], [delta(5),delta(25)]),
    ([snap(0), snap(0,"3",2), snap(10,"4",3)], [delta(0),delta(5,seq=2)]),
])
def test_exact_grid_paths_equal_original_disk_builder(tmp_path,snapshots,rows):
    old, new = tmp_path / "old.sqlite", tmp_path / "new.sqlite"
    build_disk_timeline(path=old,ticker="M1",snapshots=snapshots,paid_rows=rows,identity={})
    build_precision_timeline(path=new,ticker="M1",snapshots=snapshots,paid_rows=rows,identity={})
    with closing(DiskTimeline(old)) as a, closing(DiskTimeline(new)) as b:
        assert len(a.segments) == len(b.segments)
        for x,y in zip(a.segments,b.segments):
            assert (x.start_timestamp_ms,x.end_timestamp_ms) == (y.start_timestamp_ms,y.end_timestamp_ms)
            assert tuple(x.states) == tuple(y.states)
            assert tuple(x.state_changes(x.start_timestamp_ms,x.end_timestamp_ms)) == tuple(y.state_changes(y.start_timestamp_ms,y.end_timestamp_ms))


def test_real_gap_stays_gap_and_end_of_evidence_not_extended(tmp_path):
    path = tmp_path / "gap.sqlite"
    build_precision_timeline(path=path,ticker="M1",snapshots=[snap(0),snap(10,"99",2)],
                             paid_rows=[delta(5)],identity={})
    with closing(DiskTimeline(path)) as timeline:
        assert len(timeline.segments) == 2
        assert timeline.unique_segment_for_interval(0,10) is None
        assert timeline.unique_segment_for_interval(10,11) is None
        assert len(validate_precision_cache(timeline)["remaining_unreconciled_pairs"]) == 1


def test_one_cent_snapshot_mismatch_still_fails():
    _,report = precision_audit(ticker="M1",snapshots=[snap(0),snap(10,"3.01",2)],paid_rows=[delta(5)])
    assert report["after"]["unreconciled_pair_count"] == 1


def test_duplicate_prices_fail():
    s=snap(0);s["yes_bids"].append({"price":"40.0","size":"1"})
    with pytest.raises(ValueError,match="duplicate"):
        normalize_snapshots([s])


def test_old_cache_rejected_as_precision_cache(tmp_path):
    path=tmp_path/"old.sqlite"
    build_disk_timeline(path=path,ticker="M1",snapshots=[snap(0),snap(10,"3",2)],paid_rows=[delta(5)],identity={})
    with closing(DiskTimeline(path)) as timeline:
        with pytest.raises(ValueError,match="precision audit"):
            validate_precision_cache(timeline)


def test_freeze():
    from src.kxbtcd_candidate_e_v2_replay_precision_freeze import validate_precision_amendment
    assert validate_precision_amendment(Path(__file__).parents[1])["checkpoint_id"] == "21N-Y-A3"


def ticker_inputs(tmp_path,monkeypatch):
    import materialize_kxbtcd_candidate_e_v2_paths_replay_precision as runner
    ticker="M1"
    backfill=tmp_path/runner.BACKFILL_ROOT_RELATIVE_PATH/f"{ticker}_raw_pages.jsonl"
    backfill.parent.mkdir(parents=True);backfill.write_text('synthetic source')
    replay=tmp_path/runner.REPLAY_TICKER_ROOT_RELATIVE_PATH/f"{ticker}.json"
    replay.parent.mkdir(parents=True);replay.write_text(json.dumps({"ticker":ticker,
        "candidate_e_scored":False,"outcomes_accessed":False,"strategy_pnl_calculated":False,
        "network_requests":0,"orders_placed":0,"segments":[{"start_timestamp":0,"end_timestamp":10}]}))
    calls=[]
    def loader(*args):
        calls.append(True)
        return {ticker:[delta(5)]}
    monkeypatch.setattr(runner.parent,'load_paid_rows_for_tickers',loader)
    monkeypatch.setattr(runner,'load_backfill_snapshots',lambda *a,**kw:[snap(0),snap(10,"3",2)])
    cache=tmp_path/'cache';cache.mkdir()
    return runner,dict(repo=tmp_path,root=cache,ticker=ticker,paid_path=tmp_path/'fake.parquet',
                       amendment_fp='synthetic'),calls


def test_precision_seal_reuse_and_changed_amendment_rejected(tmp_path,monkeypatch):
    runner,args,calls=ticker_inputs(tmp_path,monkeypatch)
    path=runner.prepare_ticker(**args,progress=lambda message:None)
    digest=runner.file_sha256(path)
    assert runner.prepare_ticker(**args,progress=lambda message:None) == path
    assert len(calls)==1 and runner.file_sha256(path)==digest
    args['amendment_fp']='changed'
    with pytest.raises(RuntimeError,match='mismatch'):
        runner.prepare_ticker(**args,progress=lambda message:None)


def test_precision_interruption_preserves_other_cache_and_allows_resume(tmp_path,monkeypatch):
    runner,args,calls=ticker_inputs(tmp_path,monkeypatch)
    other=args['root']/'preserved.sqlite';other.write_bytes(b'preserve')
    def interrupt(message):
        if 'reconstructing segment' in message:raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):runner.prepare_ticker(**args,progress=interrupt)
    assert list(args['root'].iterdir())==[other] and other.read_bytes()==b'preserve'
    assert runner.prepare_ticker(**args,progress=lambda message:None).is_file()


def test_revised_runner_no_partial_scoring_and_different_output_rejected(tmp_path):
    import materialize_kxbtcd_candidate_e_v2_paths_replay_precision as runner
    import materialize_kxbtcd_candidate_e_v2_paths_memory_safe as previous
    assert runner.CACHE_ROOT != previous.CACHE_ROOT and runner.OUTPUT != previous.OUTPUT
    with pytest.raises(ValueError):runner.materialize(simulate=True,max_tickers=1)
    with pytest.raises(RuntimeError):runner.require_committed_amendment(tmp_path,{"frozen_files":{}})
    path=tmp_path/'out.json'
    digest=runner.write_output(path,{"policy_results":[]})
    assert runner.write_output(path,{"policy_results":[]})==digest
    with pytest.raises(RuntimeError):runner.write_output(path,{"policy_results":[1]})
    with pytest.raises(runner.parent.simulate_policy.__globals__['SpotRelativeV2SimulatorError']):
        runner.write_output(tmp_path/'bad.json',{"settlement_value":1})

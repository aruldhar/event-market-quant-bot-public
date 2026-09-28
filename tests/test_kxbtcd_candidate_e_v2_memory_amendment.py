from contextlib import ExitStack, closing
from dataclasses import replace
from decimal import Decimal as D
import ast
import gc
import inspect
import json
from pathlib import Path
import sqlite3
import tracemalloc

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel, BookState, VerifiedSegmentTimeline, VerifiedTickerTimeline,
    ExecutableConvergenceSimulatorError, build_verified_ticker_timeline,
)
from src.kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import (
    canonicalize_verified_ticker_timeline, V2QuantityTransportAmendmentError,
)
from src.kxbtcd_candidate_e_v2_disk_timeline import (
    DiskTimeline, build_disk_timeline, write_timeline_fixture, file_sha256,
)
from src import kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator as original
from src import kxbtcd_candidate_e_v2_disk_policy as adapted
from src.kxbtcd_candidate_e_continuous_btc_materialization import (
    ContinuousBtcRow, required_minutes, scan_bounds_ms,
)
from src.kxbtcd_candidate_e_v2_memory_amendment_freeze import validate_memory_amendment, validate_policy_body, text_hash
import materialize_kxbtcd_candidate_e_v2_paths_memory_safe as runner


def book(ts, bid="0.39", ask="0.40", bidq="2", askq="2", deep="3"):
    return BookState(ts,
        () if bid is None else (BookLevel(D(bid), D(bidq)), BookLevel(D("0.001"), D(deep))),
        () if ask is None else (BookLevel(D(ask), D(askq)), BookLevel(D("0.999"), D(deep))))


def tl(ticker, segments):
    return VerifiedTickerTimeline(ticker, tuple(VerifiedSegmentTimeline(i, start, end, tuple(states))
                                              for i, (start, end, states) in enumerate(segments)))


def disk_fixture(tmp_path, timeline):
    path = tmp_path / (timeline.ticker + ".sqlite")
    write_timeline_fixture(path, timeline)
    return DiskTimeline(path)


def snapshot(ts, q, seq=1, ask="2"):
    return {"timestamp": ts, "sequence": seq, "yes_bids": [{"price": "40", "size": q}],
            "yes_asks": [{"price": "60", "size": ask}]}


def delta(ts, q, seq=1):
    return {"timestamp": ts, "sequence": seq, "side": "yes", "price_dollars": "0.40", "delta_fp": q}


def compare_replay(tmp_path, snapshots, rows):
    baseline = canonicalize_verified_ticker_timeline(build_verified_ticker_timeline(
        ticker="M1", snapshots=snapshots, paid_rows=rows))
    path = tmp_path / "replay.sqlite"
    build_disk_timeline(path=path, ticker="M1", snapshots=snapshots, paid_rows=rows, identity={})
    with closing(DiskTimeline(path)) as disk:
        assert len(baseline.segments) == len(disk.segments)
        for a, b in zip(baseline.segments, disk.segments):
            assert (a.segment_index, a.start_timestamp_ms, a.end_timestamp_ms) == (
                b.segment_index, b.start_timestamp_ms, b.end_timestamp_ms)
            assert a.states == tuple(b.states)
            for timestamp in range(a.start_timestamp_ms, a.end_timestamp_ms + 1):
                assert a.state_at(timestamp) == b.state_at(timestamp)
            assert a.state_changes(a.start_timestamp_ms, a.end_timestamp_ms) == tuple(b.state_changes(
                b.start_timestamp_ms, b.end_timestamp_ms))
    return baseline


@pytest.mark.parametrize("snapshots,rows", [
    ([snapshot(0,"2"),snapshot(10,"4",2)], [delta(5,"1",1),delta(5,"1",2)]),
    ([snapshot(0,"2"),snapshot(10,"3",2),snapshot(20,"99",3),snapshot(30,"100",4)],
     [delta(5,"1"),delta(25,"1",2)]),
    ([snapshot(0,"2.0000000000001"),snapshot(10,"3.0000000000001",2)], [delta(5,"1")]),
    ([snapshot(0,"2"),snapshot(0,"3",2),snapshot(10,"4",3)], [delta(0,"1"),delta(5,"1",2)]),
    ([snapshot(0,"2"),snapshot(10,"3",2),snapshot(10,"4",3),snapshot(20,"5",4)],
     [delta(5,"1"),delta(10,"1",2),delta(15,"1",3)]),
    ([snapshot(0,"2"),snapshot(10,"3",2)], [delta(10,"1")]),
    ([snapshot(0,"2"),snapshot(10,"2",2)], [delta(5,"1"),delta(5,"-1",2)]),
    ([snapshot(0,"2"),snapshot(10,"2",2)], [delta(5,"0")]),
    ([snapshot(0,"2")], [delta(0,"0")]),
])
def test_disk_reconstruction_matches_frozen_replay_then_quantity_adapter(tmp_path, snapshots, rows):
    compare_replay(tmp_path, snapshots, rows)


def test_normalization_keeps_raw_change_timestamps(tmp_path):
    baseline = compare_replay(tmp_path,
        [snapshot(0,"2.0000000000001"),snapshot(10,"2.0000000000002",2)], [delta(5,"0")])
    assert len(baseline.segments[0].states) == 2
    assert len(baseline.segments[0].state_changes(0,10)) == 1


def test_materially_off_grid_stops_without_complete_cache(tmp_path):
    path = tmp_path / "invalid.sqlite"
    with pytest.raises(V2QuantityTransportAmendmentError):
        build_disk_timeline(path=path, ticker="M1", snapshots=[snapshot(0,"1.005")],
                            paid_rows=[delta(0,"0")], identity={})
    with pytest.raises((ValueError, TypeError)):
        DiskTimeline(path)


def test_no_gap_crossing_and_shared_boundary_is_ambiguous(tmp_path):
    base = tl("M1", [(0,10,[book(0),book(5)]), (10,20,[book(10)]), (30,40,[book(30)])])
    with closing(disk_fixture(tmp_path, base)) as disk:
        for start,end in [(0,9),(10,10),(9,11),(21,29),(31,35),(-1,0)]:
            a = base.unique_segment_for_interval(start,end)
            b = disk.unique_segment_for_interval(start,end)
            assert (None if a is None else a.segment_index) == (None if b is None else b.segment_index)
        with pytest.raises(ExecutableConvergenceSimulatorError):
            disk.segments[0].state_at(11)
        with pytest.raises(ExecutableConvergenceSimulatorError):
            tuple(disk.segments[0].state_changes(9,11))


def btc_rows(price="10050"):
    return tuple(ContinuousBtcRow(m.event_ticker,m.event_close_time_utc,m.minute_start_utc,m.minute_end_utc,D(price))
                 for m in required_minutes())


def market(event,ticker,strike,rank=0,n=1):
    return original.LadderMarket(event,ticker,D(strike),rank,n,None)


@pytest.mark.parametrize("mode", ["round_trips","no_side","partial","missed","gap","empty","no_exit","no_edge"])
def test_all_fifteen_policies_identical_on_synthetic_paths(tmp_path,mode):
    event="KXBTCD-26JUL1013"; ticker=event+"-T10000"
    lo,hi=scan_bounds_ms(event)
    states=[book(lo),book(lo+1000,"0.65","0.66"),book(lo+3000,"0.01","0.99"),
            book(lo+4000),book(lo+5000,"0.65","0.66")]
    if mode=="partial": states.insert(1,book(lo+500,askq="0.40"))
    if mode=="missed": states.insert(1,book(lo+500,"0.60","0.61"))
    if mode=="empty": states=[book(lo,None,None)]
    if mode=="no_edge": states=[book(lo,"0.01","0.99")]
    if mode=="no_exit": states=[book(lo)]
    if mode=="no_side":
        states=[book(lo),book(lo+1000,"0.19","0.20"),book(lo+3000,"0.01","0.99"),
                book(lo+4000),book(lo+5000,"0.19","0.20")]
    base=tl(ticker,[(lo,hi+120000,states)])
    if mode=="gap": base=tl(ticker,[(lo,lo+250,[book(lo)]),(lo+2000,hi,[book(lo+2000)])])
    rows=btc_rows("9950" if mode=="no_side" else "10050"); ladder=(market(event,ticker,10000),)
    with closing(disk_fixture(tmp_path,base)) as disk:
        for threshold in original.THRESHOLDS:
            for latency in original.LATENCY_MS:
                args=dict(event_ticker=event,event_ladder=ladder,btc_rows=rows,threshold=threshold,latency_ms=latency)
                a=original.simulate_policy(timelines={ticker:base},**args)
                b=adapted.simulate_policy(timelines={ticker:disk},**args)
                assert a==b
                assert original.jsonable(a)==original.jsonable(b)
                if mode=="round_trips" and latency==0:
                    assert len(a.trades)==2 and a.trades[-1].liquidation.status=="EXIT_FULL"
                if mode=="partial" and latency==500:
                    assert a.trades[0].entry.ioc.status=="PARTIAL"
                if mode=="no_side" and latency==0:
                    assert a.trades[0].signal.side=="NO" and a.trades[0].liquidation.status=="EXIT_FULL"


def test_clock_moving_window_deep_changes_missing_btc_and_boundaries(tmp_path):
    event="KXBTCD-26JUL1013"; lo,hi=scan_bounds_ms(event)
    rows=btc_rows("10725")
    idx=original.materialization_index(rows)
    # Indexed clock deliberately also accepts an incomplete index, as its parent does.
    idx.pop((event,lo+60000))
    key=(event,lo+120000)
    idx[key]=replace(idx[key],close_price=D("11900"))
    ladder=tuple(market(event,f"M{i}",10000+100*i,i,20) for i in range(20))
    mem={}; disks={}
    with ExitStack() as stack:
        for m in ladder:
            states=[book(lo),book(lo+100,deep="4"),book(lo+200,askq="3"),
                    book(lo+60000,askq="4"),book(lo+180000,askq="5")]
            base=tl(m.market_ticker,[(lo,lo+180000,states),(lo+180500,hi,[book(lo+180500)])])
            mem[m.market_ticker]=base
            disks[m.market_ticker]=stack.enter_context(closing(disk_fixture(tmp_path,base)))
        args=dict(event_ticker=event,event_ladder=ladder,btc_rows_or_index=idx)
        a=original.decision_clock(timelines=mem,**args)
        b=adapted.decision_clock(timelines=disks,**args)
        assert a==b
        assert lo+100 not in a and lo+200 in a and lo+180500 in a


def test_policy_body_and_economic_function_aliases_unchanged():
    validate_policy_body(Path('.'))
    for name in adapted.simulate_policy.__code__.co_names:
        if name in adapted.__dict__ and name!="decision_clock":
            assert adapted.__dict__[name] is original.__dict__[name]


def test_cache_reuse_requires_hash_and_source_identity(tmp_path):
    identity={"ticker":"M1","source":"a"}
    path=tmp_path/"M1.sqlite"
    write_timeline_fixture(path,tl("M1",[(0,1,[book(0)])]),identity)
    seal=path.with_suffix('.seal.json')
    seal.write_text(json.dumps({"identity":identity,"sha256":file_sha256(path)}))
    with closing(runner.open_sealed_cache(path,identity)) as disk: assert disk.ticker=="M1"
    with pytest.raises(RuntimeError):runner.open_sealed_cache(path,{**identity,"source":"b"})
    with path.open('ab') as f:f.write(b'corruption')
    with pytest.raises(RuntimeError):runner.open_sealed_cache(path,identity)


def test_interrupt_preserves_sealed_cache_and_releases_run_lock(tmp_path):
    saved=tmp_path/'saved.sqlite'; saved.write_bytes(b'sealed fixture')
    with pytest.raises(KeyboardInterrupt):
        with runner.run_lock(tmp_path):
            with pytest.raises(RuntimeError):
                with runner.run_lock(tmp_path):pass
            raise KeyboardInterrupt
    assert saved.read_bytes()==b'sealed fixture'
    assert not (tmp_path/'RUNNING.lock').exists()


def ticker_inputs(tmp_path,monkeypatch):
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
        return {ticker:[delta(5,"1")]}
    monkeypatch.setattr(runner.parent,'load_paid_rows_for_tickers',loader)
    monkeypatch.setattr(runner,'load_backfill_snapshots',lambda *a,**kw:[snapshot(0,"2"),snapshot(10,"3",2)])
    cache=tmp_path/'cache';cache.mkdir()
    return dict(repo=tmp_path,root=cache,ticker=ticker,paid_path=tmp_path/'fake.parquet',amendment_fp='synthetic'),calls


def test_completed_ticker_is_reused_without_reconstruction(tmp_path,monkeypatch):
    args,calls=ticker_inputs(tmp_path,monkeypatch)
    first=runner.prepare_ticker(**args,progress=lambda message:None)
    digest=file_sha256(first)
    second=runner.prepare_ticker(**args,progress=lambda message:None)
    assert len(calls)==1 and first==second and file_sha256(second)==digest


def test_interrupt_during_ticker_build_cleans_only_incomplete_work(tmp_path,monkeypatch):
    args,calls=ticker_inputs(tmp_path,monkeypatch)
    saved=args['root']/'already_sealed.sqlite';saved.write_bytes(b'preserve')
    def interrupt(message):
        if 'reconstructing segment' in message:raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):runner.prepare_ticker(**args,progress=interrupt)
    assert sorted(p.name for p in args['root'].iterdir())==['already_sealed.sqlite']
    assert saved.read_bytes()==b'preserve'
    completed=runner.prepare_ticker(**args,progress=lambda message:None)
    assert completed.is_file() and len(calls)==2


def test_output_is_idempotent_and_rejects_different_or_outcome_payload(tmp_path):
    path=tmp_path/'paths.json'
    first=runner.write_output(path,{"policy_results":[]})
    assert runner.write_output(path,{"policy_results":[]})==first
    with pytest.raises(RuntimeError):runner.write_output(path,{"policy_results":[1]})
    with pytest.raises(original.SpotRelativeV2SimulatorError):runner.write_output(tmp_path/'bad.json',{"outcome":1})


def test_no_simulation_with_partial_ticker_preparation():
    with pytest.raises(ValueError):runner.materialize(simulate=True,max_tickers=1)


def test_uncommitted_repair_stops_before_real_source_reads(tmp_path):
    with pytest.raises(RuntimeError):runner.require_committed_amendment(tmp_path,{"frozen_files":{}})


def test_memory_does_not_hold_reconstructed_history(tmp_path):
    n=1800
    levels=[{"price":str(10+i),"size":"2"} for i in range(20)]
    first={"timestamp":0,"sequence":0,"yes_bids":levels,"yes_asks":[{"price":"60","size":"2"}]}
    final={**first,"timestamp":n+1,"sequence":n+1,"yes_bids":[*levels,{"price":"40","size":str(n)}]}
    rows=[delta(i,"1",i) for i in range(1,n+1)]
    gc.collect();tracemalloc.start()
    base=build_verified_ticker_timeline(ticker="M1",snapshots=[first,final],paid_rows=rows)
    expected_count=sum(len(s.states) for s in base.segments)
    baseline_peak=tracemalloc.get_traced_memory()[1]
    tracemalloc.stop();del base;gc.collect()
    tracemalloc.start()
    path=tmp_path/'memory.sqlite'
    build_disk_timeline(path=path,ticker="M1",snapshots=[first,final],paid_rows=rows,identity={})
    disk_peak=tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    with closing(DiskTimeline(path)) as disk:
        assert sum(s.state_count for s in disk.segments)==expected_count
    print(f"tracemalloc replay peaks: original={baseline_peak} disk={disk_peak}")
    assert disk_peak < baseline_peak * 0.35


def test_memory_amendment_freeze():
    payload=validate_memory_amendment('.')
    assert payload['checkpoint_id']=='21N-Y-A2'


def test_windows_powershell_newline_translation_preserves_text_hash():
    assert text_hash(b'line 1\r\nline 2\r\n')==text_hash(b'line 1\nline 2\n')
    assert text_hash(b'line 1\nline 3\n')!=text_hash(b'line 1\nline 2\n')

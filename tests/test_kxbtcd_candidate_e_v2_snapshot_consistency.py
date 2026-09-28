from __future__ import annotations
import copy
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from src import predexon_segment_safe_replay as replay
from src.kxbtcd_candidate_e_v2_replay_precision import normalize_snapshots
from src.kxbtcd_candidate_e_v2_snapshot_consistency import (
    RULES, ReplayWorkBound, coverage_variant, exact_chain, plan_repairs, repair_coverage,
)
from src.kxbtcd_candidate_e_v2_snapshot_consistency_io import CoveragePairs, sha256

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/fixtures/kxbtcd_snapshot_consistency_cases.json').read_text())['cases']


def setup_case(case):
    snapshots, _ = normalize_snapshots(case['snapshots'])
    rows = sorted(case['paid_rows'], key=lambda r: (r['timestamp'], r['sequence'], r.get('source_row_number_1based', 0)))
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE ticks(ticker TEXT,ts INTEGER,seq INTEGER,source_row INTEGER,side TEXT,price TEXT,delta TEXT)')
    con.executemany('INSERT INTO ticks VALUES (?,?,?,?,?,?,?)', [
        (case['ticker'], r['timestamp'], r['sequence'], r.get('source_row_number_1based', i + 1), r['side'], r['price_dollars'], r['delta_fp'])
        for i, r in enumerate(rows)])
    selected = [[r for r in rows if a['timestamp'] <= r['timestamp'] <= b['timestamp']] for a, b in zip(snapshots, snapshots[1:])]
    segments, results = replay.build_verified_segments(snapshots, selected, epsilon=replay.Decimal(0))
    failed = [{'pair_index': i, 'start_timestamp_ms': snapshots[i]['timestamp'], 'end_timestamp_ms': snapshots[i+1]['timestamp'],
               'result': asdict(r)} for i, r in enumerate(results) if not r.exact]
    coverage = {'remaining_unreconciled_pairs': failed,
                'after_bounds': [[s.start_timestamp, s.end_timestamp] for s in segments],
                'after': {'snapshot_count': len(snapshots), 'paid_delta_count': len(rows), 'unreconciled_pair_count': len(failed)}}
    return snapshots, coverage, con, CoveragePairs(case['ticker'], snapshots, coverage, con, replay)


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['name'])
def test_real_source_cases(case):
    snapshots, coverage, con, pair = setup_case(case)
    before = copy.deepcopy(snapshots)
    result = repair_coverage(snapshots, coverage, pair)
    con.close()
    assert snapshots == before
    accepted = [p for p in result['proposals'] if p['status'] == 'ACCEPTED']
    if case['expected_kind'] is None:
        assert accepted == []
        assert result['variants']['combined']['remaining_failed_pair_count'] == len(coverage['remaining_unreconciled_pairs'])
    else:
        assert len(accepted) == 1 and accepted[0]['kind'] == case['expected_kind']
        assert accepted[0]['chain']['cut_chain_count_capped_at_two'] == 1
        assert result['variants']['combined']['remaining_failed_pair_count'] == 0
        assert len(result['variants']['combined']['required_local_cut_chains']) == 1
    assert result['cache_built'] is result['strategy_run'] is False


def synthetic(sizes, times=None, sources=None):
    return {'ticker': 'SYNTH', 'paid_rows': [], 'snapshots': [
        {'timestamp': (times or list(range(1000, 1000 + 1000 * len(sizes), 1000)))[i],
         'sequence': i, 'source': (sources or ['source'] * len(sizes))[i],
         'yes_bids': [{'price': '20', 'size': str(q)}], 'yes_asks': []}
        for i, q in enumerate(sizes)]}


def test_multiple_bad_snapshots_remain_unresolved():
    ss, cov, con, pair = setup_case(synthetic([10, 10, 100, 101, 10, 10]))
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert not result['accepted_counts']
    assert result['variants']['combined']['remaining_failed_pair_count'] == 3


def test_overlapping_contexts_reject_both_proposals():
    ss, cov, con, pair = setup_case(synthetic([10, 10, 99, 10, 10, 99, 10, 10]))
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert result['rejection_counts']['overlapping_original_contexts'] == 2
    assert not result['accepted_counts']


def test_long_context_is_preserved():
    ss, cov, con, pair = setup_case(synthetic([10, 10, 99, 10, 10], times=[0, 1, 2, 3, 120001]))
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert result['rejection_counts'] == {'context_exceeds_120_seconds': 1}
    assert result['variants']['combined']['remaining_failed_pair_count'] == 2


def test_non_strict_quarantine_context_is_preserved():
    ss, cov, con, pair = setup_case(synthetic([10, 10, 99, 10, 10], times=[0, 0, 2, 3, 4]))
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert result['rejection_counts'] == {'five_snapshot_times_not_strict': 1}


def test_source_labels_do_not_make_a_conflict_acceptable():
    ss, cov, con, pair = setup_case(synthetic([10, 10, 99, 11, 11]))
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert not result['accepted_counts']
    assert result['rejection_counts'] == {'no_unique_exact_quarantine_chain': 1}


def test_same_source_timestamp_order_is_preserved():
    case = copy.deepcopy(CASES[0])
    for s in case['snapshots']:
        s['source'] = 'same_source'
    ss, cov, con, pair = setup_case(case)
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert result['rejection_counts']['same_source_order_preserved'] == 1
    assert not result['accepted_counts']


def test_shared_snapshot_cut_must_agree_and_ambiguity_is_rejected():
    pairs = {(0, 1): {'exact_cuts': [[0, 1]]}, (1, 2): {'exact_cuts': [[0, 1]]}}
    assert exact_chain([0, 1, 2], lambda a, b: pairs[a, b])['cut_chain_count_capped_at_two'] == 0
    pairs[(0, 1)]['exact_cuts'] = [[0, 0], [1, 0]]
    result = exact_chain([0, 1, 2], lambda a, b: pairs[a, b])
    assert result['cut_chain_count_capped_at_two'] == 2 and result['unique_cut_chain'] is None


def test_resource_bound_is_not_a_repair(monkeypatch):
    ss, cov, con, pair = setup_case(CASES[0])
    monkeypatch.setitem(RULES, 'maximum_pair_rows', 0)
    result = repair_coverage(ss, cov, pair)
    con.close()
    assert not result['accepted_counts']
    assert any(k.startswith('resource_bound:') for k in result['rejection_counts'])


def test_no_change_preserves_singleton_segments():
    ss, cov, con, pair = setup_case(synthetic([10, 11, 12]))
    result = coverage_variant(ss, cov['remaining_unreconciled_pairs'], [], pair, set())
    con.close()
    assert result['pairwise_verified_bounds'] == cov['after_bounds']
    assert result['pairwise_verified_bounds'] == [[1000, 1000], [2000, 2000], [3000, 3000]]


def test_freeze_validates_and_detects_changed_child_file(tmp_path):
    from src.kxbtcd_candidate_e_v2_snapshot_consistency_freeze import validate_snapshot_consistency_amendment
    result = validate_snapshot_consistency_amendment(ROOT)
    assert result['rules'] == RULES
    # Full tampering checks use an isolated copy of the required project files.
    for folder in ('src', 'configs', 'docs', 'tests', 'scripts'):
        shutil.copytree(ROOT / folder, tmp_path / folder, ignore=shutil.ignore_patterns('__pycache__'))
    for p in ROOT.glob('*.py'):
        shutil.copyfile(p, tmp_path / p.name)
    target = tmp_path / 'src/kxbtcd_candidate_e_v2_snapshot_consistency.py'
    target.write_bytes(target.read_bytes() + b'# changed\n')
    with pytest.raises(ValueError, match='frozen file changed'):
        validate_snapshot_consistency_amendment(tmp_path)


def test_coverage_runner_file_flow_preserves_sources_and_caches(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq
    import validate_kxbtcd_candidate_e_v2_snapshot_consistency_coverage as runner
    from src.predexon_subcent_backfill import SCHEMA_VERSION, body_sha256
    repo = tmp_path / 'repo'
    for folder in ('src', 'configs', 'docs', 'tests', 'scripts'):
        shutil.copytree(ROOT / folder, repo / folder, ignore=shutil.ignore_patterns('__pycache__'))
    for p in ROOT.glob('*.py'):
        shutil.copyfile(p, repo / p.name)
    selected = CASES[:3]
    rows = [r for c in selected for r in c['paid_rows']]
    paid = repo / runner.PAID_FILE
    paid.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), paid)
    monkeypatch.setattr(runner, 'PAID_SHA', sha256(paid))
    reports = []
    for c in selected:
        ticker = c['ticker']
        ss, report, con, _ = setup_case(c)
        con.close()
        report['ticker'] = ticker
        reports.append(report)
        body = json.dumps({'snapshots': c['snapshots'], 'pagination': {'limit': 2000, 'count': len(ss), 'has_more': False, 'pagination_key': None}})
        source = repo / runner.SNAPSHOTS / (ticker + '_raw_pages.jsonl')
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(json.dumps({'schema_version': SCHEMA_VERSION, 'ticker': ticker, 'page_number': 1,
                                     'http_status': 200, 'body': body, 'body_sha256': body_sha256(body)}) + '\n')
        original_replay = repo / runner.REPLAYS / (ticker + '.json')
        original_replay.parent.mkdir(parents=True, exist_ok=True)
        original_replay.write_text('{}\n')
        identity = {'ticker': ticker, 'paid_sha256': runner.PAID_SHA, 'snapshot_sha256': sha256(source),
                    'replay_sha256': sha256(original_replay), 'replay_precision_amendment_fingerprint': runner.AMENDMENT,
                    'memory_amendment_fingerprint': runner.MEMORY, 'quantity_amendment_fingerprint': runner.QUANTITY}
        cache = repo / runner.CACHE / (ticker + '.sqlite')
        cache.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(cache)
        db.executescript('CREATE TABLE metadata(payload TEXT); CREATE TABLE segments(segment INTEGER,start INTEGER,end INTEGER);')
        db.execute('INSERT INTO metadata VALUES (?)', (json.dumps({'ticker': ticker, 'complete': True, 'identity': identity, 'replay_precision_audit': report}),))
        db.executemany('INSERT INTO segments VALUES (?,?,?)', [(i, a, b) for i, (a, b) in enumerate(report['after_bounds'])])
        db.commit();db.close()
        cache.with_suffix('.seal.json').write_text(json.dumps({'identity': identity, 'sha256': sha256(cache)}))
    coverage_path = repo / runner.CACHE / 'coverage_full.json'
    coverage_path.write_text(json.dumps({'replay_precision_amendment_fingerprint': runner.AMENDMENT, 'ticker_reports': reports}))
    monkeypatch.setattr(runner, 'COVERAGE_SHA', sha256(coverage_path))
    path = repo / runner.PATH_FILE
    path.write_text(json.dumps({'replay_precision_amendment_fingerprint': runner.AMENDMENT,
                               'replay_precision_coverage_sha256': runner.COVERAGE_SHA,
                               'dynamic_ticker_union': [c['ticker'] for c in selected]}))
    monkeypatch.setattr(runner, 'PATH_SHA', sha256(path))
    monkeypatch.setattr(runner, 'EXPECTED_TICKERS', 3)
    monkeypatch.setattr(runner, 'EXPECTED_FAILURES', 4)
    import tempfile
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    before = {str(p.relative_to(repo)): sha256(p) for p in repo.rglob('*') if p.is_file()}
    output = tmp_path / 'coverage.json'
    result = runner.run_coverage(repo, output)
    after = {str(p.relative_to(repo)): sha256(p) for p in repo.rglob('*') if p.is_file()}
    assert before == after
    assert not list(tmp_path.glob('candidate_e_snapshot_coverage_*'))
    assert result['status'] == 'PASS_INCREMENTAL_COVERAGE_GATE'
    assert result['totals']['combined']['remaining_failed_pair_count'] == 0
    assert result['totals']['ordering_only']['remaining_failed_pair_count'] == 2
    assert result['totals']['quarantine_only']['remaining_failed_pair_count'] == 2
    assert result['safety']['strategy_run'] is False
    assert result['safety']['new_cache_built'] is False
    with pytest.raises(RuntimeError, match='already exists'):
        runner.run_coverage(repo, output)

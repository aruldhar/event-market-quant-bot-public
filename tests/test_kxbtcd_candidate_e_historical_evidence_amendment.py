import csv, json
from pathlib import Path
import pytest
from src.kxbtcd_candidate_e_historical_evidence_amendment import (
    FROZEN_AMENDMENT_FINGERPRINT, HistoricalEvidenceAmendmentError,
    compute_universe_identity, validate_amendment,
)

def test_frozen_amendment_validates():
    assert validate_amendment()==FROZEN_AMENDMENT_FINGERPRINT

def test_stage_sizes_and_firewall_are_frozen():
    d=json.loads(Path('configs/kxbtcd_candidate_e_historical_evidence_amendment.json').read_text(encoding='utf-8'))
    p=d['historical_pipeline']
    assert [p['H1_train']['target_eligible_events'],p['H2_validation']['target_eligible_events'],p['H3_locked_test']['target_eligible_events']]==[1500,750,750]
    assert d['reserve_policy']['minimum_outcome_unopened_reserve_events_after_candidate_e_materialization']==5000
    assert p['H2_validation']['outcome_access'].startswith('prohibited')
    assert p['H3_locked_test']['outcome_access'].startswith('prohibited')

def test_candidate_e_formulas_are_preserved():
    d=json.loads(Path('configs/kxbtcd_candidate_e_historical_evidence_amendment.json').read_text(encoding='utf-8'))
    inv=d['candidate_e_invariants']
    assert inv['distance_formula']=='10000 * ln(S_t / K)'
    assert inv['momentum_formula']=='10000 * ln(S_t / S_t_minus_300s)'
    assert inv['scored_ttc_target_minutes']==[55,50,45,40,35,30]

def test_universe_identity_uses_only_ticker_membership(tmp_path):
    census=tmp_path/'census.csv'
    with census.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['event_ticker','strike_date_utc']); w.writeheader();
        w.writerows([{'event_ticker':'A','strike_date_utc':'2025-01-01T00:00:00Z'},{'event_ticker':'B','strike_date_utc':'2025-01-01T01:00:00Z'},{'event_ticker':'C','strike_date_utc':'2025-01-01T02:00:00Z'}])
    exp=tmp_path/'outcomes.csv'
    with exp.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['event_ticker','outcome']); w.writeheader(); w.writerow({'event_ticker':'B','outcome':'YES'})
    x=compute_universe_identity(census,[exp])
    assert x['census_event_count']==3 and x['prior_outcome_exposed_event_count']==1 and x['untouched_event_count']==2
    assert x['first_untouched']==('2025-01-01T00:00:00Z','A') and x['last_untouched']==('2025-01-01T02:00:00Z','C')

def test_universe_fails_if_exposure_outside_census(tmp_path):
    census=tmp_path/'c.csv'; exp=tmp_path/'e.csv'
    census.write_text('event_ticker,strike_date_utc\nA,2025-01-01T00:00:00Z\n',encoding='utf-8')
    exp.write_text('event_ticker,outcome\nZ,YES\n',encoding='utf-8')
    with pytest.raises(HistoricalEvidenceAmendmentError): compute_universe_identity(census,[exp])

def test_portable_path_normalizes_windows_separators():
    from src.kxbtcd_candidate_e_historical_evidence_amendment import _portable_path
    assert _portable_path(r"data\derived\example.csv") == "data/derived/example.csv"

"""Checkpoint-19F historical evidence amendment for Candidate E.

This module is network-free and performs no model fitting or outcome scoring.
It validates the pre-outcome protocol amendment and can verify the exact local
historical census/exposure identities using only event_ticker from previously
exposed outcome files. No new outcome field is accessed.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_AMENDMENT_PATH = Path("configs/kxbtcd_candidate_e_historical_evidence_amendment.json")
DEFAULT_CANDIDATE_E_PATH = Path("configs/kxbtcd_candidate_e_predeclaration.json")
DEFAULT_SOURCE_POLICY_PATH = Path("configs/kxbtcd_independent_btc_source_policy.json")
FROZEN_AMENDMENT_FINGERPRINT = "b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb"
EXPECTED_PARENT_PROTOCOL = "b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8"
EXPECTED_PARENT_SOURCE_POLICY = "6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18"
EXPECTED_PARENT_CANDIDATE_E = "9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9"

class HistoricalEvidenceAmendmentError(RuntimeError):
    pass

def _err(msg: str) -> None:
    raise HistoricalEvidenceAmendmentError(msg)

def _load(path: str | Path) -> dict[str, Any]:
    p=Path(path)
    try: x=json.loads(p.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as e: raise HistoricalEvidenceAmendmentError(f"could not read {p}: {e}") from e
    if not isinstance(x,dict): _err(f"{p} root must be an object")
    return x

def _sha_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def _sha_lines(lines: Iterable[str]) -> str:
    h=hashlib.sha256()
    for line in lines:
        h.update(line.encode('utf-8')); h.update(b'\n')
    return h.hexdigest()

def _portable_path(value: str | Path) -> str:
    # Config fingerprints use repository-relative POSIX-style paths.
    # Windows Path.__str__ uses backslashes, so normalize separators
    # before comparing path identities. This does not alter file bytes
    # or any frozen SHA-256 value.
    return str(value).replace("\\", "/")

def _canonical_fingerprint(doc: Mapping[str,Any]) -> str:
    payload={k:v for k,v in doc.items() if k!='amendment_fingerprint'}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def validate_amendment(path: str|Path=DEFAULT_AMENDMENT_PATH, *, verify_parents: bool=True) -> str:
    d=_load(path)
    if d.get('schema_version')!='kxbtcd_candidate_e_historical_evidence_amendment.v1': _err('schema_version changed')
    if d.get('checkpoint_id')!='19F': _err('checkpoint_id changed')
    if d.get('parent_protocol_fingerprint')!=EXPECTED_PARENT_PROTOCOL: _err('parent protocol changed')
    if d.get('parent_source_policy_fingerprint')!=EXPECTED_PARENT_SOURCE_POLICY: _err('parent source policy changed')
    if d.get('parent_candidate_e_predeclaration_fingerprint')!=EXPECTED_PARENT_CANDIDATE_E: _err('parent Candidate-E predeclaration changed')
    if d.get('amendment_fingerprint')!=FROZEN_AMENDMENT_FINGERPRINT: _err('amendment fingerprint field changed')
    if _canonical_fingerprint(d)!=FROZEN_AMENDMENT_FINGERPRINT: _err('canonical amendment fingerprint mismatch')
    fw=d['evidence_firewall']
    if fw['amendment_selected_using_new_candidate_e_outcomes'] is not False or fw['candidate_e_fit_before_amendment'] is not False or fw['new_candidate_e_outcome_access_before_amendment'] is not False: _err('pre-outcome firewall changed')
    if fw['checkpoint17_outcome_values_used'] is not False: _err('Checkpoint-17 outcome values must remain prohibited')
    u=d['frozen_universe']
    if (u['census_event_count'],u['prior_outcome_exposed_event_count'],u['untouched_event_count'])!=(9738,307,9431): _err('frozen universe counts changed')
    p=d['historical_pipeline']
    if (p['H1_train']['target_eligible_events'],p['H2_validation']['target_eligible_events'],p['H3_locked_test']['target_eligible_events'])!=(1500,750,750): _err('historical stage sizes changed')
    if p['H1_train']['selection_layout']!='same seven contiguous blocks and five rolling-origin score folds frozen in 19E': _err('H1 selection layout changed')
    r=d['reserve_policy']
    if r['minimum_outcome_unopened_reserve_events_after_candidate_e_materialization']!=5000: _err('reserve floor changed')
    if d['historical_state_realization']['max_historical_cross_source_disagreement_bps']!=5.0: _err('historical verifier disagreement gate changed')
    inv=d['candidate_e_invariants']
    if inv['distance_formula']!='10000 * ln(S_t / K)' or inv['momentum_formula']!='10000 * ln(S_t / S_t_minus_300s)': _err('Candidate-E feature formula changed')
    if inv['scored_ttc_target_minutes']!=[55,50,45,40,35,30]: _err('TTC targets changed')
    if any(d['safety'][k] for k in ('paper_execution','demo_execution','real_money_execution','order_creation','order_cancellation','transfers')): _err('execution safety changed')
    if verify_parents:
        ce=_load(DEFAULT_CANDIDATE_E_PATH)
        if ce.get('predeclaration_fingerprint')!=EXPECTED_PARENT_CANDIDATE_E: _err('local Candidate-E parent fingerprint mismatch')
        sp=_load(DEFAULT_SOURCE_POLICY_PATH)
        if sp.get('policy_fingerprint')!=EXPECTED_PARENT_SOURCE_POLICY: _err('local source-policy parent fingerprint mismatch')
    return FROZEN_AMENDMENT_FINGERPRINT

def compute_universe_identity(census_path: str|Path, exposure_paths: Sequence[str|Path]) -> dict[str,Any]:
    cp=Path(census_path)
    with cp.open('r',encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if not rows or 'event_ticker' not in rows[0] or 'strike_date_utc' not in rows[0]: _err('census missing event_ticker/strike_date_utc')
    census_events={r['event_ticker'].strip() for r in rows if r.get('event_ticker','').strip()}
    if len(census_events)!=len(rows): _err('census event_ticker values must be nonblank and unique')
    exposed:set[str]=set()
    source=[]
    for raw in exposure_paths:
        p=Path(raw)
        with p.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if 'event_ticker' not in (reader.fieldnames or []): _err(f'event_ticker missing from {p}')
            s={(r.get('event_ticker') or '').strip() for r in reader if (r.get('event_ticker') or '').strip()}
        exposed.update(s); source.append({'path':_portable_path(p),'sha256':_sha_file(p),'event_count':len(s)})
    if exposed-census_events: _err('exposure set contains events outside census')
    untouched=sorted(((r['strike_date_utc'].strip(),r['event_ticker'].strip()) for r in rows if r['event_ticker'].strip() not in exposed),key=lambda x:(x[0],x[1]))
    return {
      'census_sha256':_sha_file(cp),'census_event_count':len(rows),'prior_outcome_exposed_event_count':len(exposed),'untouched_event_count':len(untouched),
      'exposed_event_set_sha256':_sha_lines(sorted(exposed)),
      'untouched_chronological_universe_sha256':_sha_lines(f'{dt}|{ticker}' for dt,ticker in untouched),
      'first_untouched':untouched[0] if untouched else None,'last_untouched':untouched[-1] if untouched else None,'exposure_sources':source
    }

def verify_local_universe(path: str|Path=DEFAULT_AMENDMENT_PATH) -> dict[str,Any]:
    validate_amendment(path)
    d=_load(path); u=d['frozen_universe']; sf=u['source_files']
    identity=compute_universe_identity(sf['census']['path'],[x['path'] for x in sf['exposure_files']])
    checks={
      'census_sha256':u['census_sha256'],'census_event_count':u['census_event_count'],'prior_outcome_exposed_event_count':u['prior_outcome_exposed_event_count'],'untouched_event_count':u['untouched_event_count'],
      'exposed_event_set_sha256':u['exposed_event_set_sha256'],'untouched_chronological_universe_sha256':u['untouched_chronological_universe_sha256']
    }
    for k,v in checks.items():
        if identity[k]!=v: _err(f'local universe mismatch for {k}: expected {v}, observed {identity[k]}')
    expected_files={_portable_path(x['path']):x['sha256'] for x in sf['exposure_files']}
    for x in identity['exposure_sources']:
        if expected_files.get(x['path'])!=x['sha256']: _err(f'exposure source hash mismatch: {x["path"]}')
    return identity

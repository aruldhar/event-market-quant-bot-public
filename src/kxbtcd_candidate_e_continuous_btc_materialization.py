"""21N-U-A continuous Coinbase-minute materialization contract."""
from __future__ import annotations
import csv, hashlib
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from typing import Any,Mapping,Sequence

SCHEMA_VERSION='kxbtcd_candidate_e_continuous_coinbase_1m.v1'
CHECKPOINT_ID='21N-U'
SOURCE_ID='coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1'
EVENT_CLOSE_UTC={
 'KXBTCD-26JUL1013':'2026-07-10T17:00:00Z',
 'KXBTCD-26JUL1014':'2026-07-10T18:00:00Z',
 'KXBTCD-26JUL1015':'2026-07-10T19:00:00Z',
 'KXBTCD-26JUL1016':'2026-07-10T20:00:00Z',
}
EVENT_COUNT=4; MINUTES_PER_EVENT=54; EXPECTED_ROW_COUNT=216
SCAN_START_TTC_MINUTES=55; SCAN_END_TTC_MINUTES=2
DEFAULT_OUTPUT_RELATIVE_PATH=Path('data/analysis/predexon_credit_efficiency/july10_candidate_e_continuous_coinbase_1m.csv')
CSV_FIELDS=('schema_version','event_ticker','event_close_time_utc','minute_start_utc','minute_end_utc','coinbase_close_price')
class ContinuousBtcMaterializationError(RuntimeError): pass
def _fail(m): raise ContinuousBtcMaterializationError(m)
def parse_utc(text):
    try: dt=datetime.fromisoformat(str(text).strip().replace('Z','+00:00'))
    except ValueError as exc: raise ContinuousBtcMaterializationError(f'invalid UTC timestamp: {text}') from exc
    if dt.tzinfo is None: _fail('timestamp must include timezone')
    return dt.astimezone(timezone.utc)
def format_utc(dt):
    dt=dt.astimezone(timezone.utc)
    return dt.isoformat(timespec='microseconds').replace('+00:00','Z')
def epoch_ms(dt):
    dt=dt.astimezone(timezone.utc); e=datetime(1970,1,1,tzinfo=timezone.utc); d=dt-e
    return d.days*86400000+d.seconds*1000+d.microseconds//1000
def _positive(v,n):
    try:d=Decimal(str(v))
    except (InvalidOperation,TypeError,ValueError) as exc: raise ContinuousBtcMaterializationError(f'{n} must be numeric') from exc
    if not d.is_finite() or d<=0:_fail(f'{n} must be positive')
    return d
@dataclass(frozen=True)
class RequiredMinute:
    event_ticker:str; event_close_time_utc:str; minute_start_utc:str; minute_end_utc:str
    @property
    def minute_start_ms(self): return epoch_ms(parse_utc(self.minute_start_utc))
    @property
    def minute_end_ms(self): return epoch_ms(parse_utc(self.minute_end_utc))
@dataclass(frozen=True)
class ContinuousBtcRow:
    event_ticker:str; event_close_time_utc:str; minute_start_utc:str; minute_end_utc:str; close_price:Decimal
    @property
    def minute_start_ms(self): return epoch_ms(parse_utc(self.minute_start_utc))
    @property
    def minute_end_ms(self): return epoch_ms(parse_utc(self.minute_end_utc))
def required_minutes():
    out=[]
    for event in sorted(EVENT_CLOSE_UTC):
        close=parse_utc(EVENT_CLOSE_UTC[event]); first=close-timedelta(minutes=56)
        for i in range(54):
            s=first+timedelta(minutes=i); e=s+timedelta(minutes=1)
            out.append(RequiredMinute(event,format_utc(close),format_utc(s),format_utc(e)))
    if len(out)!=216:_fail('required minute count mismatch')
    return tuple(out)
def required_minutes_by_event():
    g={e:[] for e in EVENT_CLOSE_UTC}
    for r in required_minutes(): g[r.event_ticker].append(r)
    if any(len(v)!=54 for v in g.values()):_fail('per-event minute count mismatch')
    return {k:tuple(v) for k,v in g.items()}
def scan_bounds_ms(event):
    if event not in EVENT_CLOSE_UTC:_fail('unexpected event')
    c=epoch_ms(parse_utc(EVENT_CLOSE_UTC[event])); return c-55*60000,c-2*60000
def decision_required_minute_start_ms(t): return (int(t)//60000)*60000-60000
def required_minute_for_decision(event,t):
    lo,hi=scan_bounds_ms(event)
    if not lo<=t<=hi:_fail('decision outside scan window')
    key=decision_required_minute_start_ms(t)
    m=[r for r in required_minutes_by_event()[event] if r.minute_start_ms==key]
    if len(m)!=1:_fail('required minute unavailable')
    return m[0]
def validate_rows(rows):
    exp=required_minutes(); rows=tuple(sorted(rows,key=lambda r:(r.event_ticker,r.minute_start_ms)))
    if len(rows)!=216:_fail(f'expected 216 rows, got {len(rows)}')
    for i,(r,q) in enumerate(zip(rows,exp)):
        if (r.event_ticker,r.event_close_time_utc,r.minute_start_utc,r.minute_end_utc)!=(q.event_ticker,q.event_close_time_utc,q.minute_start_utc,q.minute_end_utc):_fail(f'row key mismatch at {i}')
        _positive(r.close_price,'coinbase_close_price')
    return rows
def serialize_csv(rows):
    from io import StringIO
    s=StringIO(newline=''); w=csv.DictWriter(s,fieldnames=CSV_FIELDS,lineterminator='\n'); w.writeheader()
    for r in validate_rows(rows): w.writerow({'schema_version':SCHEMA_VERSION,'event_ticker':r.event_ticker,'event_close_time_utc':r.event_close_time_utc,'minute_start_utc':r.minute_start_utc,'minute_end_utc':r.minute_end_utc,'coinbase_close_price':format(r.close_price,'f')})
    return s.getvalue().encode()
def write_materialization(path,rows):
    raw=serialize_csv(rows); p=Path(path)
    if p.exists() and p.read_bytes()!=raw:_fail(f'refusing non-identical overwrite: {p}')
    if not p.exists(): p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(raw)
    return p,hashlib.sha256(raw).hexdigest()
def load_materialization(path):
    p=Path(path)
    if not p.is_file():_fail(f'materialization missing: {p}')
    out=[]
    with p.open('r',encoding='utf-8',newline='') as h:
        rd=csv.DictReader(h)
        if tuple(rd.fieldnames or ())!=CSV_FIELDS:_fail('CSV schema mismatch')
        for i,r in enumerate(rd):
            if r['schema_version']!=SCHEMA_VERSION:_fail(f'schema mismatch row {i}')
            out.append(ContinuousBtcRow(r['event_ticker'],r['event_close_time_utc'],r['minute_start_utc'],r['minute_end_utc'],_positive(r['coinbase_close_price'],'coinbase_close_price')))
    return validate_rows(out)
def materialization_index(rows):
    rows=validate_rows(rows); idx={(r.event_ticker,r.minute_start_ms):r for r in rows}
    if len(idx)!=216:_fail('duplicate BTC row')
    return idx
def btc_row_for_decision(rows_or_idx,*,event_ticker,decision_timestamp_ms):
    idx=rows_or_idx if isinstance(rows_or_idx,Mapping) else materialization_index(rows_or_idx)
    lo,hi=scan_bounds_ms(event_ticker)
    if not lo<=decision_timestamp_ms<=hi:return None
    row=idx.get((event_ticker,decision_required_minute_start_ms(decision_timestamp_ms)))
    if row is None:return None
    if row.minute_end_ms>decision_timestamp_ms:_fail('future candle used')
    return row

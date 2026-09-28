"""Settlement-blind continuous Candidate-E convergence/re-entry simulator, 21N-U-A."""
from __future__ import annotations
from dataclasses import dataclass,asdict,is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any,Mapping,Sequence
from .kxbtcd_candidate_e_continuous_btc_materialization import EVENT_CLOSE_UTC,ContinuousBtcRow,btc_row_for_decision,epoch_ms,materialization_index,parse_utc,scan_bounds_ms
from .kxbtcd_candidate_e_continuous_convergence_reentry_v1_predeclaration import EXPECTED_PREDECLARATION_FINGERPRINT,load_predeclaration,validate_predeclaration
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import LATENCY_MS,PLANNED_QUANTITY,SIDE_ORDER,THRESHOLDS,ZERO,BookState,EntryAttempt,ExecutableConvergenceSimulatorError,LiquidationBranch,SignalCandidate,VerifiedTickerTimeline,account_synthetic_fill,best_yes_quote,candidate_e_probability,side_fair_probability,side_purchase_asks,simulate_entry,simulate_liquidation_branch,validate_frozen_parents
from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_freeze import validate_freeze as validate_21n_r_freeze
STRATEGY_ID='kxbtcd_candidate_e_continuous_convergence_reentry_v1'; STRUCTURAL_ROLES=('q10','q30','q50','q70','q90'); ORIGINAL_ANCHORS=(55,50,45,40,35,30); MIN_DEPTH=Decimal('1.00')
class ContinuousStrategySimulatorError(RuntimeError): pass
def _fail(m): raise ContinuousStrategySimulatorError(m)
@dataclass(frozen=True)
class SideEvaluation: side:str; purchase_price:Decimal; decision_level_quantity:Decimal; depth_qualifies:bool; fair_probability:Decimal; entry_fee:Decimal; net_edge:Decimal
@dataclass(frozen=True)
class MarketEvaluation:
    event_ticker:str; market_ticker:str; structural_role:str; strike:Decimal; decision_timestamp_ms:int; decision_ttc_ms:int; btc_spot:Decimal|None; btc_minute_start_ms:int|None; btc_state_age_ms:int|None; status:str; q_market:Decimal|None; candidate_probability:Decimal|None; decision_yes_bid:Decimal|None; decision_yes_ask:Decimal|None; sides:tuple[SideEvaluation,...]
@dataclass(frozen=True)
class ContinuousSignal:
    event_ticker:str; market_ticker:str; structural_role:str; strike:Decimal; decision_timestamp_ms:int; decision_ttc_ms:int; ttc_bucket:str; is_exact_original_anchor:bool; candidate_e_domain_label:str; late_window_extrapolation:bool; side:str; btc_spot:Decimal; btc_minute_start_ms:int; btc_state_age_ms:int; q_market:Decimal; candidate_probability:Decimal; side_fair_probability:Decimal; decision_yes_bid:Decimal; decision_yes_ask:Decimal; decision_limit_price:Decimal; decision_level_quantity:Decimal; signal_entry_fee:Decimal; net_edge_per_contract:Decimal
@dataclass(frozen=True)
class EntryAttemptRecord: trade_number:int; signal:ContinuousSignal; latency_ms:int; entry:EntryAttempt
@dataclass(frozen=True)
class TradePath: trade_number:int; signal:ContinuousSignal; latency_ms:int; entry:EntryAttempt; liquidation:LiquidationBranch|None; fully_closed_round_trip_cash_change:Decimal|None; matched_hold_settlement_quantity:Decimal
@dataclass(frozen=True)
class RearmRecord: reference_market_ticker:str; reference_side:str; rearm_timestamp_ms:int; reason:str
@dataclass(frozen=True)
class ContinuousPolicyResult: event_ticker:str; threshold:Decimal; latency_ms:int; decision_clock_count:int; entry_attempts:tuple[EntryAttemptRecord,...]; trades:tuple[TradePath,...]; rearm:RearmRecord|None; terminal_state:str
def validate_parents(repo_root='.'):
    repo=Path(repo_root); d=load_predeclaration(repo/'configs/kxbtcd_candidate_e_continuous_convergence_reentry_v1_predeclaration.json'); validate_predeclaration(d)
    if d.get('predeclaration_fingerprint')!=EXPECTED_PREDECLARATION_FINGERPRINT:_fail('21N-T fingerprint mismatch')
    p=validate_frozen_parents(repo); fr=validate_21n_r_freeze(repo)
    if fr.get('implementation_fingerprint')!='6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf':_fail('21N-R fingerprint mismatch')
    return {'continuous_strategy_predeclaration_fingerprint':EXPECTED_PREDECLARATION_FINGERPRINT,**p,'simulator_21n_r_implementation_fingerprint':fr['implementation_fingerprint']}
def ttc_bucket(ms):
    m=Decimal(int(ms))/Decimal(60000)
    if 45<m<=55:return '55_to_45'
    if 30<m<=45:return '45_to_30'
    if 20<m<=30:return '30_to_20'
    if 10<m<=20:return '20_to_10'
    if 5<m<=10:return '10_to_5'
    if 2<=m<=5:return '5_to_2'
    _fail('TTC outside T-55 to T-2')
def exact_original_anchor(ms): return int(ms) in {m*60000 for m in ORIGINAL_ANCHORS}
def domain_label(ms):
    if exact_original_anchor(ms):return 'exact_original_anchor',False
    if ms<30*60000:return 'continuous_time_extrapolation__late_window_outside_historical_ttc_support',True
    return 'continuous_time_extrapolation',False
def _top_signature(s):
    b=s.yes_bids[0] if s.yes_bids else None; a=s.yes_asks[0] if s.yes_asks else None
    return (None if b is None else b.price,None if b is None else b.quantity,None if a is None else a.price,None if a is None else a.quantity)
def decision_clock(*,event_ticker,structural_timelines,btc_rows):
    lo,hi=scan_bounds_ms(event_ticker); times={lo,hi}
    for r in btc_rows:
        if r.event_ticker==event_ticker and lo<=r.minute_end_ms<=hi:times.add(r.minute_end_ms)
    for tl in structural_timelines.values():
        for seg in tl.segments:
            s=max(lo,seg.start_timestamp_ms); e=min(hi,seg.end_timestamp_ms)
            if s>e:continue
            first=seg.state_at(s); prev=_top_signature(first); times.add(s)
            for st in seg.states:
                if not s<st.timestamp_ms<=e:continue
                sig=_top_signature(st)
                if sig!=prev:times.add(st.timestamp_ms); prev=sig
    return tuple(sorted(times))
def evaluate_market(*,event_ticker,market_ticker,structural_role,strike,decision_timestamp_ms,event_close_timestamp_ms,timeline,btc_row):
    if structural_role not in STRUCTURAL_ROLES:_fail('bad role')
    ttc=event_close_timestamp_ms-decision_timestamp_ms; ttc_bucket(ttc); strike=Decimal(str(strike))
    if btc_row is None:return MarketEvaluation(event_ticker,market_ticker,structural_role,strike,decision_timestamp_ms,ttc,None,None,None,'BTC_SOURCE_UNAVAILABLE',None,None,None,None,())
    seg=timeline.unique_segment_for_interval(decision_timestamp_ms,decision_timestamp_ms)
    if seg is None:return MarketEvaluation(event_ticker,market_ticker,structural_role,strike,decision_timestamp_ms,ttc,btc_row.close_price,btc_row.minute_start_ms,decision_timestamp_ms-btc_row.minute_end_ms,'KALSHI_SOURCE_UNAVAILABLE',None,None,None,None,())
    state=seg.state_at(decision_timestamp_ms)
    try:bid,ask=best_yes_quote(state)
    except ExecutableConvergenceSimulatorError as exc:
        if str(exc) in {'two-sided YES book required','crossed YES book'}:return MarketEvaluation(event_ticker,market_ticker,structural_role,strike,decision_timestamp_ms,ttc,btc_row.close_price,btc_row.minute_start_ms,decision_timestamp_ms-btc_row.minute_end_ms,'INVALID_TWO_SIDED_BOOK',None,None,None,None,())
        raise
    q=(bid.price+ask.price)/Decimal(2); p=candidate_e_probability(q_market=q,btc_spot=btc_row.close_price,strike=strike); sides=[]
    for side in ('YES','NO'):
        best=side_purchase_asks(state,side)[0]; fee=account_synthetic_fill(action='BUY',price=best.price,quantity=PLANNED_QUANTITY,accumulator_before=ZERO).net_fee; fair=side_fair_probability(side,p)
        sides.append(SideEvaluation(side,best.price,best.quantity,best.quantity>=MIN_DEPTH,fair,fee,fair-best.price-fee))
    return MarketEvaluation(event_ticker,market_ticker,structural_role,strike,decision_timestamp_ms,ttc,btc_row.close_price,btc_row.minute_start_ms,decision_timestamp_ms-btc_row.minute_end_ms,'EVALUABLE',q,p,bid.price,ask.price,tuple(sides))
def signal_from_evaluation(ev,s):
    if ev.status!='EVALUABLE':_fail('unavailable evaluation')
    label,late=domain_label(ev.decision_ttc_ms)
    return ContinuousSignal(ev.event_ticker,ev.market_ticker,ev.structural_role,ev.strike,ev.decision_timestamp_ms,ev.decision_ttc_ms,ttc_bucket(ev.decision_ttc_ms),exact_original_anchor(ev.decision_ttc_ms),label,late,s.side,ev.btc_spot,ev.btc_minute_start_ms,ev.btc_state_age_ms,ev.q_market,ev.candidate_probability,s.fair_probability,ev.decision_yes_bid,ev.decision_yes_ask,s.purchase_price,s.decision_level_quantity,s.entry_fee,s.net_edge)
def select_signal_at_timestamp(evaluations,*,threshold):
    th=Decimal(str(threshold))
    if th not in THRESHOLDS:_fail('threshold outside menu')
    c=[signal_from_evaluation(e,s) for e in evaluations if e.status=='EVALUABLE' for s in e.sides if s.depth_qualifies and s.net_edge>=th]
    if not c:return None
    c.sort(key=lambda x:(-x.net_edge_per_contract,x.market_ticker,SIDE_ORDER[x.side]));return c[0]
def _parent_signal(s): return SignalCandidate(s.event_ticker,s.market_ticker,s.structural_role,int(s.decision_ttc_ms//60000),s.decision_timestamp_ms,s.side,s.candidate_probability,s.side_fair_probability,s.q_market,s.decision_yes_bid,s.decision_yes_ask,s.decision_limit_price,s.signal_entry_fee,s.net_edge_per_contract)
def simulate_continuous_entry(*,signal,timeline,latency_ms): return simulate_entry(signal=_parent_signal(signal),timeline=timeline,latency_ms=latency_ms)
def simulate_continuous_liquidation(*,signal,entry,timeline,event_close_timestamp_ms): return simulate_liquidation_branch(signal=_parent_signal(signal),entry=entry,timeline=timeline,event_close_timestamp_ms=event_close_timestamp_ms)
def _cash(entry,liq):
    if not entry.source_available or entry.ioc is None or entry.ioc.filled_quantity<=ZERO or liq is None or liq.status!='EXIT_FULL' or liq.exit_ioc is None or liq.exit_ioc.status!='FULL' or liq.settlement_fallback_quantity!=ZERO:return None
    return entry.ioc.net_cash_change_total+liq.exit_ioc.net_cash_change_total
def _eval_event(event,rows,timelines,idx,t,event_close):
    btc=btc_row_for_decision(idx,event_ticker=event,decision_timestamp_ms=t); out=[]
    for r in rows:
        if str(r['event_ticker'])==event:
            ticker=str(r['market_ticker']);out.append(evaluate_market(event_ticker=event,market_ticker=ticker,structural_role=str(r['structural_role']),strike=r['strike'],decision_timestamp_ms=t,event_close_timestamp_ms=event_close,timeline=timelines[ticker],btc_row=btc))
    if len(out)!=5:_fail('expected five structural markets')
    return tuple(out)
def _rearmed(evals,ref,th):
    ev=[e for e in evals if e.market_ticker==ref.market_ticker]
    if len(ev)!=1:_fail('reference market missing')
    if ev[0].status!='EVALUABLE':return False,None
    s=[s for s in ev[0].sides if s.side==ref.side][0]
    if not s.depth_qualifies:return True,'REFERENCE_DEPTH_BELOW_ONE_CONTRACT'
    if s.net_edge<th:return True,'REFERENCE_EDGE_BELOW_THRESHOLD'
    return False,None
def simulate_policy(*,event_ticker,structural_rows,timelines,btc_rows,threshold,latency_ms):
    th=Decimal(str(threshold))
    if th not in THRESHOLDS or latency_ms not in LATENCY_MS:_fail('bad scenario')
    close=epoch_ms(parse_utc(EVENT_CLOSE_UTC[event_ticker])); idx=materialization_index(btc_rows); et={str(r['market_ticker']):timelines[str(r['market_ticker'])] for r in structural_rows if str(r['event_ticker'])==event_ticker}
    if len(et)!=5:_fail('expected five timelines')
    clock=decision_clock(event_ticker=event_ticker,structural_timelines=et,btc_rows=btc_rows); mode='ARMED_FIRST';block=-1;attempts=[];trades=[];rearm=None;ref=None
    for t in clock:
        if t<=block:continue
        evs=_eval_event(event_ticker,structural_rows,timelines,idx,t,close)
        if mode=='WAIT_REARM':
            yes,reason=_rearmed(evs,ref,th)
            if yes: rearm=RearmRecord(ref.market_ticker,ref.side,t,str(reason));mode='ARMED_SECOND';block=t
            continue
        if mode not in {'ARMED_FIRST','ARMED_SECOND'}:break
        sig=select_signal_at_timestamp(evs,threshold=th)
        if sig is None:continue
        num=1 if mode=='ARMED_FIRST' else 2; entry=simulate_continuous_entry(signal=sig,timeline=timelines[sig.market_ticker],latency_ms=latency_ms);attempts.append(EntryAttemptRecord(num,sig,latency_ms,entry));block=entry.arrival_timestamp_ms
        if not entry.source_available or entry.ioc is None or entry.ioc.filled_quantity==ZERO:continue
        liq=simulate_continuous_liquidation(signal=sig,entry=entry,timeline=timelines[sig.market_ticker],event_close_timestamp_ms=close);trades.append(TradePath(num,sig,latency_ms,entry,liq,_cash(entry,liq),entry.ioc.filled_quantity))
        if num==2:mode='DONE_MAX_TWO_FILLED_ENTRIES';break
        ref=sig
        if liq is not None and liq.status=='EXIT_FULL' and liq.exit_ioc is not None and liq.exit_ioc.status=='FULL' and liq.settlement_fallback_quantity==ZERO and liq.exit_arrival_timestamp_ms is not None:mode='WAIT_REARM';block=liq.exit_arrival_timestamp_ms
        else:mode='DONE_FIRST_POSITION_NOT_FULLY_EXITED';break
    terminal='NO_FILLED_ENTRY' if mode=='ARMED_FIRST' else 'FIRST_TRADE_FULLY_EXITED_NO_REARM' if mode=='WAIT_REARM' else 'REARMED_NO_SECOND_FILLED_ENTRY' if mode=='ARMED_SECOND' else mode
    return ContinuousPolicyResult(event_ticker,th,latency_ms,len(clock),tuple(attempts),tuple(trades),rearm,terminal)
def jsonable(v):
    if isinstance(v,Decimal):
        t=format(v,'f');return t.rstrip('0').rstrip('.') if '.' in t else t
    if is_dataclass(v):return jsonable(asdict(v))
    if isinstance(v,Mapping):return {str(k):jsonable(x) for k,x in v.items()}
    if isinstance(v,(tuple,list)):return [jsonable(x) for x in v]
    return v
FORBIDDEN_OUTPUT_KEYS={'outcome','outcomes','winner','settlement_value','settlement_outcome','realized_pnl','pnl','profit','loss'}
def assert_outcome_blind_payload(payload):
    found=set()
    def walk(v):
        if isinstance(v,Mapping):
            for k,x in v.items():
                if str(k).lower() in FORBIDDEN_OUTPUT_KEYS:found.add(str(k).lower())
                walk(x)
        elif isinstance(v,(tuple,list)):
            for x in v:walk(x)
    walk(payload)
    if found:_fail(f'forbidden keys: {sorted(found)}')

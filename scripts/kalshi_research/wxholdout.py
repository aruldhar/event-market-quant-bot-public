# FROZEN 2026-09-27. Do not edit any parameter below.
# Preregistered forward test: ask-only maker quoting, Kalshi weather buckets.
# See docs/KALSHI_WEATHER_MAKER_PREREGISTRATION.md
# Run: re-run wxmmf.py (no earlier than 2026-11-01), then run this.
import json,math,statistics,calendar,time
CUT=calendar.timegm(time.strptime('2026-09-28T00:00:00','%Y-%m-%dT%H:%M:%S'))
MID_MAX=20.0; TTC_MIN=12.0; QUEUE=50.0; MAKER_FEE=0.0
GATE_N=20000; GATE_T=2.0
R=[r for r in json.load(open('/data/wxmm.json')) if not r['trunc']]
NEW=[r for r in R if r['cl']>CUT]
print('FROZEN RULE: ask-only, mid<%.0fc, ttc>%.0fh, queue %.0f, maker fee %.0f'%(MID_MAX,TTC_MIN,QUEUE,MAKER_FEE))
print('cutoff %s   markets in cache=%d   HOLDOUT markets (settled after cutoff)=%d'%(
      time.strftime('%Y-%m-%d',time.gmtime(CUT)),len(R),len(NEW)))
if not NEW:
    print('NO HOLDOUT DATA YET -- re-run wxmmf.py after 2026-11-01.'); raise SystemExit
def arm(pool):
    out=[];sub={'24+':[],'12-24':[]}
    for r in pool:
        S=100.0 if r['res']=='yes' else 0.0
        c=sorted(r['c']); t=r['t']; ti=0
        for i in range(1,len(c)):
            t0,t1=c[i-1][0],c[i][0]; bp,ap=c[i-1][1],c[i-1][2]
            while ti<len(t) and t[ti][0]<=t0: ti+=1
            j=ti; hh=[]
            while j<len(t) and t[j][0]<=t1: hh.append(t[j]); j+=1
            ti=j
            if bp is None or ap is None or bp<=0 or ap>=100 or ap<=bp: continue
            mid=(ap+bp)/2.0; ttc=(r['cl']-t1)/3600.0
            if mid>=MID_MAX or ttc<=TTC_MIN: continue
            cs=0.0; fs=False
            for (ts,p,cnt,tbs,ib) in hh:
                if ib: continue
                if p>=ap and not fs:
                    cs+=cnt
                    if cs>QUEUE: fs=True
            e=(ap-S-MAKER_FEE) if fs else 0.0
            out.append(e); sub['24+' if ttc>=24 else '12-24'].append(e)
    return out,sub
v,sub=arm(NEW)
def st(x,lab):
    if len(x)<25: print('  %-16s n=%-7d (too few)'%(lab,len(x))); return None
    m=statistics.mean(x); se=statistics.stdev(x)/math.sqrt(len(x))
    print('  %-16s n=%-7d mean %+7.3fc  se %5.3f  t %+6.2f'%(lab,len(x),m,se,m/se))
    return m,m/se
print('')
print('=== PRIMARY (the only number that decides it) ===')
r0=st(v,'HOLDOUT')
print('=== secondary prediction: both sub-buckets positive ===')
st(sub['24+'],'ttc 24+h'); st(sub['12-24'],'ttc 12-24h')
print('')
print('prediction was +0.28c/hr (24+h arm +0.12c)')
if r0 is None: print('VERDICT: FAIL (insufficient data)')
else:
    m,tt=r0
    ok = (len(v)>=GATE_N) and (m>0) and (tt>GATE_T)
    print('GATE: n>=%d and mean>0 and t>%.1f  ->  n=%d  mean=%+.3f  t=%+.2f'%(GATE_N,GATE_T,len(v),m,tt))
    print('VERDICT: %s'%('PASS' if ok else 'FAIL'))
    if not ok: print('A positive mean with t<%.1f is a FAIL, not "encouraging". Direction closes.'%GATE_T)

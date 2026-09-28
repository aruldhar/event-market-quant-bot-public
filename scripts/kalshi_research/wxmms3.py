# Weather market-making analysis with maker fee correctly at ZERO.
# Reads /data/wxmm.json (produced by wxmmf.py). Runs in seconds.
# See docs/KALSHI_WEATHER_MARKET_MAKING_RESULT.md
#
# Quote = the PREVIOUS hour's closing bid/ask, never the current bar's: using the same
# bar's close lets information from after the trade set the price we quoted.
import json,math,statistics
from collections import defaultdict
R=[r for r in json.load(open('/data/wxmm.json')) if not r['trunc']]
QS=[0.0,50.0,200.0]
def rp(v,lab,ind='    '):
    if len(v)<25: print('%s%-32s n=%-7d (too few)'%(ind,lab,len(v))); return
    m=statistics.mean(v); se=statistics.stdev(v)/math.sqrt(len(v))
    print('%s%-32s n=%-7d mean %+7.3fc se %5.3f t %+7.2f'%(ind,lab,len(v),m,se,m/se))
med=statistics.median([r['cl'] for r in R])
A=defaultdict(list);TW=defaultdict(list);RULE=defaultdict(list);DAYS=set()
for r in R:
    S=100.0 if r['res']=='yes' else 0.0
    c=sorted(r['c']); t=r['t']; ti=0
    half='H1' if r['cl']<=med else 'H2'
    DAYS.add(r['cl']//86400)
    for i in range(1,len(c)):
        t0,t1=c[i-1][0],c[i][0]; bp,ap=c[i-1][1],c[i-1][2]
        while ti<len(t) and t[ti][0]<=t0: ti+=1
        j=ti; hh=[]
        while j<len(t) and t[j][0]<=t1: hh.append(t[j]); j+=1
        ti=j
        if bp is None or ap is None or bp<=0 or ap>=100 or ap<=bp: continue
        mid=(ap+bp)/2.0; ttc=(r['cl']-t1)/3600.0
        bnd=min(4,int(mid//20)); tb='0-6' if ttc<6 else '6-12' if ttc<12 else '12-24' if ttc<24 else '24+'
        for q in QS:
            cs=cb=0.0; fs=fb=False
            for (ts,p,cnt,tbs,ib) in hh:
                if ib: continue            # block trades cannot fill a resting order
                if p>=ap and not fs:
                    cs+=cnt
                    if cs>q: fs=True
                elif p<=bp and not fb:
                    cb+=cnt
                    if cb>q: fb=True
            a=(ap-S) if fs else 0.0
            b=(S-bp) if fb else 0.0
            A[(q,bnd,tb)].append(a)
            TW[q].append(a+b)
            if q==50.0 and mid<20.0 and ttc<12.0:
                RULE[half].append(a); RULE['ALL'].append(a)
print('MAKER FEE = 0 (fee_type "quadratic": takers pay, makers do not)')
print('distinct event days in sample: %d'%len(DAYS))
print('')
print('=== TWO-SIDED ===')
for q in QS: rp(TW[q],'two-sided, queue %d'%int(q))
print('')
print('=== ASK-ONLY per quoted hour, ZERO MAKER FEE ===')
for q in QS:
    print('  --- queue %d ---'%int(q))
    print('    %-12s %s'%('band',''.join('%-22s'%x for x in ('24+','12-24','6-12','0-6'))))
    for bnd in range(5):
        cells=[]
        for tb in ('24+','12-24','6-12','0-6'):
            v=A[(q,bnd,tb)]
            if len(v)<40: cells.append('%-22s'%'-'); continue
            m=statistics.mean(v); se=statistics.stdev(v)/math.sqrt(len(v))
            cells.append('%-22s'%('%+6.3f t%+6.2f n%d'%(m,m/se,len(v))))
        print('    %-12s %s'%('%d-%dc'%(bnd*20,bnd*20+20),''.join(cells)))
print('')
print('=== the FAILED pre-stated rule (ttc<12h, taken from the queue-0 ordering) ===')
rp(RULE['ALL'],'ALL dates')
rp(RULE['H1'],'first half of dates')
rp(RULE['H2'],'second half of dates')
print('')
print('NOTE: the surviving cell (ttc>12h) was chosen AFTER seeing this grid and is NOT')
print('re-fitted here. It is preregistered for a forward test -- see wxholdout.py and')
print('docs/KALSHI_WEATHER_MAKER_PREREGISTRATION.md')

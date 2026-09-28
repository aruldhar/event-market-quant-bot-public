# The diagnostic that caught the weather settlement retraction.
# Reads /data/wxlad.json (weather ladders + bid/ask/floor/cap/result).
# See docs/KALSHI_WEATHER_SETTLEMENT_RETRACTION.md
#
# Block B is the test that should have been run FIRST: implied mean against the bucket
# Kalshi actually paid out on. No METAR, no IEM, no assumption about what settlement
# means. Three prior runs all compared against an unvalidated external proxy and all
# inherited the same error.
import json,statistics,math
from collections import defaultdict
R=json.load(open('/data/wxlad.json'))
rows=[]
for r in R:
    y=[l for l in r['legs'] if l['res']=='yes']
    if len(y)!=1: continue
    fl,cp=y[0]['fl'],y[0]['cp']
    if fl is None and cp is None: continue
    tail=(fl is None) or (cp is None)
    km=(cp-1.0) if fl is None else (fl+1.0) if cp is None else (fl+cp)/2.0
    legs=[]
    for x in r['legs']:
        f2,c2=x['fl'],x['cp']
        if f2 is None and c2 is None: continue
        rp=(c2-1.5) if f2 is None else (f2+1.5) if c2 is None else (f2+c2)/2.0
        legs.append(((x['a']+x['b'])/200.0,rp))
    tot=sum(p for p,_ in legs)
    if tot<0.70 or tot>1.40: continue
    im=sum(p*q for p,q in legs)/tot
    inb=((fl is None) or r['settle']>=fl) and ((cp is None) or r['settle']<=cp)
    rows.append((r['ser'],r['kind'],im,km,r['settle'],tail,inb))
def rep(v,lab):
    if len(v)<10: print('  %-26s n=%4d (too few)'%(lab,len(v))); return
    m=statistics.mean(v); se=statistics.stdev(v)/math.sqrt(len(v))
    print('  %-26s n=%4d  mean %+6.3f  se %.3f  t %+6.2f'%(lab,len(v),m,se,m/se))
core=[r for r in rows if not r[5]]
print('rows=%d  non-tail winners=%d'%(len(rows),len(core)))
print('')
print('=== A. KALSHI-SETTLED BUCKET MID  minus  MY IEM SETTLEMENT ===')
print('    (if ~+1 for HIGH and ~-1 for LOW, my proxy is the bias, not the market)')
for lab,f in (('ALL',lambda r:True),('HIGH',lambda r:r[1]=='HIGH'),('LOW',lambda r:r[1]=='LOW')):
    rep([r[3]-r[4] for r in core if f(r)],lab)
print('')
print('=== B. IMPLIED MEAN  minus  KALSHI-SETTLED BUCKET MID  (no IEM at all) ===')
print('    (this is the real test: ~0 = market calibrated, no edge)')
for lab,f in (('ALL',lambda r:True),('HIGH',lambda r:r[1]=='HIGH'),('LOW',lambda r:r[1]=='LOW')):
    rep([r[2]-r[3] for r in core if f(r)],lab)
print('')
print('=== C. PER SERIES: bucketmid-IEM | implied-bucketmid | IEM inside winning bucket ===')
print('    (a uniform offset across ALL series = the settlement DEFINITION is wrong;')
print('     an offset concentrated in one city = wrong station for that city)')
bys=defaultdict(list)
for r in core: bys[r[0]].append(r)
for s,v in sorted(bys.items()):
    print('  %-12s n=%3d   mid-IEM %+6.3f   imp-mid %+6.3f   IEM-in-bucket %5.1f%%'%(
        s,len(v),statistics.mean([x[3]-x[4] for x in v]),
        statistics.mean([x[2]-x[3] for x in v]),
        100.0*sum(1 for x in v if x[6])/len(v)))
print('')
print('=== D. DISTRIBUTION of (bucketmid - IEM), degF ===')
for lab,f in (('HIGH',lambda r:r[1]=='HIGH'),('LOW',lambda r:r[1]=='LOW')):
    c=defaultdict(int)
    for r in core:
        if f(r): c[round(r[3]-r[4])]+=1
    n=sum(c.values())
    print('  %s (n=%d): '%(lab,n)+'  '.join('%+d:%d(%.0f%%)'%(k,v,100.0*v/n) for k,v in sorted(c.items())))

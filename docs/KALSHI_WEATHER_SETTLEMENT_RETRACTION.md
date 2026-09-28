# Kalshi Weather Settlement — Retraction and Corrected Definition

Last updated: 2026-09-28. Evidence dates 2026-09-24 to 2026-09-26.

## Retraction

Between 2026-09-24 and 2026-09-25 this project reported a **+1.00F definitional edge (t +10.6)**
in Kalshi daily temperature markets, on the theory that settlement used the maximum of 24 hourly
METAR readings while the market priced the continuous daily maximum.

**That is wrong and the opposite is true. Kalshi settles on the CONTINUOUS daily extremum.**
The apparent edge was entirely an artifact of my own settlement proxy.

## How it was caught

The decisive test compares the market's implied mean to the bucket Kalshi **actually settled**
— no METAR, no IEM, no assumption about what settlement means:

```
implied mean - Kalshi settled bucket mid
  ALL    n=439   -0.056   t -0.86
  HIGH   n=233   -0.110   t -1.15
  LOW    n=206   +0.004   t +0.04
```

The market is calibrated. And the proxy error is exactly the size of the reported "edge":

```
Kalshi settled bucket mid - my IEM hourly extremum
  HIGH   +0.989  (t +17.0)
  LOW    -0.473  (t  -8.5)
```

A strike-convention check against Kalshi's own `result` matched only **55.1%** of station-days,
and on **47%** of high-temperature days the IEM-derived value landed a full 2F bucket below the
one that settled. The join was broken about half the time.

## Why three prior tests all missed it

- `impmean2.py` reported implied minus my hourly max at **+1.002 (t +10.6)** — the proxy error.
- `contmax.py` reported implied minus the continuous max at **-0.048 (t -0.47)** — which was
  the market being *right*, misread as confirmation.
- `hilo.py` reported a clean sign flip, HIGH +1.002 and LOW -0.765, **all 8 series correct
  sign**, which I presented as decisive.

**The sign flip did not prove what I said it proved.** It tested whether the *implied mean* was
biased and correctly eliminated three artifacts there: warm arithmetic in the implied mean,
regression toward climatology, and a general warm bias in forecasts. It never touched the
*settlement* side. A sampled extremum is biased low for maxima and high for minima **by
construction**, so it produces the sign flip on its own.

The high/low asymmetry (0.99 against 0.47) that I explained with flat-minima/sharp-maxima
physics is real physics — it just describes **my** sampling error, not Kalshi's settlement.

All three runs shared one unvalidated proxy, so no amount of agreement between them could
detect it.

## The process rule this produced

**Before measuring any market against an external truth source, first check that the proxy
reproduces the venue's own realised settlements, row by row.** Not "does it match a table the
venue displays" — the realised settlement itself.

The earlier note that IEM was "VALIDATED, ATL 90/86/80 exact match" validated my hourly readings
against the *hourly table displayed* on weather.com/kalshi, which is a different object from the
settlement value.

Three corollaries:

1. Write the validation run before the measurement run. Require ~100% agreement. 55% is a
   broken join; even 90% means the residual 10% can carry the whole effect.
2. **A falsification test only falsifies the side it touches.** Name which half of the
   comparison it constrains, and say so out loud rather than claiming "no artifact can produce
   this."
3. Prefer a formulation that never needs the external source at all. Implied mean against the
   venue's own settled bucket needed no METAR, took minutes, and was the correct test from the
   start.

## What still stands in this family

The longshot bias (ratio 0.65 in the 2-15c band, the strongest measured anywhere in this
project) and the 5-minute impossible-bucket kill (145 of 145 events) both used Kalshi's own
prices and outcomes rather than the IEM proxy, so they are unaffected. Both were already
measured as too small to trade.

## Corrected market facts

- Settlement is the **continuous daily extremum** at the named ICAO station, not a sample of
  hourly observations. The weather.com/kalshi page *displays* 24 hourly slots; that display is
  not the settlement value.
- Daily temperature markets **do not exist before roughly T-24h to T-48h**. Queried at T-48h
  and T-72h, 0 of 2,807 events returned usable ladders.
- Buckets are 2F wide and contiguous over integers: `[fl, cp]` inclusive, with the next bucket
  starting at `cp + 1`, plus a `less` tail and a `greater` tail.
- Chicago and Houston each have two stations (KORD/KMDW, KIAH/KHOU). Resolve which series uses
  which before trusting any join — though the correct approach is to avoid the join entirely.

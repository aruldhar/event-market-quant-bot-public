# Kalshi Weather Ask-Only Maker Test — Preregistration

**Frozen 2026-09-27. Evaluate no earlier than 2026-11-01.**

This document and `scripts/kalshi_research/wxholdout.py` were committed before any holdout data
existed. Neither may be edited. If a parameter below needs to change, that is a new hypothesis
with a new document and a new forward window, not an amendment to this one.

## Why a forward test rather than another slice

The corrected market-making grid (`KALSHI_WEATHER_MARKET_MAKING_RESULT.md`) shows
**+0.278c per quoted hour (t +2.27)** for ask-only quoting in the 0-20c band, 12-24 hours from
close, at queue depth 50 with maker fees correctly at zero.

**That cell was chosen after seeing the grid.** A rule frozen earlier using the *opposite*
time-to-close half had already failed. A t of 2.27 on a post-hoc slice is a hypothesis, not
evidence — and this project has produced six documented cases of a weighted or post-hoc
measure surviving until an executable or out-of-sample test erased it.

The holdout is time itself. `wxmmf.py` pulls **settled** markets, so any event settling after
the freeze date is data that did not exist when the rule was written.

Cost of this test: zero dollars, zero capital, two commands.

## The frozen rule — no parameter may change

- **Series**: KXHIGHNY, KXHIGHTATL, KXHIGHLAX, KXHIGHTPHX, KXLOWTNYC, KXLOWTATL, KXLOWTLAX,
  KXLOWTPHX
- **Action**: ask-only. Rest an offer at the **previous** hour's closing ask. Never quote the
  bid. (Using the current bar's close would let information from after the fill set the price
  we quoted — the one-bar lookahead that faked a z=+41 signal earlier in this project.)
- **Filter**: quote midpoint **< 20c** and time-to-close **> 12 hours**
- **Queue assumption**: 50 contracts must trade at the level before we fill
- **Fees**: maker fee **0** (all eight series are `fee_type: quadratic`)
- **Exit**: hold to settlement. No exits, no targets, no stops.
- **Metric**: mean P&L per **quoted hour**, with unfilled hours counted as 0.0
- **Skips**: hours where bid <= 0, ask >= 100, or ask <= bid; block trades; truncated tapes

## The prediction and the gate — stated before the data exists

Point prediction **+0.28c per quoted hour**. The 24h+ sub-bucket should also be positive
(+0.12c).

**PASS requires mean > 0 with t > 2.0 on at least 20,000 forward quoted hours.**

Anything less is a FAIL and the direction closes. **A positive mean with t < 2.0 is a FAIL,
not "encouraging".** If it passes, the next step is still small: real money sized to the
measured edge, not to the hoped-for one.

## How to run it

```bash
# 1. Refresh the dataset (~30 min). Pulls all settled markets for the eight series.
sudo docker run -d --name wxmm2 -v /var/lib/kalshi-research:/data \
  python:3.12-slim python3 -u /data/wxmmf.py

# 2. Evaluate. Filters to markets settling after the cutoff and runs only the frozen arm.
sudo docker run --rm -v /var/lib/kalshi-research:/data \
  python:3.12-slim python3 -u /data/wxholdout.py
```

Run today, step 2 prints `NO HOLDOUT DATA YET` — confirmed on 2026-09-27, which validates the
cutoff logic before any holdout data exists.

Every parameter is hard-coded in `wxholdout.py`: cutoff 2026-09-28, mid < 20c, ttc > 12h, queue
50, maker fee 0, gate n >= 20000 and t > 2.0. **Freezing the evaluator matters as much as
freezing the rule** — it removes the room to adjust the analysis once the numbers are visible,
which is where this project's six weighting artifacts came from.

## Known limits, to be stated alongside any result

- Queue 200 decays the same cell to +0.097c (t 0.99). The effect is **queue-position
  dependent**, so it rewards standing size and presence rather than insight. A new entrant does
  not start at the front of the book.
- The simulation does not model **our own** order changing queue position or fill probability.
- Selling YES at 10c requires posting the other 90c as collateral, so breadth across markets
  needs real capital even though the per-hour edge is small.
- Weather settles on the **continuous** daily extremum. Do not reintroduce any METAR or IEM
  proxy into the P&L — settlement comes from Kalshi's own `result` field. See
  `KALSHI_WEATHER_SETTLEMENT_RETRACTION.md` for why.

# Kalshi Weather Market Making — Result

Last updated: 2026-09-28. Evidence date 2026-09-27.

The cleanest dataset produced by this project: **3,360 markets, 121,157 candles, 2,326,029 real
trades, only 3 truncated tapes.** Eight series (NYC / ATL / LAX / PHX, high and low), all
settled markets. Scripts: `scripts/kalshi_research/wxmmf.py` (fetch), `wxmms3.py` (analysis).

The 12,000-trade cap that made the KXBTC15M fill simulation unusable — it silently selected
markets 2.3x thinner than average — **does not bite here.** Weather tapes are hundreds of
prints and return complete in one call with an empty cursor.

## Method

The resting quote is the **previous** hour's closing bid and ask, never the current bar's.
Using the same bar's close would let information from after the trade set the price we quoted;
that is the `px[m-1]` lookahead documented in `KALSHI_EDGE_SEARCH_CLOSEOUT.md`.

Block trades are skipped — a negotiated off-book print would not fill a resting order. Fills
are classified by **price against the prevailing quote**, not by `taker_book_side`: that field
reads `'bid'` on 77% of at-or-above-ask prints, so it describes the taker's own order side
rather than which resting side was hit, and is not a reliable classifier.

Maker fees are **zero** — all eight series are `fee_type: quadratic`. An earlier version of
this analysis charged the *taker* coefficient on maker fills and understated every ask-only
cell by roughly 0.63c per fill at a 10c quote. See `KALSHI_MAKER_FEE_CORRECTION.md`.

## Two-sided market making fails

Per quoted hour, one contract each side, **zero fees**:

| queue depth | two-sided fill rate | P&L per quoted hour |
|---|---|---|
| 0 | 31.3% | -0.124c (t -1.65) |
| 50 | 13.5% | -0.762c (t -11.15) |
| 200 | 6.5% | -0.731c (t -13.16) |

The spread captured when both sides fill is 2.33c, but the one-sided hours lose more than that.
This is adverse selection, not cost — the same verdict as KXBTC15M, reached with fees removed.

Per fill at queue 0, selling at our ask is **+0.230c** and buying at our bid is **-0.468c**,
consistent with the wings being overpriced.

## The key finding: every positive cell is queue position 0

Ask-only, per quoted hour, maker fee 0:

| 0-20c band | 24h+ | 12-24h | 6-12h | 0-6h |
|---|---|---|---|---|
| queue 0 | +0.524 | +0.668 | +0.403 | +0.917 |
| queue 50 | +0.124 | **+0.278** | -0.125 | -0.485 |
| queue 200 | +0.018 | +0.097 | -0.203 | -1.007 |

**Being first in the book is not a strategy, it is an incumbency** — an infrastructure and
standing-size advantage unavailable to a new entrant.

Note that the time-to-close ordering **inverts with queue depth**: near-expiry is best at queue
0 and worst at queue 50 and beyond. A rule frozen using the queue-0 ordering (`ttc < 12h`)
therefore failed: **-0.225c all dates, -0.552c first half, +0.122c second half.** It was not
re-fitted to `ttc > 12h` — that would be this project's signature cherry-pick. The surviving
cell is instead preregistered for a forward test in
`KALSHI_WEATHER_MAKER_PREREGISTRATION.md`.

Bid-only is negative in all five price bands at t of about -2.6. The single eye-catching cell
(40-60c at 0-6h: +10.56c, t +2.58, n=136) decays to +3.66 at queue 50 and -0.97 at queue 200,
which is what noise does.

## What survives

At queue 50 with fees correctly at zero, the 0-20c ask-only band is **+0.124c (t 1.84) at 24h+
and +0.278c (t 2.27) at 12-24h** over roughly 40,000 quoted hours. Break-even to marginally
positive, entirely dependent on queue position, and gone by queue 200.

That is the precondition a rebate business needs — Kalshi pays for resting orders whether or
not they fill — because break-even quoting plus a rebate is positive, while a losing quote
needs the rebate to cover the bleed first. Settling that requires live capital rather than more
backtesting.

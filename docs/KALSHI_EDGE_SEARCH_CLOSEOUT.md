# Kalshi Edge Search — Closeout

Last updated: 2026-09-28 (UTC evidence timestamps)

This document closes the broad search for a tradeable edge on Kalshi that ran from the
KXBTC15M work through 2026-09-27. It records eleven closed directions, the single mechanism
that explains most of them, the one hypothesis still live, and the methodological findings
that are the most reusable output of the whole effort.

No entry in this document establishes executable market edge or profitability.

## The one-sentence result

Every observable inefficiency measured on Kalshi was real and was sized at or just under the
cost of trading it. This is not eleven unlucky draws; it is the shape of the venue.

Representative reconciliations, each computed independently:

| Effect | Gross size | Cost to capture | Residual |
|---|---|---|---|
| Sports favourite/longshot bias | ~3.5c | ~2c spread + ~1.2c fees | ~0.3c |
| Weather longshot overpricing (1-5c band) | 1.57c | 1.11c spread | +0.40c, 1 of 10 cells |
| Weather ladder dutch book (6 legs) | ~3c | ~4.8c fee load | negative |
| Multi-outcome sell-all (`mutually_exclusive`) | up to 5c | ~6c fee load | ~ -1c |
| Weather implied distribution 40% too wide | several c | 4-7c spread | negative both directions |
| KXBTC15M at-the-money taker | ~0 | 3.5% of capital at the fee peak | negative |

## Closed directions

### KXBTC15M (the original direction)
Calibration is ~1.0 with complete coverage. GBM/XGBoost models score worse than the mid. The
mom5/zscore signal passed a flipped control and a one-way split, then failed a symmetric
fit-B-trade-A test with coefficients flipping sign between halves. The preregistered mom15
rule went +1.35c in development to **-0.57c (t -0.71, n=1998)** on a sealed holdout. Two-sided
market making with fees set to zero is +0.09c only at queue 0, -1.24c at queue 200; adverse
selection is 11x the spread and break-even needs a 91.9% two-sided fill rate. Exit rules are
dead by optional stopping — every timed exit is significantly negative and monotone in holding
time. See `KXBTC15M_H3_RESEARCH_CLOSEOUT.md`.

### Structural advantages
14 series carry `fee_multiplier` 0 and 19 (all MLB) carry 0.5. Only KXBTCY is liquid among the
zero-fee set, and market making there is break-even even though adverse selection is 3x smaller
than in KXBTC15M. Ladder "arbitrage" resolves to the time value of money, capped at two
contracts. Cost and sensitivity scale together, so cheaper execution does not help.

### Kalshi to Polymarket basis
The one clean pair is KXBTCD hour-12 against the Polymarket daily, both settling 16:00 UTC,
overlapping about one hour a day. 174 strike-days agree on resolution 100% of the time
including two near-misses. Mean mid gap is **+0.49c against a ~2.55c hurdle**. Long-dated
apparent arbitrage is interest rates and must beat an 8-9% cost of carry.

### Weather settlement definition — RETRACTED
An apparent +1.00F definitional edge (t +10.6) was **my own broken settlement proxy**, not a
market bias. Full retraction and the corrected settlement definition are in
`KALSHI_WEATHER_SETTLEMENT_RETRACTION.md`.

### Weather forecast model
Markets do not exist before roughly T-24h, so there is no longer horizon to test. The implied
distribution is genuinely ~40% too wide at T-24h (PIT middle 52.0% against 40.0% expected) but
the whole effect sits inside a 4-7c spread: buying at the ask and selling at the bid both lose
in every price band. A better forecast cannot be monetised through that.

### Strike-ladder arbitrage
177,450 structural relations across 38,484 open markets in 3,432 series produced **one
violation worth $0.13**. See `KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md`.

### Multi-outcome arbitrage
4,425 sell-all tests and 53,068 exclusive-pair tests across 5,021 `mutually_exclusive` events
produced **zero**. Gross violations of the 100-cent line are routine (sum of bids: median 92,
p90 99, max 105.0) and the fee load beats them by about a cent.

### Weather market making
3,357 markets, 2,326,029 real trades, 78,540 quoted hours. Two-sided quoting is -0.124c/hr at
queue 0 and -0.762c at queue 50 **with maker fees correctly set to zero**. Every positive cell
in the ask-only grid is a queue-position-0 artifact that decays to ~0 by queue 200. See
`KALSHI_WEATHER_MARKET_MAKING_RESULT.md`.

### Sports favourite/longshot bias
A calibration table showed +3 to +7c maker and +2 to +4.6c taker on 65-99c favourites across
732 games. An executable backtest turned that into **-2.75c (t -9.42)**: contract-weighting
over-weights trades from games where the favourite is already cruising, so the measure
conditioned on in-game state. A pre-game entry test then found **no favourite band reaching
t = 1.3 at any entry horizon**.

### Sports in-game repricing lag
Buying the scoring team at the ask on the first bar after a scoring play and exiting at the bid
returns -3.1c to -3.6c (t -2.8 to -15.1) across 322 events. Those are the round-trip costs, so
gross drift is zero.

### Sports game-state modelling
On a 271-game 2025 holdout, Kalshi's price is **significantly more accurate than nflfastR's**
win probability (logloss 0.2031 against 0.2298, t -2.67). Strategy P&L degrades monotonically
as model disagreement grows, the winner's-curse signature. Do not build a game-state model.

## Still live

One hypothesis, preregistered with both the rule and the evaluator frozen before the data
exists: `KALSHI_WEATHER_MAKER_PREREGISTRATION.md`. Costs no capital. Evaluate after 2026-11-01.

One survey in progress: `CROSS_VENUE_PERP_FUNDING_SURVEY.md`.

## Methodological findings — the reusable output

Six times in this project a weighted or normalised measure showed a large edge and an
executable simulation erased it. This is the single most transferable result here.

1. **Crypto minute-weighted +5c** became entry-once +2c (t 0.49).
2. **Sports contract-weighted +4.64c** became an executable backtest at -2.75c.
3. **In-game "56% of the move remains"** became an event study at -3.4c. The fraction-of-
   eventual-move measure conditioned on the future.
4. **A 32-game logloss win** reversed on a 271-game holdout.
5. **Weather implied-mean +1.00F** was a settlement proxy error.
6. **A maker grid positive at queue 0** decayed to zero at realistic queue depth.

The rule that follows: *any statistic that weights by volume or time, or normalises by a future
value, is not evidence of a tradeable edge.* Only simulate an actual decision — one entry per
independent unit, an executable price, both fees, clustered by the true independent unit.

Two more specific traps, each of which produced a large false positive:

- **Lookahead by one bar.** `btc_minutes.csv` is end-of-minute, so indexing `px[m]` leaks 60
  seconds of future BTC and faked a z=+41 signal that was really z=+1.6. The reusable
  diagnostic is an alignment probe: check whether `px[close//60 - k] > K` reproduces the
  realised outcome.
- **Banding by a normalised weight instead of a price.** Banding ladder legs by
  `p_i / sum(p)` rather than by the actual ask manufactured a 13.4c favourite edge that was
  -4.44c at the price you could trade.

And one process rule, learned the hard way on 2026-09-27: **read the full research note, not its one-line summary.** A stale one-line summary said a direction was untested when the file itself recorded it
as dead three ways, and a whole research plan was built on the summary.

## Related documents

- `KALSHI_API_SCHEMA_REFERENCE.md` — the API field semantics, five of which were guessed wrong
- `KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md`
- `KALSHI_WEATHER_SETTLEMENT_RETRACTION.md`
- `KALSHI_WEATHER_MARKET_MAKING_RESULT.md`
- `KALSHI_MAKER_FEE_CORRECTION.md`
- `KALSHI_WEATHER_MAKER_PREREGISTRATION.md`
- `CROSS_VENUE_PERP_FUNDING_SURVEY.md`
- `scripts/kalshi_research/` — the analysis scripts, including the frozen evaluator

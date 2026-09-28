# Correction — Makers Pay Nothing on 98.9% of Kalshi

Last updated: 2026-09-28. Evidence date 2026-09-27.

## The correction

Much of this project's analysis charged the **taker** fee coefficient to **maker** activity.
On almost the entire exchange, makers owe nothing at all.

The authoritative field is `fee_type` on the `/series` object:

```
quadratic                        = 14,235 series (98.9%)   taker pays, maker pays ZERO
quadratic_with_maker_fees        =    160
quadratic_with_combo_maker_fees  =      3
```

Published schedule, effective 2026-07-07:

- taker `0.07 x C x P x (1 - P) x M_taker`
- maker `0.0175 x C x P x (1 - P) x M_maker` — one quarter the coefficient, **and `M_maker`
  defaults to 0**

So on a `quadratic` series, a resting order costs nothing to have filled. All weather series
are `quadratic`. `KXMLBGAME` is the awkward exception: `fee_multiplier` 0.5 **and**
`quadratic_with_maker_fees`, so the half-fee sport is one of the 160 that does charge makers.
`KXBTCY` is `fee_multiplier` 0, free on both sides.

## What this corrects, and what it does not

**Corrected.** The weather market-making grid charged the taker coefficient on maker fills. Its
"with fee" column was wrong and the **zero-fee column is the correct one**. The entire ask-only
grid was understated by roughly 0.63c per fill at a 10c quote — the difference between
"break-even" and a small positive margin. See `KALSHI_WEATHER_MARKET_MAKING_RESULT.md`.

**Not corrected.** The arbitrage screens in `KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md` needed
executable crossing prices, so taker fees were the right charge there and those results stand.

**Not rescued.** Two-sided market making still fails at zero fee: -0.124c/hr at queue 0 and
-0.762c at queue 50. The binding constraint there was always adverse selection, never the toll.

## The general rule

**"Fees killed it" is a statement about taker strategies only.** Every conclusion in this
project of the form "the effect was real but the fee ate it" applies to crossing the spread.
The cost side of every resting-order strategy was overstated until this was found.

This does not change the headline finding — observable biases on Kalshi are sized at or under
the cost of trading them — because for taker strategies the spread alone is usually enough to
close the gap. It does mean the maker side deserved more attention than it got, which is why
the one remaining live hypothesis is a maker test.

## How it was found

Not from the documentation. A blog reading of the fee-schedule PDF suggested separate maker and
taker formulas; the API was then queried directly and `fee_type` settled it by census. This is
the sixth API field in this project whose semantics were guessed wrong before being dumped —
see `KALSHI_API_SCHEMA_REFERENCE.md`.

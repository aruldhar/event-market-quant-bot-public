# KXBTC15M H3 causal time-window diagnostic

## Question

Holding the accepted H3 rule and causal native monitoring fixed, does allowing
the same 90%-to-below-98% favored-midpoint trigger earlier than the final
4-to-5-minute window improve or damage realized development economics?

## Frozen mechanics

- Frozen 96-market development population; the 26-market holdout remains
  sealed.
- Raw HTTP response receipt time is causal availability.
- Every archived response is evaluated; nominal capture cadence is about 0.5
  seconds with jitter.
- Favored midpoint band is `>= 0.90` and `< 0.98`.
- One-second entry latency, $100 maximum budget, archived full depth,
  whole-contract fills, and conservative frozen KXBTC15M fees.
- Unprotected delayed entry, as supported by the frequency diagnostic.
- Protected exit target equal to 50% of maximum net settlement profit.
- Ten-second delayed preclose full-depth fallback; settlement only after a
  recorded full-depth liquidity failure.
- At most one filled entry per market and scenario.

## Predeclared windows

The independent windows are:

- `04_240_300s`: 4 to 5 minutes remaining, the causal-native baseline;
- `05_300_450s`: 5 to 7.5 minutes remaining;
- `06_450_600s`: 7.5 to 10 minutes remaining;
- `07_600_900s`: 10 to 15 minutes remaining.

Each independent window selects its first qualifying trigger. These rows are
counterfactual alternatives and must not be summed as four trades per market.

`expanded_first_240_900s` is the directly deployable expansion: monitor from
15 minutes through 4 minutes remaining and take the first qualifying trigger
across the combined span. It remains one trade at most per market.

## Integrity and coverage

The 4-to-5-minute row must reproduce every market-level decision, fill, exit,
and P&L from the causal native unprotected frequency scenario and must retain
57 filled entries. Failure stops the diagnostic.

Because historical recorders may start shortly after market open, each row
reports observed coverage. Both mean and minimum per-market coverage are
retained; missing early seconds are not forward-filled or inferred.

## Metrics

The primary outcome is mean P&L per eligible market, assigning $0 to no-trade
markets. Each earlier-window policy is paired market by market with the causal
4-to-5-minute baseline. A deterministic market-cluster bootstrap reports the
95% interval for that paired difference.

Secondary metrics include trigger/fill counts, conditional mean per fill,
profitable rate, target-fill and fallback rates, favored-side settlement win
rate, full-capital-loss rate, 5% tail, worst P&L, median decision time, entry
price, chronological earlier/later stability, coverage, and signal origin.

## Interpretation boundary

This is a four-window development comparison plus one predeclared expanded
policy. It exposes multiplicity and cannot authorize choosing the largest row
as if it were an untouched result. The 90%-to-below-98% band is deliberately
unchanged; lower-band analysis is a later and separately labelled diagnostic.

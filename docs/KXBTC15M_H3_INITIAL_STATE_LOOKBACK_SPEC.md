# KXBTC15M H3 Initial-State Native Lookback Diagnostic

## Question

For the 35 accepted H3 entries whose first native observation inside the
4-to-5-minute window was already in the 90%-to-below-98% favored band, what did
the same favored side do during the preceding 5-to-7.5-minute window?

This diagnostic asks whether persistence, repeated band episodes, or favored-
side changes are sufficiently structured to justify defining one causal
earlier-entry candidate later.

## Selection and lookahead boundary

The 35-market subgroup is defined using its state at five minutes. That label
is not available earlier. Therefore:

- path summaries are descriptive;
- counterfactual entries are explicitly future-selected;
- the final surviving episode is an additional lookahead label;
- no row in this diagnostic is a deployable rule or profitability validation.

A later causal candidate must be evaluated on all 96 development markets and
must use only information known at its decision time.

## Frozen inputs

- Same 96 development markets; the 26-market holdout remains sealed.
- Raw HTTP response receipt time and every archived native response.
- Frozen H3 baseline: 4-to-5 minutes, favored midpoint 90% inclusive to below
  98%, one-second latency, full depth, $100 maximum including fees.
- Frozen protected 50%-of-maximum exit and ten-second preclose fallback.
- No external BTC feed, authentication, or orders.

The analyzer must reproduce 57 native H3 entries and exactly 35
`initial_state` entries before writing a report. Each selected market must have
at least 95% timestamp coverage of the 5-to-7.5-minute lookback.

## Path measurements

Each selected market records:

- native observation coverage and counts;
- fraction of usable observations in the same-side entry band;
- fraction favoring the eventual baseline side;
- number of same-side band episodes and exits;
- favored-side changes;
- below-band, above-band, and opposite-side observation counts;
- first earlier same-side band observation;
- start, age, and native observation count of the final episode that contains
  the baseline decision.

An episode table preserves every same-side in-band run in timestamp order.

## Descriptive counterfactuals

The report compares the selected subgroup's frozen baseline with:

1. first same-side band observation during 5-to-7.5 minutes;
2. start of the final episode that survives to baseline;
3. the 5-, 15-, 30-, and 60-second native milestones of that final episode.

Earlier fills must execute after the same one-second delay and strictly before
the five-minute boundary. Missing earlier entries count as $0 per selected
market. The final-episode rows are upper-bound descriptions because survival
to baseline is known in advance.

## Correlation screen

Spearman rank correlations relate six predeclared path features to the first-
earlier counterfactual P&L and its increment versus baseline. The report shows
bootstrap intervals plus earlier-64 and later-32 chronological diagnostics.

A correlation is not considered actionable merely because its point estimate
is large. It must have adequate sample size, a reasonably bounded interval,
the same direction in both chronological segments, and a plausible causal
translation. Even then, it may motivate only one new bounded development rule.

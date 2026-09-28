# KXBTC15M H3 Causal Early-Persistence Diagnostic

## Question

Can a short, causally observable period of uninterrupted membership in the
favored 90%-to-below-98% band identify safe entries during 5-to-7.5 minutes
remaining, without relying on the future fact that a market is still in-band
at five minutes?

## Preregistered ladder

The only persistence thresholds are 0, 1, 2, and 5 elapsed seconds. Testing 3
or 4 seconds after seeing these results is not part of this diagnostic.

At each native response:

1. A favored side in the band arms a new episode.
2. Every subsequent native response must retain that same favored side inside
   the band.
3. An unavailable quote, band exit, or favored-side change resets the episode.
4. A changed side may arm a new episode immediately if it is itself in-band.
5. Once elapsed receipt time reaches the threshold, the standard one-second
   delayed full-depth fill is attempted.
6. The fill must execute strictly before five minutes remain.

The zero-second strict policy is the immediate first-trigger candidate, but its
delayed fill must still occur before five minutes.

The report also includes one non-selectable historical control. It reproduces
the prior timing diagnostic's decision-window convention, which allowed a
signal observed before five minutes to execute just after the boundary. This
separate row prevents a boundary-crossing fill from being silently mixed into
the new strict policies.

## Frozen mechanics

- Same 96 development markets; separate 26-market holdout sealed.
- Causal raw HTTP response receipt times and every archived native response.
- Favored midpoint 90% inclusive to below 98%.
- One-second entry latency, full depth, $100 maximum including fees.
- Protected 50%-of-maximum target and ten-second preclose fallback.
- At most one position cycle; no overlapping or compounded exposure.
- No external BTC data, authentication, or orders.

## Policy variants

For every threshold:

- `early_only`: take the qualifying 5-to-7.5-minute entry or do not trade.
- `early_else_baseline`: take the early entry if filled; otherwise attempt the
  frozen 4-to-5-minute H3 baseline.

An early fill replaces, rather than supplements, the baseline cycle.

## Reproduction gates

Before output, the analyzer must reproduce market by market:

- all 57 accepted causal-native 4-to-5-minute baseline entries; and
- the prior decision-window immediate 5-to-7.5-minute control with 52 entries.

Any mismatch fails closed.

## Selection rule

Only strict-cutoff combined policies are eligible for selection. The historical
control can never be selected. A threshold passes if:

1. it has zero full-capital losses;
2. its paired mean P&L difference versus baseline is positive across all 96
   markets;
3. that paired mean difference is also positive in the earlier-64 diagnostic
   segment; and
4. it is positive in the later-32 diagnostic segment.

If multiple thresholds pass, select the shortest passing threshold, not the
threshold with the highest observed mean. Paired bootstrap intervals and tail
metrics remain reported but are not additional post-hoc selection gates.

This is an adaptive development test. Passing defines a candidate for the
sealed holdout; it does not provide an unbiased return estimate or guarantee.

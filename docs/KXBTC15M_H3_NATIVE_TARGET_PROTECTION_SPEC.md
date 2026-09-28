# KXBTC15M H3 Causal-Native Target-Protection Diagnostic

## Question

On the updated 57-entry causal-native H3 population, should a 50%-of-maximum
profit signal cause an unconditional delayed sale, or should the delayed sale
execute only if full-depth net P&L still meets the target?

## Frozen mechanics

- Same 96 development markets; separate 26-market holdout sealed.
- Native raw HTTP response-receipt monitoring.
- First 90%-to-below-98% favored midpoint during 4–5 minutes remaining.
- One-second full-depth entry latency; maximum $100 including fees.
- Target equal to 50% of actual maximum settlement profit.
- Every exit attempt waits at least one second and requires full archived depth.
- Ten-second preclose cash fallback.
- No external BTC feed, authentication, or orders.

## Compared modes

`unprotected_50pct_max`:

1. Detect that a full sale at the observed snapshot meets the target.
2. Wait at least one second.
3. Sell the full position at the delayed executable price even if its net P&L
   has slipped below target.

`protected_50pct_max`:

1. Detect the same target signal and wait the same delay.
2. Sell only if the delayed full-depth execution still meets the target.
3. Otherwise reject that sale and continue monitoring.

This is exit-target protection. It is distinct from entry-state protection,
which was already rejected in the native frequency diagnostic.

## Primary comparison and gates

Mean P&L per all 96 markets, with no-trades assigned $0, and paired bootstrap
95% interval versus protected execution. Report below-target unprotected exits,
target/fallback rates, exposure, tail, and worst P&L.

The analyzer must reproduce all 57 entries exactly in both modes and reproduce
the accepted protected-50% causal-native result market by market before writing
output. Holdout, external-feed, and order flags must remain false.

## Interpretation

This is the last bounded exit-mechanics reassessment necessitated by the native
clock and entry-set change. It remains adaptive development evidence rather than
an unbiased future-return estimate or guarantee.

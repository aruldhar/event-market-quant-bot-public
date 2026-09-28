# KXBTC15M H3 Probability-Band Diagnostic

## Question

After native monitoring and the 4–5-minute entry window were selected on the
development set, does H3's result differ across distinct favored-midpoint
probability bands?

## Frozen mechanics

- Same 96 eligible development markets.
- Separate 26-market holdout remains sealed.
- Raw HTTP response-receipt clock.
- Every archived response is evaluated.
- Entry window: 4–5 minutes remaining.
- Entry mode: unprotected after the frozen one-second latency.
- Budget: at most $100 using whole contracts and conservative fees.
- Archived full-depth execution only.
- Protected target: 50% of maximum settlement profit.
- Cash-exit fallback begins ten seconds before close.
- No external BTC data, authentication, or order code.

## Scenarios

All bands are half-open:

| Scenario | Favored midpoint |
|---|---:|
| `baseline_090_098` | 90% inclusive to below 98% |
| `band_080_090` | 80% inclusive to below 90% |
| `band_090_095` | 90% inclusive to below 95% |
| `band_095_098` | 95% inclusive to below 98% |

The three narrower bands are standalone alternatives, not additive entries.
The combined 90–98% row preserves the accepted H3 baseline and must reproduce
all 57 native-frequency entries exactly.

An 80–98% combined policy is deliberately excluded. Combining the lower and
higher bands would conceal whether one band is weak and would introduce another
operational selection rule. If a specific band survives, its direct policy can
be frozen separately.

## Primary metric

Mean realized P&L per all 96 eligible markets, counting no-trades as $0. Each
scenario is compared with the combined 90–98% baseline using the paired
market-level P&L difference and a deterministic paired-bootstrap 95% interval.

Secondary diagnostics include fills, overlap/new/missed markets, conditional
mean per fill, entry price, maximum possible settlement profit, profitable and
target-fill rates, favored-side outcome, full-capital-loss rate, 5% tail, and
worst result.

## Interpretation boundary

This diagnostic was chosen after earlier development results were observed and
contains multiple comparisons. A favorable row may define a candidate for the
sealed holdout, but it is not an unbiased expected-return estimate and does not
establish guaranteed profitability.

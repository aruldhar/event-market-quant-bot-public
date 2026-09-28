# KXBTC15M H3 Last-Five-Minute Timing Diagnostic

## Question

With native response-by-response monitoring now selected on development data,
does H3 work best only during 4–5 minutes remaining, or should it continue
looking for a first entry later in the same market?

This is an adaptive development diagnostic requested after the broader timing
result was observed. It is not an unbiased preregistered estimate.

## Frozen mechanics

- Development set: the same 96 eligible markets.
- Holdout: the separate 26 markets remain sealed.
- Clock: raw HTTP response receipt time.
- Monitoring: every archived response, approximately 0.5 seconds with jitter.
- Favored midpoint: at least 90% and below 98%.
- Entry mode: the frozen unprotected delayed entry.
- Minimum entry latency: one second.
- Sizing: at most $100, whole contracts, fees included.
- Execution: archived full depth only.
- Exit: protected 50%-of-maximum-profit target.
- Fallback: attempt cash exit beginning ten seconds before close.
- No external BTC data, authentication, API keys, or order code.

## Scenarios

The standalone windows are half-open and disjoint:

| Scenario | Decision time remaining |
|---|---:|
| `04_240_300s` | More than 4m through 5m |
| `03_180_240s` | More than 3m through 4m |
| `02_120_180s` | More than 2m through 3m |
| `01_060_120s` | More than 1m through 2m |
| `00_010_060s` | More than 10s through 1m |
| `expanded_first_010_300s` | First qualifying state from 5m to the 10s cutoff |

The final ten seconds are not an entry window. A signal observed before the
cutoff is also rejected if its one-second delayed executable snapshot arrives
at or after the cutoff. This prevents the strategy from opening a position
after its frozen fallback-exit phase has already begun.

The standalone rows are counterfactual alternatives, not five additive trades.
The expanded row is the direct operational policy: start at five minutes and
continue monitoring only when no earlier entry was taken.

## Primary comparison

For every row, calculate realized P&L per all 96 markets, assigning $0 to a
no-trade market. Compare each market's result with that same market under the
native 4–5-minute baseline. Report the paired mean difference and deterministic
paired-bootstrap 95% interval.

For the expanded policy, that paired difference measures the incremental result
of continuing to search after the 4–5-minute window. Conditional mean P&L per
fill is secondary because changing timing changes which markets enter.

## Required integrity checks

1. Exactly 96 development markets are eligible.
2. Outcome tickers exactly match those 96 markets.
3. The 4–5-minute row exactly reproduces the 57-entry native-frequency result
   market by market.
4. Whenever the 4–5-minute baseline fills, the expanded policy must preserve
   the same first decision, entry, exit reason, and P&L.
5. No delayed entry may fill at or after the ten-second cutoff.
6. Output flags must state that holdout data, external BTC data, authentication,
   and orders were not used.

## Interpretation

The test can reject an unsafe late interval or nominate a last-five-minute
candidate before opening the holdout. Because the comparison was added after
earlier development results were seen and includes multiple windows, the best
row must not be described as an unbiased expected return or guaranteed edge.

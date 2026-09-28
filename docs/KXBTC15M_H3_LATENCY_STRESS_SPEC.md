# KXBTC15M H3 latency stress specification

## Purpose

Measure whether the frozen H3 price-only candidate remains economically viable
when observation-to-execution latency is slower than the accepted one-second
development assumption.

## Frozen strategy

- Development-only 96-market sample; sealed holdout is not opened.
- One previously selected first trigger per market.
- Trigger: `240 < seconds_remaining <= 300` and favored midpoint
  `0.90 <= midpoint < 0.98`.
- Maximum entry budget: $100.
- Archived full-depth marketable execution with conservative taker fees.
- Protected exit target: 50% of the filled position's maximum net settlement
  profit.
- A target signal executes only if the full delayed sale still meets the target
  after fees; otherwise the attempt is rejected and monitoring resumes.
- Ten-second preclose full-depth sale fallback. If full liquidity is unavailable
  before close, settlement is the explicit final fallback.

## Matched latency grid

Two stress modes are evaluated at 1, 2, 3, and 5 seconds:

1. `combined`: entry latency and every exit attempt use the same stressed delay.
2. `exit_only`: entry latency stays at one second while every exit attempt uses
   the stressed delay.

Every rejected target attempt and every preclose sale attempt receives a new
full configured exit delay. Execution uses the first archived snapshot at or
after the required time, so realized delay may exceed configured delay slightly.

## Required gates

- Exactly 52 frozen primary triggers.
- Exactly 416 matched scenario rows: 52 markets times 8 latency settings.
- The one-second result in both stress modes must reproduce the prior protected
  50%-target/preclose scenario P&L for every ticker within `1e-9`.
- No external BTC data.
- No holdout read.
- No authentication or orders.

## Reported evidence

- Entry fill rate.
- Mean P&L per trigger and bootstrap interval.
- Paired mean difference from the matching one-second mode.
- Positive-P&L rate.
- Protected target-fill and preclose-fallback rates.
- Full-capital-loss rate, 5% tail, and worst P&L.
- Mean realized entry and exit latency.
- Earlier-64 versus later-32 chronological stability.

This diagnostic tests execution sensitivity only. It does not authorize a
holdout read, paper orders, demo orders, or real-money trading.

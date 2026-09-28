# KXBTC15M H3 causal delta-risk specification

## Fixed strategy inputs

- 52 previously selected H3 first-trigger decisions.
- Favored midpoint from 90 cents inclusive to 98 cents exclusive.
- First trigger with more than 240 and at most 300 seconds remaining.
- $100 maximum budget and archived full-depth execution.
- Conservative quadratic taker fees.
- Protected profit target equal to 50% of maximum net settlement profit.
- Ten-second preclose fallback.
- The same eight entry/exit latency settings from the completed latency stress.

## Causal delta

For every order-book signal timestamp, use the latest Kalshi BTC live-data value
whose timestamp is less than or equal to that signal. Future chart observations
are prohibited. A chart value two or more seconds old fails closed.

Side-aligned delta is:

- YES position: `chart value - target`
- NO position: `target - chart value`

Positive delta therefore means the chart is currently on the purchased side of
the settlement target.

## Predeclared risk policies

1. No risk overlay.
2. Exit when side-aligned delta is at or below $0.
3. Exit when side-aligned delta is at or below $5.
4. Exit when side-aligned delta is at or below $10.
5. Exit when executable net P&L is at or below -5% of deployed cash.
6. Exit when executable net P&L is at or below -10% of deployed cash.
7. Exit on delta at or below $5 **or** loss at or below -10%.
8. Exit on delta at or below $5 **and** loss at or below -5%.

This is a deliberately small mechanics grid. No additional threshold may be
introduced after reviewing the results on these 52 entries.

## Signal and execution ordering

At each archived order-book observation before the preclose window:

1. Evaluate the protected profit target first.
2. If no target signal is active, evaluate the selected risk policy.
3. Wait the configured exit latency.
4. Attempt to sell the entire position through archived depth.

The protected target executes only if it still meets the target after latency.
A risk exit, once triggered, accepts the delayed full-depth executable result.
Partial risk liquidations are not credited; monitoring resumes after a failed
full-position attempt.

## Interpretation gate

For each latency setting, compare the overlay with its exact no-overlay
counterfactual. Report mean P&L, paired difference, profitable rate, risk-exit
rate, stops of baseline winners, full-capital-loss rate, 5% tail, and worst P&L.

The existing holdout remains sealed. These development results can identify a
simple implementable protection candidate, but cannot provide an unbiased edge
estimate after the extensive exploration already performed.

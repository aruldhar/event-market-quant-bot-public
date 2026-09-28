# KXBTC15M Kalshi chart/order-book lead-lag audit

## Purpose

Test the manual observation that KXBTC15M contract prices may update one or two seconds before the Kalshi BTC chart reflects the corresponding movement.

This is an outcome-blind timing diagnostic, not a strategy-selection experiment.

## Frozen inputs and partition

- The same 100-market frozen development partition used by the raw-depth audit.
- Exactly the 96 markets passing the existing quality gate.
- The verified one-second Kalshi development chart histories: 96 markets and 345,696 total points.
- No outcome, holdout, authenticated endpoint, external BTC feed, or execution action.

## Causal alignment

For every chart timestamp in the final five minutes, use the latest YES best-bid observation timestamped at or before that chart second. Never use a future quote. Skip the aligned second if the latest bid is more than two seconds old.

The primary book state is the executable YES best bid. A two-sided midpoint is not used because one side of the archived book can legitimately be absent, and switching between midpoint and one-sided proxies would create artificial changes. The analysis uses one-second first differences:

- contract change in cents;
- chart change in dollars.

Each eligible market must retain at least 150 of the 301 possible aligned seconds. The report discloses minimum, median, and maximum coverage; it does not silently fill longer missing intervals.

## Fixed lag grid

The initial audit tested integer lags from -5 through +5 seconds and peaked at the positive boundary. The frozen extension tests integer lags from -10 through +15 seconds without changing any alignment, market, phase, or signal definition.

- Positive lag: the order-book change occurs first and the chart change is observed later.
- Negative lag: the chart change occurs first and the order-book change is observed later.
- Zero: same one-second grid timestamp.

Report equal-market-weighted Pearson correlation, a market-cluster bootstrap interval, and directional agreement among nonzero changes.

Run the grid for the complete final five minutes and for each individual minute. Preserve earlier-64 and later-32 diagnostic segments as a stability check.

## Large-jump event study

Study absolute one-second order-book changes of at least 2 cents and at least 5 cents. Suppress another qualifying event for five seconds after selection. The initial event window also peaked at its +5-second boundary, so the frozen extension measures direction-aligned chart changes from ten seconds before through fifteen seconds after each event.

The thresholds are overlapping component diagnostics, not independent experiments.

## Interpretation

A positive peak lag supports the descriptive statement that the order book tends to lead the Kalshi chart at this sampling resolution. It does not prove causation or establish that an external BTC feed would behave the same way.

The audit must not select an entry, exit, or risk-overlay rule. Any trading-policy use requires a separate frozen design and prospective or otherwise untouched validation.

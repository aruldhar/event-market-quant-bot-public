# Sports Calibration Experiment Design

## Status

**Predeclared design. Not yet run.**

This document freezes the first strategy-research question selected by checkpoint 07 before historical outcomes are analyzed. It is intentionally a simple calibration baseline rather than a machine-learning system.

## Research target

```text
Venue: Kalshi
Domain: Sports
Observation horizon: 1–7 days before market close
Strategy family: calibration / behavioral structure
Execution state: research only; no orders
```

Checkpoint-07 census evidence selected this class because the observed 1–7d Sports slice combined a large number of independent events with usable current market structure:

```text
2,144 screened contracts
1,077 unique events
69.0% with spread <= $0.02
median spread = $0.02
median 24h volume = 59.535
median best-bid size = 300
median best-ask size = 568.5
```

These values justify historical study. They do not establish persistent liquidity, mispricing, or profitability.

## Primary question

> When a Kalshi Sports contract is quoted at probability-like level `q` between 1 and 7 days before close, does the YES outcome occur approximately `q` of the time?

For a binary contract:

```text
Y = 1 if final result is YES
Y = 0 if final result is NO
```

Perfect calibration means:

```text
E[Y | q] = q
```

Example: if a set of comparable contracts is observed near 0.70, a calibrated market should resolve YES roughly 70% of the time over a sufficiently large sample.

## Hypotheses

### Null hypothesis

After accounting for sampling uncertainty and correlated contracts within the same event, Kalshi Sports prices are adequately calibrated at the predeclared horizons.

### Research alternative

Calibration error varies systematically with probability level and/or time to close and the pattern is stable in a later chronological holdout.

A stable calibration deviation is only a **candidate structural signal**. It is not a tradable edge until executable prices, fees, depth, latency, fills, and other costs are modeled separately.

## Source data plan

Use only official/public Kalshi data unless a later accepted decision adds another source.

Current official documentation describes a live/historical split:

- older settled markets and their candlesticks move to historical endpoints;
- recent markets/candlesticks remain on live endpoints;
- `GET /historical/cutoff` defines the boundary;
- historical market candlesticks support 1-, 60-, and 1440-minute intervals;
- candlesticks expose YES bid OHLC, YES ask OHLC, trade-price OHLC/mean/previous, volume, and open interest;
- public historical trades are separately available.

The project has not yet live-validated these historical endpoints. The next checkpoint must first archive representative responses, validate schema/lineage, and confirm correct cutoff routing.

## Raw-data requirements

Every network response used by the experiment must be persisted before transformation using the project's existing raw-first principles.

For every source observation preserve:

- source endpoint identity;
- request parameters;
- raw response body;
- local request-start UTC and monotonic time;
- local receive UTC and monotonic time;
- raw source/session/request IDs;
- run ID and manifest linkage;
- schema/version information;
- HTTP/API errors rather than silently skipping them.

Historical reconstruction may use source event time for analytical alignment because the data is already historical. It must never be described as a live first-seen timestamp.

## Eligible market rules

Primary experiment includes only markets satisfying all of the following:

1. source category is Sports;
2. binary market with final result explicitly `yes` or `no`;
3. not a multivariate/combo market in the baseline experiment;
4. close time is available and internally consistent;
5. required historical quote observations can be reconstructed without future information;
6. source bid/ask pair used for `q` is present and not crossed;
7. midpoint is within `[0.10, 0.90]` at the observation anchor;
8. raw lineage and manifest validation pass.

Missing or ambiguous source fields are exclusions with reason codes, not values to impute.

## Observation anchors

Primary analysis uses fixed time-to-close anchors:

```text
7 days before close
3 days before close
1 day before close
```

These anchors remain inside the selected 1–7d research class.

For each anchor, use the latest **real** 1-minute candlestick ending at or before the target timestamp. Never use a candlestick ending after the target.

Do not silently forward-fill arbitrary gaps.

### Staleness threshold

A maximum allowed quote age is **not yet frozen** because the project has not observed historical candlestick sparsity.

Checkpoint 08 may run a data-quality pilot that measures quote-age/missingness distributions **without examining final outcomes**. After that outcome-blind pilot, freeze a staleness threshold in `docs/DECISIONS.md` before running the calibration analysis.

This prevents outcome-driven tuning of the data-availability rule.

## Probability proxy

When both source YES bid and YES ask closes are present and uncrossed:

```text
q_mid = (yes_bid_close + yes_ask_close) / 2
spread = yes_ask_close - yes_bid_close
```

`q_mid` is a market-consensus proxy for calibration analysis. It is **not** an executable entry price.

Later economic testing must use executable side prices plus applicable fees and fill assumptions.

## Dependence structure

Contracts belonging to the same sporting event are not independent.

The dataset must preserve `event_ticker` and any available source series/product identifiers. Uncertainty estimates must cluster or resample by **event**, not pretend every contract row is an independent observation.

Do not infer stronger sample size from alternate lines, thresholds, or related contracts within one event.

## Predeclared probability bins

Primary reliability table uses:

```text
[0.10, 0.20)
[0.20, 0.30)
[0.30, 0.40)
[0.40, 0.50)
[0.50, 0.60)
[0.60, 0.70)
[0.70, 0.80)
[0.80, 0.90]
```

For each anchor and probability bin report:

- number of contract observations;
- number of unique events;
- mean `q_mid`;
- realized YES frequency;
- calibration error `realized_frequency - mean_q_mid`;
- median spread;
- missing/stale exclusion count;
- event-clustered uncertainty interval.

## Primary metrics

### 1. Calibration error

```text
CE_bin = mean(Y) - mean(q_mid)
```

Positive means YES occurred more often than the market proxy implied. Negative means YES occurred less often.

### 2. Expected calibration error

Weighted mean absolute bin error:

```text
ECE = sum_b (n_b / N) * abs(CE_b)
```

This is a descriptive summary; it must not hide the individual reliability table.

### 3. Brier score

```text
Brier = mean((q_mid - Y)^2)
```

Lower is better. It measures probability forecast accuracy but does not by itself identify a tradable bias.

### Secondary diagnostics

- calibration intercept/slope;
- results by source series/product family;
- results by major sport where sample permits;
- spread and quote-age distributions;
- sensitivity to probability-bin boundaries reported separately from the frozen primary bins.

Secondary diagnostics cannot replace the primary result after outcomes are seen.

## Chronological evaluation

Sort underlying events chronologically by close time.

Primary split:

```text
earliest 70% of unique events -> development sample
latest   30% of unique events -> untouched holdout
```

Any exploratory subgroup discovery must occur only in the development sample. The holdout is used once for the predeclared confirmatory evaluation.

Repeated contracts from one event must stay in the same split.

## Minimum evidence gates

Before making a checkpoint-level calibration conclusion:

- at least 1,000 unique eligible events overall;
- at least 100 unique events for any probability-bin × horizon cell used for a specific cell-level claim;
- both chronological partitions contain meaningful coverage across the probability range;
- no material schema/result ambiguity remains unresolved.

Cells below the threshold may be reported descriptively but cannot support a standalone conclusion.

## Decision rules

### No supported structural signal

Use this conclusion when the holdout data does not reproduce a stable directional calibration pattern after event-level uncertainty is accounted for.

### Candidate structural signal

Use this label only when:

1. a predeclared probability/horizon pattern appears in development data;
2. the same direction appears in the chronological holdout;
3. the holdout event-clustered uncertainty interval for that pattern excludes zero;
4. the result is not driven by one event, one series, one sport, obvious stale quotes, or unresolved source semantics.

Even then, do **not** call it profitable or executable.

### Experiment blocked / inconclusive

Use this when:

- historical bid/ask data is too sparse;
- quote staleness cannot be bounded honestly;
- event/product identity is insufficient to control dependence;
- result fields are ambiguous;
- source routing around the historical cutoff is unreliable;
- sample gates are not met.

Blocked data is not converted into a negative or positive strategy result.

## What is intentionally out of scope

This first experiment does not:

- train ML;
- use external sports feeds;
- place paper/demo/real orders;
- assume market midpoint is executable;
- optimize entry/exit timing;
- optimize probability bins after seeing outcomes;
- claim that calibration bias survives costs;
- evaluate maker economics;
- treat correlated contracts as independent;
- use Kalshi's deprecated Market `liquidity` field as an activity measure.

## Required next checkpoint outputs

Checkpoint 08 should produce, in order:

1. historical-endpoint/source validation evidence;
2. a versioned Sports historical dataset schema;
3. a raw-first historical collector with tests;
4. an outcome-blind data-quality/staleness report;
5. a frozen staleness rule;
6. a reproducible calibration analysis implementing this document;
7. an experiment-log entry regardless of result.

Only after the calibration result exists should the project decide whether an execution-cost experiment is justified.

## Checkpoint-08 data-quality result

**Status: blocked before outcome analysis.**

The historical endpoint path and raw-first Sports collector were successfully validated, but the required outcome-blind freshness gate did not produce an acceptable quote-age rule.

Accepted 100-event input run:

`collect_sports_historical_20260809T060907842728Z_94ad3820`

The run contained 100 unique Sports events, 1,200 markets, 3,600 fixed anchors, and 288,210 real one-minute candle rows. Independent manifest validation indexed 4,718 raw records and passed with outcomes unmaterialized.

The predeclared staleness pilot evaluated only 1m, 5m, 15m, 30m, and 1h. No candidate retained >=90% of quote-bearing anchors overall and >=80% within each of 7d, 3d, and 1d.

Observed 100-event quote availability was 73.500%. Horizon availability was 58.667% at 7d, 82.167% at 3d, and 79.667% at 1d. Overall quote-age p90 was 50,183 seconds.

Decision D-027 freezes **no** staleness threshold and blocks this experiment before outcome materialization. Therefore the calibration metrics, chronological development/holdout split, and candidate-signal decision rules in this document were never executed.

This is a data-feasibility result, not a calibration or profitability result.

# BTC Family Quote Feasibility — Checkpoint 10

## Purpose

This is the final outcome-blind family-selection gate before Checkpoint 10 may choose a first BTC historical baseline. It compares `KXBTC15M`, `KXBTC`, and `KXBTCD` using public Kalshi one-minute candlesticks only.

This experiment does **not** inspect final outcomes, test predictive accuracy, claim an edge, choose an external feed, or simulate execution.

## Why Checkpoint-09 time windows are not reused

Checkpoint 09 used T-7d through T-1d because its selected markets could be observed days before close. These BTC families are short-horizon products. A days-before-close window would therefore be scientifically inappropriate.

For this comparison, every selected market is observed only during its own source-defined active lifetime:

```text
open_time <= candle_end <= close_time
```

Every real one-minute candle keeps its exact timestamp and exact `time_to_close_seconds`.

## Equal settlement-cluster sample

The evaluation unit is the settlement cluster, not a contract ticker or candle row.

Exactly 20 clusters are selected for each family using ascending SHA-256 of `event_ticker` from the already completed Checkpoint-10 structural inventory.

- `KXBTC15M`: selected from already resolved sampled clusters.
- `KXBTC`: selected only from sampled `brti_60s_simple_mean_untrimmed` clusters.
- `KXBTCD`: selected only from sampled `brti_60s_simple_mean_untrimmed` clusters.

The 20-cluster target is fixed. Quote availability, prices, volume, liquidity, and outcomes cannot affect selection.

## Ladder probe design

Fetching every strike from every ladder event would spend thousands of requests while still producing only one settlement outcome per event. For the feasibility screen, each selected `KXBTC` and `KXBTCD` cluster therefore uses three deterministic structural probes.

Markets are ordered by structural strike coordinate and the 25th, 50th, and 75th percentile positions are selected. This is intended only to test whether low/middle/high portions of the ladder have historical quote support. It is not a trading rule and does not claim that three contracts reconstruct the full distribution.

`KXBTC15M` has one probe market per settlement cluster.

## Normalized time bands

Different families have different active durations, so coverage bands are fractions of each market's own lifetime:

- `early`: final time remaining is at least 2/3 of active duration;
- `middle`: final time remaining is at least 1/3 but less than 2/3;
- `late`: final time remaining is less than 1/3.

The bands are diagnostics only. The underlying observation retains exact `time_to_close_seconds` and `normalized_time_remaining`.

## Quote validity

A one-minute observation is valid only when both YES bid and YES ask close fields are present, both lie in `[0, 1]`, and bid is not above ask.

No forward fill, interpolation, synthetic continuity, anchor substitution, or nearest-observation snapping is allowed. Live candlestick requests explicitly set `include_latest_before_start=false`.

## Frozen gates

Base feasibility requires, for each family:

- exactly 20 settlement clusters;
- >=80% cluster coverage with at least one valid quote;
- >=60% probe-market coverage with at least one valid quote;
- >=50% settlement-cluster coverage in each normalized early/middle/late band.

For `KXBTC` and `KXBTCD`, a separate ladder-breadth diagnostic requires >=50% of clusters to have **all three structural probes** represented by a valid quote in **all three** normalized bands.

The ladder-breadth gate does not apply to `KXBTC15M`.

A gate pass establishes historical quote support only. It is not evidence of calibration, prediction, expected value, profitability, or executable fills.

## Dependence rule

Raw candle rows are repeated observations, not independent trials. Multiple ladder contracts remain one settlement cluster. Any later train/development/holdout split must keep a settlement primitive wholly within one partition and must respect settlement-regime boundaries.

## Accepted Checkpoint-10 result

Accepted run:

```text
collect_btc_family_quote_feasibility_20260809T114516450822Z_a232d26c
```

Observed output:

```text
Settlement clusters: 60
Probe markets: 140
Candle requests: 140
Real 1m candle observations: 9,648
Valid uncrossed quote observations: 9,648
```

Family results:

```text
KXBTC15M: cluster_quote=1.000000 early/middle/late=1.000000/1.000000/1.000000
           all_probe_all3=1.000000 status=quote_feasibility_pass

KXBTC:    cluster_quote=1.000000 early/middle/late=1.000000/1.000000/1.000000
           all_probe_all3=0.450000 status=quote_feasibility_pass_ladder_breadth_failed

KXBTCD:   cluster_quote=1.000000 early/middle/late=1.000000/0.950000/1.000000
           all_probe_all3=0.750000 status=quote_feasibility_pass
```

No outcomes, authentication, external predictive feed, or orders were used.

## Family-selection disposition

`KXBTCD` is selected as the first BTC historical baseline family because it passed both the frozen base quote-feasibility gate and the frozen ladder-breadth gate, while exposing a simple cumulative threshold structure suitable for a cross-strike coherence baseline.

`KXBTC15M` remains a qualified secondary BTC benchmark with excellent sampled quote support.

`KXBTC` is not rejected. It passed the base quote-feasibility gate but failed the predeclared three-probe/all-three-band ladder-breadth threshold at 45% versus the frozen 50% requirement. The project does not lower that threshold after seeing the result.

This selection is a research-priority decision only and does not establish predictive edge, profitability, or venue superiority.

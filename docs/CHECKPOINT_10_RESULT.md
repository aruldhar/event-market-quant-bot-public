# Checkpoint 10 Result — BTC-Specific Historical Research Design

Date: 2026-08-09 local Pacific / 2026-08-09 UTC.

## Status

Checkpoint 10 has reached its substantive stopping point and is ready for safe Git closeout.

Phase 1 remains **public, read-only research**. Checkpoint 10 did not authenticate, place or cancel orders, paper trade, demo trade, use real funds, or claim profitability.

## Purpose

Checkpoint 10 replaced broad category ranking with BTC-specific research-unit design. The checkpoint asked four questions in order:

1. What are the actual Kalshi BTC historical market families?
2. What is the correct settlement/dependence unit so correlated strikes are not counted as independent outcomes?
3. Which BTC family has sufficiently trustworthy historical quote support for a first baseline?
4. Does a deliberately simple cross-strike KXBTCD coherence baseline improve untouched predictive scoring?

The project did not select an external BTC predictive feed before these questions were answered.

## BTC structural inventory

Accepted inventory run:

```text
collect_btc_research_unit_inventory_20260809T100753813114Z_5d03b78e
```

Observed inventory summary:

```text
BTC series: 64
Settled BTC events discovered: 44,958
Events sampled for structure: 136
BTC markets: 5,670
Settlement clusters: 262
Resolved at initial inventory stage: 25
Candidate at initial inventory stage: 237
Unresolved: 0
Outcomes materialized: no
Quotes collected: no
External predictive feed used: no
Orders placed: 0
```

Three recurring Series dominated the discovered settled-event population:

```text
KXBTC15M: 22,456 settled events discovered
KXBTCD:   11,249
KXBTC:    11,192
```

Together they represented 44,897 of 44,958 discovered settled BTC events in the inventory crawl. This concentration is descriptive and does not by itself make any Series superior.

## Settlement primitive and cluster result

Checkpoint 10 accepted the following research-unit definitions:

- **Quote observation:** one actual source-returned quote/candle at its exact timestamp. It is a repeated market-state observation, not an independent trial.
- **Contract:** one Kalshi binary market ticker.
- **Settlement primitive:** the smallest source-defined BTC measurement required to determine payoff, including index, statistic, measurement window, boundary, and rule regime.
- **Settlement cluster:** all contracts whose payoffs depend on the same set of settlement primitives.

Development and holdout partitions must have zero settlement-primitive overlap.

For KXBTC/KXBTCD ladders, strike/payoff shape is not part of primitive identity. `below`, `between`, and `above` contracts may share one primitive when they use the same BRTI measurement.

## Historical settlement-rule regimes

Exact preserved rule text showed that KXBTC and KXBTCD are **not stationary rule templates across history**.

The sampled ladder data contained:

```text
KXBTC
  1 x 300-second trimmed BRTI mean, top/bottom 20% removed
  2 x 60-second trimmed BRTI mean, top/bottom 20% removed
 22 x 60-second simple BRTI/RTI mean

KXBTCD
  1 x 60-second trimmed BRTI mean, top/bottom 20% removed
 24 x 60-second simple BRTI/RTI mean
```

Observed transition dates are sample brackets only, not exact production rule-change timestamps.

The all-market semantic resolver then validated every sampled ladder contract:

```text
KXBTC:  2,393 markets -> 25 resolved event clusters -> 25 unique primitives
KXBTCD: 2,915 markets -> 25 resolved event clusters -> 25 unique primitives
Shared primitive groups within ladder sample: 0
Cross-series shared primitive groups: 0
```

The resolution claim applies only to the sampled evidence set. Unsampled historical events require their own semantic proof.

## BTC-family quote-feasibility comparison

Accepted run:

```text
collect_btc_family_quote_feasibility_20260809T114516450822Z_a232d26c
```

Frozen comparison:

- 20 settlement clusters per family;
- actual one-minute candlesticks during each contract's own active lifetime;
- exact `time_to_close_seconds` retained;
- no forward fill, anchor snapping, or synthetic continuity;
- KXBTC/KXBTCD limited to the validated modern `brti_60s_simple_mean_untrimmed` regime;
- three deterministic structural probe strikes per ladder cluster;
- outcome-blind selection.

Observed data:

```text
Settlement clusters: 60
Probe markets: 140
Candle requests: 140
Real one-minute observations: 9,648
Valid uncrossed quote observations: 9,648
```

Results:

```text
KXBTC15M
  cluster quote coverage: 100%
  early/middle/late: 100% / 100% / 100%
  status: quote_feasibility_pass

KXBTC
  cluster quote coverage: 100%
  early/middle/late: 100% / 100% / 100%
  all-three-probe/all-three-band coverage: 45%
  frozen ladder-breadth gate: 50%
  status: quote_feasibility_pass_ladder_breadth_failed

KXBTCD
  cluster quote coverage: 100%
  early/middle/late: 100% / 95% / 100%
  all-three-probe/all-three-band coverage: 75%
  status: quote_feasibility_pass
```

KXBTCD was selected as the first BTC historical baseline family because it passed both the frozen base quote-feasibility and ladder-breadth gates and exposes a simple cumulative threshold structure. KXBTC15M remains a qualified secondary BTC benchmark. KXBTC remains deferred under the existing three-probe ladder design; the 50% gate was not relaxed after seeing its 45% result.

## KXBTCD v1 pre-outcome freeze

Experiment:

```text
kxbtcd_three_probe_monotone_baseline.v1
```

Design fingerprint:

```text
bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4
```

The pilot used the already selected 20 modern-regime KXBTCD settlement clusters and three structural threshold probes (`q25`, `q50`, `q75`). A cluster entered the primary experiment only if all three probes had a real quote at the exact same one-minute timestamp in every normalized early/middle/late band.

Pre-outcome freeze result:

```text
Source clusters: 20
Primary synchronized clusters: 12 (60%)
Frozen minimum: 50%
Development clusters: 8
Untouched holdout clusters: 4
Selected synchronized cross-sections: 50
Pre-outcome prediction rows: 150
API requests made: 0
Outcomes materialized: no
```

The first baseline compared raw quote midpoints with a nonincreasing isotonic/PAVA projection across increasing thresholds. Cluster-weighted log loss was the primary metric; Brier was secondary.

## Development result and recovery

The first development collector preserved all 24 intended development contract responses raw-first, then hit a metadata-join bug during scoring because `functional_strike` was blank in the frozen cross-section artifact. No holdout contracts were requested.

The project did not repeat the API exposure. It built a zero-network offline recovery that verified the failed run and reconstructed the 24 labels from the exact preserved raw responses while recovering strike metadata from the outcome-blind probe artifact.

Accepted recovery source run:

```text
collect_kxbtcd_development_outcomes_20260809T120413222263Z_9b7324be
```

Development scores:

```text
Development clusters: 8
Recovered labels: 24
Scored predictions: 72
Raw log loss:       0.1229517749838280758888888889
Monotone log loss:  0.1226068974322313537500000000
Delta log loss:     0.0003448775515967221388888889
Raw Brier:          0.03170277777777777777777777778
Monotone Brier:     0.03114913194444444444444444444
Delta Brier:        0.00055364583333333333333333334
Raw monotonicity violation rate: 37.5%
Mean absolute adjustment: 0.009652777777777777777777777778
Max absolute adjustment: 0.0700
```

The primary-metric improvement was favorable but tiny. No model, metric, sample, synchronization rule, weighting, or threshold was changed after viewing development results.

## Untouched holdout result

Accepted run:

```text
collect_kxbtcd_holdout_outcomes_20260809T121952744398Z_ec29a2ab
```

The original fingerprinted procedure was reused unchanged.

```text
Holdout clusters: 4
Holdout labels: 12
Scored predictions: 36
Raw log loss:       0.03832137791396992041666666668
Monotone log loss:  0.03832137791396992041666666668
Delta log loss:     0
Raw Brier:          0.01129722222222222222222222222
Monotone Brier:     0.01129722222222222222222222222
Delta Brier:        0
Raw monotonicity violation rate: 0
Mean absolute adjustment: 0
Max absolute adjustment: 0
```

All holdout ladders were already monotone, so the isotonic projection made no change. The small development improvement did **not** replicate out of sample.

## Final scientific disposition

The v1 hypothesis that simple monotone cross-strike post-processing improves KXBTCD forecast quality beyond raw quote midpoints is **not supported by the untouched holdout**.

This result is intentionally narrow:

- it does not establish that KXBTCD contains no predictive information;
- it does not establish market efficiency;
- it does not reject external BTC information or other predeclared models;
- it does not establish expected value or profitability;
- it does not model executable side prices, fees, depth, latency, partial fills, missed fills, or adverse selection;
- the sample is small and intended as a structural pilot rather than an effect-size estimate.

The opened v1 holdout must not be reused as an untouched test set for tuned variants.

## Safety and execution state

Unchanged:

- public read-only Kalshi data only;
- no credentials or authenticated collection;
- no external predictive feed used in v1;
- no order placement or cancellation;
- no paper, demo, or production execution;
- no real funds;
- no profitability claim.

`docs/RISK_POLICY.md` is unchanged.

## Recommended next milestone

After safe Checkpoint-10 closeout, begin:

```text
11 - KXBTCD Baseline Expansion and Reference Feed Reassessment
```

Checkpoint 11 should not tune the failed/neutral v1 monotone baseline against the same holdout. It should compare evidence-based next paths, including whether to:

1. expand KXBTCD to a larger chronologically separated sample with a new outcome firewall;
2. define the simplest external-information hypothesis that would justify revisiting Coinbase/Kraken/BRTI source selection under D-021; or
3. compare another already-qualified BTC family such as KXBTC15M after its own historical rule-regime audit.

No external feed should be selected merely because Checkpoint 10 completed.

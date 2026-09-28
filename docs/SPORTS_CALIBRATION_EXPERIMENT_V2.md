# Sports Calibration Experiment V2 — Exact-Time Event-Balanced Design

## Status

**Predeclared before outcome materialization. Deferred before outcome analysis at Checkpoint-09 closeout; preserved as a qualified secondary research design.**

This is a new experiment. It does not reopen, alter, or weaken the Checkpoint-08 fixed-anchor design or its failed <=1-hour staleness gate.

## Research target

```text
Venue: Kalshi
Domain: Sports
Observation region: 1–7 days before close
Observation source: real source-returned 1-minute candlesticks
Strategy family: calibration / behavioral structure
Execution: research only
```

## Why V2 exists

Checkpoint 08 asked historical quotes to represent exact 7d/3d/1d anchors. The outcome-blind staleness gate showed that the available quote history was too sparse for that meaning without accepting multi-hour-old substitutes. No threshold was frozen and no outcomes were analyzed.

Checkpoint 09 changed the observation question before outcomes were opened:

> When a real two-sided quote observation actually exists between one and seven days before close, what does that source observation say, and exactly how much time remains until close?

The 25-event/category feasibility pilot validated this observation path for Sports and Crypto. Sports retained 96% event-level quote coverage and at least 84% event coverage in each broad time region. This justifies a new Sports experiment; it does not establish calibration or edge.

## Observation identity

Every valid observation keeps:

```text
end_period_ts
time_to_close_seconds = close_time - end_period_ts
q_mid = (yes_bid_close + yes_ask_close) / 2
spread = yes_ask_close - yes_bid_close
```

`time_to_close_seconds` is exact relative to Kalshi's one-minute candle period end. It is not represented as the timestamp of an underlying order-book update.

No quote is snapped to an exact 7d/3d/1d timestamp. No staleness threshold, forward fill, synthetic continuity candle, or missing-quote imputation is used.

## Eligible observation rule

A primary observation must satisfy all of the following:

1. source category is `Sports`;
2. market is finalized binary and not multivariate/combo;
3. source event and market lineage validate;
4. candle is source-returned at one-minute interval;
5. `1 day <= time_to_close <= 7 days`;
6. YES bid and YES ask closes are both present;
7. bid and ask are in `[0, 1]` and bid <= ask;
8. midpoint is in the frozen primary range `[0.10, 0.90]`;
9. exact raw request lineage validates;
10. live-tier requests, if any, used `include_latest_before_start=false`.

Missing/crossed observations are exclusions with explicit reason codes. They are not repaired.

## Event and market sampling

The event is the primary independence unit.

For data collection, eligible markets within an event are ordered by ascending SHA-256 hash of ticker and at most two are selected. Market selection does not use outcome, price, spread, volume, quote availability, or later calibration result.

This prevents events with many alternate lines/thresholds from receiving more sampling opportunity merely because the venue instantiated more contracts.

## Dense-observation problem

The Checkpoint-09 feasibility pilot found severe raw-row concentration:

```text
Sports largest event share ≈ 39.4%
Sports top-decile event share ≈ 68.2%
Crypto largest event share ≈ 38.3%
Crypto top-decile event share ≈ 67.8%
```

Therefore one-minute observations are repeated market states, not independent trials.

Raw row count is never reported as effective sample size.

## Frozen hierarchical weighting rule

For each analysis subset, define:

```text
E    = number of contributing events
M_e  = number of contributing sampled markets in event e
N_em = number of valid observations for market m in event e
```

Each observation j receives normalized analytical weight:

```text
w_emj = 1 / (E * M_e * N_em)
```

Consequences:

- every contributing event has total weight `1/E`;
- sampled markets within an event divide that event's weight equally;
- observations within a market divide that market's weight equally;
- a market with thousands of one-minute rows cannot dominate a market with sparse but valid observations merely because it updates more often.

For a time-band-specific analysis, `E`, `M_e`, and `N_em` are recomputed **inside that band** because coverage differs by time-to-close.

The implementation lives in `src/sports_calibration_v2_design.py` and must reject any input containing a materialized `result` field.

## Time-to-close analysis

Exact continuous `time_to_close_seconds` is retained in every observation.

Primary descriptive calibration is reported in the already frozen feasibility bands:

```text
5–7 days
3–5 days
1–3 days
```

These are analysis strata, not anchors.

A secondary continuous-time diagnostic may be run only after the primary tables are produced. It is limited to a simple weighted calibration regression; it is not an ML search. The continuous predictor is:

```text
z_time = ln(time_to_close_seconds / 86400)
```

and the predeclared secondary specification is:

```text
logit(P(Y=1)) = alpha
              + beta * logit(q_mid)
              + gamma * z_time
              + delta * logit(q_mid) * z_time
```

Use the same hierarchical observation weights and event-level resampling. Do not tune transformations or add interactions after seeing holdout outcomes.

## Probability bins

Primary reliability tables retain the original fixed midpoint bins:

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

For each time band × probability bin report:

- raw observation rows;
- unique markets;
- unique events;
- weighted mean `q_mid`;
- weighted realized YES frequency;
- weighted calibration error;
- median spread;
- event-clustered/resampled uncertainty interval;
- excluded missing/crossed observation counts.

Raw rows are descriptive only; event count and weighted uncertainty control inference.

## Primary metrics

### Weighted calibration error

```text
CE_b = weighted_mean(Y) - weighted_mean(q_mid)
```

### Weighted expected calibration error

```text
ECE = sum_b W_b * abs(CE_b)
```

where `W_b` is the normalized total analytical weight in bin b.

### Weighted Brier score

```text
Brier = sum_i w_i * (q_i - Y_i)^2
```

Weights are normalized to sum to one in the relevant analysis subset.

These are probability-quality measures, not executable-return estimates.

## Dependence and uncertainty

All observations and markets from one event remain together for uncertainty estimation and chronological splitting.

Primary uncertainty uses event-level bootstrap/resampling: sample whole events, carrying every selected market and observation from each resampled event. Do not bootstrap individual one-minute rows as if they were independent.

Series concentration must be reported. If one source `series_ticker` exceeds 25% of eligible events, flag a generalization warning and report series-stratified results. If one source series exceeds 50% of eligible events, do not make a general "Sports" conclusion; scope the result to the observed dominant series or call the general-Sports result inconclusive.

Source series is not assumed to equal a complete economic product-family taxonomy.

## Chronological evaluation

Sort unique underlying events by close time:

```text
earliest 70% -> development
latest   30% -> untouched holdout
```

All markets and observations from an event remain in the same partition.

Hierarchical weights are recomputed separately inside development and holdout so each contributing event has equal influence within its partition.

The holdout is used once for the frozen confirmatory analysis.

## Sample and data-quality gates before outcomes

Before materializing outcomes for V2:

1. complete an outcome-blind scalability sample of at least 100 Sports events;
2. independently validate its manifest/raw/derived lineage;
3. retain >=80% event-level any-quote coverage;
4. retain >=60% sampled-market any-quote coverage;
5. retain >=50% event coverage in each of the 5–7d, 3–5d, and 1–3d bands;
6. report series concentration and observation concentration;
7. verify no synthetic candle, anchor substitution, or result-derived filtering entered the path.

For checkpoint-level calibration conclusions, the final analysis dataset still requires at least:

```text
1,000 unique eligible Sports events overall
100 unique events for any time-band × probability-bin cell used for a standalone claim
```

If collection cannot support those gates under the frozen rules, stop before outcome analysis or report the experiment as sample-limited.

## Decision rules after outcomes are eventually authorized for analysis

### No supported structural signal

Use when the chronological holdout does not reproduce a stable directional calibration pattern after event-balanced weighting and event-level uncertainty.

### Candidate structural signal

Use only when a predeclared pattern:

1. appears in development;
2. repeats in the same direction in holdout;
3. has holdout event-level uncertainty excluding zero;
4. is not explained by one series, one event, stale/synthetic reconstruction, or source ambiguity.

This remains a candidate probability signal, not evidence of executable profit.

### Blocked / inconclusive

Use when data-quality, sample-size, series-concentration, identity, or source-routing gates fail.

## Economic boundary

Even a successful calibration result does not establish a trade.

A later economic experiment must separately use executable bid/ask side prices and model:

- fees;
- displayed depth;
- spread/slippage;
- latency;
- partial fills;
- missed fills;
- adverse selection;
- uncertainty.

No paper execution is authorized by this design.

## Immediate execution sequence

1. Validate this predeclared design and its outcome-blind weighting tests in the canonical repository.
2. Add a Sports-only exact-time collection mode without changing the accepted four-category feasibility evidence.
3. Run a 100-event public/read-only Sports scalability pilot with outcomes hidden.
4. Independently validate the run and re-check quote/series/observation concentration.
5. Only if those gates pass, plan the 1,000-event final historical collection.
6. Do not materialize final YES/NO outcomes until the final pre-outcome data-quality decision is recorded.

## Heterogeneity and subgroup robustness requirement

A large Sports event count does not imply that all Sports markets share one predictive or calibration process. Before any V2 outcomes are materialized, run the predeclared outcome-blind heterogeneity profile in `docs/SPORTS_V2_HETEROGENEITY_PROFILE.md`.

The profiler must characterize sport/league composition and obvious product-family structure using outcome-blind source identity only. After that composition is known, freeze subgroup robustness rules before opening outcomes. A broad Sports conclusion is not authorized merely because the aggregate sample is large.

This requirement specifically prevents MLB, NBA, NFL, combat-sports, golf, or structurally different proposition types from being silently pooled as if they were interchangeable. Aggregate results may later test a platform-level behavioral hypothesis, but any such claim must survive the predeclared subgroup robustness framework.

## Frozen subgroup eligibility policy

Before Sports V2 outcomes are materialized, the validated 100-event heterogeneity profile must be passed through `sports_v2_subgroup_policy.v1`, documented in `docs/SPORTS_V2_SUBGROUP_ELIGIBILITY.md`.

The policy produces named sport, product-family, and sport × product robustness strata using only identity and quote-availability information. Pilot eligibility requires at least 10 independent events, >=80% event quote coverage, >=50% coverage in every time-to-close region, >=50% all-three-region coverage, and the dimension-specific identity/diversity rules documented there.

Eligibility is not a calibration or trading claim. It only freezes which subgroup comparisons are allowed to be treated as predeclared robustness checks later. Unclassified, undersized, sparse, or overly concentrated groups remain descriptive-only. Standalone subgroup calibration claims still must satisfy the final Sports V2 sample/cell requirements after outcomes are eventually authorized.

## Checkpoint-09 closeout disposition

The 100-event Sports V2 scalability path passed its outcome-blind data gates, but subsequent heterogeneity profiling showed that broad Sports is not one homogeneous predictive population. MLB, NFL, and NBA qualified as sport robustness strata and `coach_or_manager_status` qualified as a product-family robustness stratum, while no sport x product-family cell qualified in the 100-event pilot.

Checkpoint 09 therefore **does not materialize Sports V2 outcomes or run this calibration experiment**. The design remains frozen and available as a qualified secondary branch. Any future return to Sports V2 must begin from this predeclared design and the subgroup evidence; it must not invent outcome-driven subgroups or reinterpret the blocked Checkpoint-08 anchor experiment.

Checkpoint 10 instead begins BTC-specific historical research design for a coherent common underlying process. That sequencing decision is not evidence that BTC is more profitable than Sports.

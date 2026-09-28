# KXBTCD Three-Probe Monotone Baseline Experiment — v1

## Status

**Predeclared before outcome materialization.**

Experiment ID:

```text
kxbtcd_three_probe_monotone_baseline.v1
```

This document freezes the first outcome experiment design for the BTC-specific branch. It does not authorize account authentication, order placement, paper execution, profitability analysis, or use of an external BTC predictive feed.

## Why KXBTCD is the first family

Checkpoint 10 compared three BTC families under the same outcome-blind quote-feasibility philosophy.

Accepted run:

```text
collect_btc_family_quote_feasibility_20260809T114516450822Z_a232d26c
```

Observed feasibility result:

| Family | Cluster any-quote coverage | Early / middle / late | All three probes in all three bands | Status |
|---|---:|---:|---:|---|
| KXBTC15M | 100% | 100% / 100% / 100% | N/A | pass |
| KXBTC | 100% | 100% / 100% / 100% | 45% | base pass; ladder-breadth fail |
| KXBTCD | 100% | 100% / 95% / 100% | 75% | pass |

KXBTCD is selected because it passed both the frozen base quote-feasibility gate and the frozen ladder-breadth gate. Its threshold ladder also has a simple structural interpretation: higher BTC thresholds should never have a higher probability of resolving Yes than lower thresholds at the same timestamp.

This selection is a **research-design choice**, not evidence that KXBTCD is profitable or superior for trading.

## Facts established before this experiment

1. The selected modern KXBTCD settlement regime is:

```text
brti_60s_simple_mean_untrimmed
```

2. In the Checkpoint-10 structural sample, all 2,915 sampled KXBTCD markets resolved into 25 event-level settlement clusters and 25 unique settlement primitives.
3. The all-market semantic validator found no mixed settlement mechanism within those sampled events and no cross-Series shared primitive in the sampled ladder set.
4. The family-feasibility run selected 20 KXBTCD settlement clusters outcome-blind and probed three deterministic structural strikes per cluster: `q25`, `q50`, and `q75`.
5. The 20-cluster feasibility sample produced strong quote coverage without opening final market results.

## Research question

At the same real source timestamp, does using the cross-strike ordering constraint in a three-point KXBTCD threshold ladder improve proper-scoring performance relative to treating each raw midpoint independently?

The two forecast baselines are:

### Baseline A — raw midpoint

For probe market `i`:

```text
q_raw_i = (YES_bid_i + YES_ask_i) / 2
```

No external BTC price is used.

### Baseline B — monotone ladder projection

Order the three probe strikes from low to high:

```text
K_1 < K_2 < K_3
```

For threshold events of the form `BTC settlement value > K`, logical probabilities should satisfy:

```text
p_1 >= p_2 >= p_3
```

The adjusted vector is the equal-weight least-squares isotonic projection:

```text
p_mono = argmin_p sum_i (p_i - q_raw_i)^2
subject to p_1 >= p_2 >= p_3
```

The implementation uses the pool-adjacent-violators algorithm (PAVA). If the raw ladder is already monotone, the adjusted probabilities are unchanged.

## Important Brier-score caveat

For a coherent realized threshold outcome vector, the realized labels are also nonincreasing by strike. Euclidean projection onto the monotone set therefore has a structural squared-error non-worsening property.

For that reason, **Brier-score non-worsening is not the primary scientific test** of this baseline. It is reported as a structural diagnostic and implementation check.

The primary empirical scoring comparison is log loss.

## Input sample

This v1 pilot deliberately reuses the already selected outcome-blind Checkpoint-10 KXBTCD feasibility sample:

```text
20 settlement clusters
3 probe markets per cluster
60 probe markets total
```

The experiment does not expand the sample after seeing outcomes.

This is a **baseline pilot**, not a final confirmatory study. Twenty settlement clusters are too few for strong statistical claims.

## Same-time cross-section rule

The experiment does not compare three markets observed at different source times.

For each settlement cluster and each normalized time band:

1. keep only valid one-minute quote observations;
2. find `end_period_ts` values that occur in all three probe markets exactly;
3. do not forward-fill, interpolate, or use a stale quote from another minute;
4. among exact common timestamps, select the timestamp whose `normalized_time_remaining` is closest to the predeclared band center;
5. if two common timestamps are equally close, choose the earlier timestamp;
6. retain the exact selected timestamp and exact normalized time remaining in the frozen pre-outcome artifact.

Frozen band centers:

| Band | Normalized remaining range from feasibility design | Selection target |
|---|---|---:|
| early | `[2/3, 1]` | `5/6` |
| middle | `[1/3, 2/3)` | `1/2` |
| late | `[0, 1/3)` | `1/6` |

These are selection targets only. The source observation is never rewritten to pretend it occurred exactly at the target.

## Pre-outcome synchronization gate

A cluster is **primary eligible** only if all three probe markets have one exact synchronized valid cross-section in all three time bands.

The frozen minimum is the same 50% ladder-breadth threshold already used before family selection:

```text
primary eligible clusters / 20 >= 0.50
```

If fewer than 10 of the 20 KXBTCD clusters satisfy the exact synchronization rule, v1 stops **before outcomes**.

Clusters with partial synchronized coverage may remain descriptive but do not enter the primary paired evaluation.

## Development / holdout split

After the synchronization gate, and still before outcomes:

1. sort primary-eligible settlement clusters by `close_time` ascending;
2. break exact timestamp ties by `event_ticker`;
3. assign the first `floor(2N/3)` clusters to **development**;
4. assign the remaining clusters to **holdout**.

The split is chronological rather than random because BTC market behavior is time-dependent and the project should not make a random split look more independent than it is.

Primitive leakage rule:

```text
primitive_ids(development) ∩ primitive_ids(holdout) = ∅
```

Any overlap fails closed.

## Holdout discipline

The first outcome-materialization implementation may open **development outcomes only**.

Development is used to verify:

- exact raw outcome lineage;
- label parsing;
- threshold-outcome monotonicity;
- scoring implementation;
- aggregation weights;
- report generation.

If experiment logic is changed after development outcomes are viewed, this v1 holdout is considered contaminated and cannot be presented as untouched confirmation. A new version and untouched sample are required.

If development executes correctly and the design is unchanged, the holdout should be opened regardless of whether development performance looks favorable or unfavorable. This prevents selective stopping.

## Outcome source

When outcomes are eventually opened, the label source is the finalized Kalshi market result for each probe contract.

Requirements:

- public/read-only endpoint only;
- raw response written before transformation;
- exact raw request lineage on every label;
- no external BTC price feed used to manufacture or replace the label;
- no inferred settlement value used when the official market result is available.

For increasing thresholds, the realized binary outcome vector must be nonincreasing:

```text
y_1 >= y_2 >= y_3
```

A violation disables scoring for that cluster and fails the semantic validation path. It is not silently repaired.

## Weighting

The settlement cluster is the evaluation unit.

For the primary sample, every primary-eligible cluster has three selected bands and three probes per band. Aggregation therefore assigns:

```text
equal total weight per settlement cluster
equal weight per band inside a cluster
equal weight per probe inside a band
```

Each of the nine cluster-level predictions receives weight `1/9` within that cluster.

Raw candle rows are not counted as independent trials.

## Primary metric

Primary metric:

```text
cluster-weighted binary log loss
```

For numerical safety only, probabilities are clipped to:

```text
[0.000001, 0.999999]
```

The same clipping rule is applied to raw and monotone forecasts.

Primary effect size:

```text
Delta_logloss = LogLoss_raw - LogLoss_monotone
```

Interpretation:

- positive: monotone baseline scored better;
- zero: no difference;
- negative: monotone baseline scored worse.

No profitability interpretation follows from any of these cases.

## Secondary diagnostics

Report:

- cluster-weighted Brier score for raw and monotone forecasts;
- raw monotonicity-violation rate;
- mean absolute monotone adjustment;
- maximum absolute monotone adjustment;
- results separately for early, middle, and late bands;
- per-cluster paired score differences.

No p-value or statistical-significance claim is authorized for this small pilot.

## Design fingerprint

The code serializes the frozen design contract canonically and records its SHA-256 fingerprint in every pre-outcome row and freeze receipt.

Current v1 fingerprint:

```text
bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4
```

A material design change requires a new fingerprint and, after outcomes have been viewed, normally a new experiment version.

## Facts, hypotheses, and unresolved questions

### Facts

- KXBTCD passed the predeclared Checkpoint-10 quote-feasibility and ladder-breadth gates in the 20-cluster sample.
- The selected KXBTCD regime is explicitly validated as a 60-second simple BRTI average in the sampled modern rule set.
- The three probe contracts in a settlement cluster are correlated claims on one underlying BTC settlement primitive.

### Hypothesis

Cross-strike logical coherence may improve holdout log-loss performance relative to raw independent midpoints when the source ladder contains monotonicity noise.

This is not yet tested.

### Unresolved

- how often exact synchronized three-probe timestamps exist in all three bands;
- whether raw KXBTCD ladders materially violate monotonicity;
- whether monotone adjustment improves, equals, or worsens holdout log loss;
- whether results scale beyond the 20-cluster pilot;
- whether a fuller ladder or external BTC reference feature later adds predictive value;
- execution economics, fees, depth, latency, fills, and profitability.

## Safety boundary

This experiment remains research-only:

```text
authentication: no
external predictive feed: no
orders: 0
paper execution: no
real money: no
```

The pilot evaluates probabilities, not tradable PnL.

## Pre-outcome command

Before any outcome collector is implemented or run:

```powershell
.\.venv\Scripts\python.exe prepare_kxbtcd_baseline_inputs.py
```

A PASS freezes the synchronized quote inputs, development/holdout assignment, source manifest hash, artifact hashes, and design fingerprint with zero API requests and zero outcomes.

## Frozen pre-outcome result

The pre-outcome preparation command completed successfully before any result field was materialized.

Accepted freeze evidence:

```text
Experiment: kxbtcd_three_probe_monotone_baseline.v1
Design fingerprint: bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4
Source clusters: 20
Primary synchronized clusters: 12 (60%)
Development clusters: 8
Holdout clusters: 4
Selected synchronized cross-sections: 50
Pre-outcome prediction rows: 150
API requests made: 0
Outcomes materialized: no
```

The frozen 50% synchronization gate therefore passed without modification. Only the 12 all-three-band synchronized clusters are primary eligible. The remaining eight source clusters are descriptive/partial and cannot be added to the primary v1 evaluation after outcomes are viewed.

The primary v1 evaluation set contains 12 clusters split chronologically into eight development and four holdout clusters. Development scoring uses exactly 72 predictions: eight clusters x three time bands x three probes.

## Development-only materialization contract

The first outcome command is `collect_kxbtcd_development_outcomes.py`.

It is intentionally unable to request holdout outcomes through its frozen request plan. The request set is derived only from cross-section rows whose partition is `development` and must contain exactly:

```text
8 development settlement clusters
24 unique development probe contracts
0 holdout contracts
```

For each development probe contract:

1. use the route tier frozen by the source quote observation (`historical` or `live`);
2. request the public single-market endpoint;
3. persist the complete raw HTTP exchange before transformation;
4. require returned ticker and event identity to match the frozen design;
5. require `status=finalized`;
6. accept only `result=yes` or `result=no`;
7. carry exact raw source/session/request lineage into the derived outcome row.

The collector does not calculate a BTC settlement value and does not use an external BTC feed to manufacture a label.

Before scoring, each development settlement cluster must have exactly one result for each `q25`, `q50`, and `q75` probe, and those realized labels must satisfy:

```text
y_q25 >= y_q50 >= y_q75
```

A violation fails closed rather than repairing or dropping the cluster.

## Development scoring outputs

For every frozen development cross-section, the evaluator reports both raw and monotone probabilities and their paired scores. The aggregate report preserves equal settlement-cluster influence and includes:

- cluster-weighted raw and monotone log loss;
- `Delta_logloss = LogLoss_raw - LogLoss_monotone`;
- raw and monotone Brier scores as structural diagnostics;
- raw ladder monotonicity-violation rate;
- mean and maximum absolute monotone adjustment;
- early/middle/late band summaries;
- per-cluster paired score differences.

The development result is diagnostic. Eight clusters are not sufficient for a profitability, statistical-significance, or execution claim.

If this development run completes without a design/code change motivated by observed outcomes, the frozen v1 holdout must later be opened regardless of whether the development delta is favorable, neutral, or unfavorable. If experiment logic changes after development labels are viewed, v1 holdout is considered contaminated and must not be presented as untouched confirmation.

## Development-run recovery rule

The first development outcome command may preserve all 24 development market responses and then fail during downstream scoring. If that occurs, the already-exposed labels are not recollected merely to obtain a successful terminal run.

Recovery must instead:

1. bind to the exact frozen pre-outcome receipt and design fingerprint;
2. verify the failed development manifest and preserved raw-archive hashes;
3. prove that every raw request belongs to the frozen development request plan and that no holdout ticker was requested;
4. require exactly one successful finalized Kalshi response for each of the 24 development tickers;
5. reconstruct outcomes with the original raw request lineage;
6. recover strike coordinates only from the original outcome-blind BTC-family probe artifact, not from outcome-dependent information;
7. score the frozen development predictions offline with zero new API requests.

The frozen cross-section artifact may contain blank strike-metadata cells because quote-observation rows do not carry the probe schema's strike fields. This does not change q25/q50/q75 selection, synchronization, partition assignment, probabilities, or the design fingerprint. For scoring/reporting, the canonical strike anchor is rejoined from the integrity-verified source probe CSV that defined the probes before outcomes were opened.

A matching failed development-exposure run blocks the normal network collector from being rerun; the offline recovery command must be used instead. Holdout outcomes remain prohibited during this recovery.

## Development result — observed before holdout opening

The first development outcome command preserved all 24 development market responses but failed during downstream scoring because strike metadata had been joined from the quote-observation schema, where those fields are intentionally blank. No holdout market was requested. The failed run was recovered offline from the exact raw archive with zero new API requests and the strike coordinate was rejoined from the integrity-verified, outcome-blind source probe artifact.

Accepted development recovery:

```text
source failed run: collect_kxbtcd_development_outcomes_20260809T120413222263Z_9b7324be
development clusters: 8
recovered labels: 24
scored predictions: 72
API requests during recovery: 0
holdout outcomes materialized: no
```

Primary development result:

```text
Raw log loss:                 0.1229517749838280758888888889
Monotone log loss:            0.1226068974322313537500000000
Delta log loss:               0.0003448775515967221388888889
Raw Brier:                    0.03170277777777777777777777778
Monotone Brier:               0.03114913194444444444444444444
Delta Brier:                  0.00055364583333333333333333334
Raw monotonicity violations:  0.375
Mean absolute adjustment:     0.009652777777777777777777777778
Max absolute adjustment:      0.0700
```

Band diagnostics:

```text
early:  delta log loss = 0.0002239970346315987500000000; violation rate = 0.25
middle: delta log loss = 0.0002984004116432935000000000; violation rate = 0.25
late:   delta log loss = 0.00051223520851527416666666667; violation rate = 0.625
```

Interpretation is deliberately limited. The monotone baseline scored slightly better on the eight development clusters, but the effect is small and the sample is too small for an edge, profitability, or statistical-significance claim. Development results do not authorize changing the v1 model, metrics, sample, synchronization rule, or holdout gate.

## Untouched holdout execution contract

Because the design fingerprint remains:

```text
bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4
```

and no model, metric, sample, or threshold is changed in response to development scores, the four frozen holdout clusters remain the next required v1 evaluation set.

The holdout implementation is frozen before any holdout outcome is requested. It must:

1. verify the exact pre-outcome freeze receipt and completed development-recovery receipt;
2. construct exactly 12 holdout ticker requests from the four frozen holdout clusters;
3. prove that the request plan contains zero development tickers;
4. use the same raw midpoint, nonincreasing isotonic projection, clipping, log-loss, Brier, and equal-cluster weighting rules already fingerprinted in v1;
5. preserve every public Kalshi response raw-first and carry exact lineage;
6. require finalized `yes`/`no` labels and coherent nested threshold outcomes;
7. score exactly 36 holdout predictions: four clusters x three bands x three probes;
8. make no model or metric change after development;
9. provide a zero-network offline recovery path if raw holdout responses are preserved but downstream reporting fails;
10. never re-request holdout labels after a matching completed or failed holdout exposure exists.

The holdout result must be reported regardless of sign. A positive development delta is not a condition for opening or publishing holdout performance.

## Untouched holdout result — final v1 disposition

Accepted holdout run:

```text
collect_kxbtcd_holdout_outcomes_20260809T121952744398Z_ec29a2ab
```

The command opened only the four pre-frozen holdout settlement clusters / 12 holdout contracts and reused the unchanged v1 design fingerprint:

```text
bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4
```

Observed holdout scores:

```text
Holdout clusters:                  4
Holdout labels:                    12
Scored predictions:                36
Raw log loss:                      0.03832137791396992041666666668
Monotone log loss:                 0.03832137791396992041666666668
Delta log loss (raw - monotone):   0
Raw Brier:                         0.01129722222222222222222222222
Monotone Brier:                    0.01129722222222222222222222222
Delta Brier (raw - monotone):      0
Raw monotonicity violation rate:   0
Mean absolute adjustment:          0
Max absolute adjustment:           0
```

Band-level log-loss deltas were also exactly zero in early, middle, and late observations because every holdout cross-section was already monotone and the PAVA projection made no adjustment.

### Interpretation

The development set showed a very small favorable primary-metric delta (`0.000344877551596722...`) while the untouched holdout showed exactly zero incremental benefit. Therefore **v1 does not provide out-of-sample evidence that monotone post-processing improves KXBTCD forecast quality beyond raw quote midpoints**.

This is not a profitability test and not a general rejection of KXBTCD. It is a completed, small structural baseline pilot. Do not tune the three probes, synchronization rule, weighting, loss function, or isotonic algorithm against this opened holdout and then reuse the same holdout as if it were untouched.

Any follow-on experiment must receive a new design/version and a new outcome firewall before labels are used for evaluation.

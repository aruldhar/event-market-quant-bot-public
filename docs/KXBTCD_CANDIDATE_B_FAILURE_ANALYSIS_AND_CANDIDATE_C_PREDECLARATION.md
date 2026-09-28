# KXBTCD Candidate-B Failure Analysis and Candidate-C Predeclaration

Status: **Checkpoint 14 diagnostic result accepted for design; Candidate C predeclared but not fit or authorized**

## 1. Purpose

Checkpoint 13 completed the frozen Candidate-B experiment and rejected it at its predeclared validation gate. The old train and validation labels are now development/exploratory data. The 64-event locked test remains outcome-sealed.

Checkpoint 14 has two bounded goals:

1. diagnose Candidate B with simple offline error/regime slices using only the already-exposed train+validation outcomes; and
2. freeze one small future Candidate-C design before any Candidate-C fitting is allowed.

This checkpoint does **not** open locked-test outcomes, fit Candidate C, access the network for diagnostics, simulate a paper broker, or enable execution.

## 2. Frozen source experiment

Canonical Checkpoint-13 run:

`collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631`

Frozen identities:

```text
pre-outcome run = collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d
dataset fingerprint = d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a
split fingerprint = 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
Candidate-B fingerprint = e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3
```

Development scope after Checkpoint 13:

- original train: 175 events / 4,645 rows;
- original validation: 56 events / 719 rows;
- combined outcome-exposed development pool: 231 events / 5,364 rows;
- 58 distinct UTC-week units in development;
- locked test: 64 events / 1,014 pre-outcome rows;
- locked-test outcomes opened: 0.

The old 56-event validation block is no longer an untouched validation set. It is development data from this point forward.

## 3. Offline diagnostic boundary

Checkpoint 13 already wrote a row-level predictions artifact for train and validation containing the raw midpoint probability, selected Candidate-B probability, outcome, row losses, row Brier scores, event/time identifiers, and event weights.

Checkpoint 14 therefore does not request any outcome again. The analyzer:

- validates the exact canonical CP13 manifest and artifact hashes first;
- reads only canonical CP13 train/validation prediction rows;
- rejects any non-development prediction partition;
- joins only pre-outcome context for those development state IDs;
- never summarizes locked-test feature density;
- makes zero HTTP/WebSocket requests; and
- fits no model.

The analyzer also treats CP12/CP13 numeric lineage correctly: fields such as `0.72` versus `0.71999999999999997` are accepted only when they are exactly the same Python binary-float value after CP13's documented float round-trip serialization. Genuine numeric differences still fail closed.

## 4. Diagnostic dimensions

The final Checkpoint-14 diagnostic reports raw-midpoint versus Candidate-B event-weighted log loss and Brier score, plus event-level better/worse/tie counts, for:

1. the combined 231-event exposed development pool;
2. original train versus original validation;
3. five contiguous chronological UTC-week blocks;
4. the six frozen TTC anchors: 55m, 50m, 45m, 40m, 35m, and 30m;
5. frozen structural strike roles q10, q30, q50, q70, and q90;
6. fixed 0.10-wide raw-market-probability bands;
7. fixed contemporaneous spread bands;
8. `q_market` band × spread band; and
9. chronological block × spread band.

These are descriptive diagnostics only. They are not candidate-selection rules and do not rewrite Candidate B.

The current Checkpoint-12 historical states contain no external BTC-state features. Checkpoint 14 therefore does not claim to diagnose BTC direction, momentum, realized volatility, or cross-feed lead/lag. Those variables would require a separately designed source-aligned pre-outcome materialization.

## 5. Observed Candidate-B failure pattern

Canonical final diagnostic run directory:

`data/analysis/kxbtcd_candidate_b_failure_analysis/20260815T214404Z`

Canonical Windows validation immediately before the final diagnostic:

```text
Checkpoint-14 focused tests = 7 passed in 0.14s
full repository regression = 638 passed, 22 subtests passed in 17.24s
```

Safety/result boundary:

```text
network requests = 0
locked-test outcomes opened = 0
Candidate C fit performed = no
execution enabled = no
orders placed = 0
```

Combined exposed development result:

```text
raw event-weighted log loss = 0.15538587480307692
Candidate-B event-weighted log loss = 0.14462803684008735
raw - Candidate B log-loss delta = +0.010757837962989569

raw event-weighted Brier = 0.037913401220456798
Candidate-B event-weighted Brier = 0.035219333463201045
raw - Candidate B Brier delta = +0.0026940677572557525

Candidate-B better/worse/tie events = 215 / 16 / 0
```

This pooled development improvement does **not** reverse the Checkpoint-13 rejection. Candidate B failed the validation block under the gate declared before those labels were opened. The pooled development result is diagnostic only.

The failure pattern is concentrated rather than broad:

- the original validation block was worse in aggregate even though Candidate B was better on most individual events;
- chronological blocks B0-B3 were directionally favorable overall, while the latest B4 block was unfavorable overall;
- all six TTC-anchor slices were directionally favorable, so the data do not support TTC as the primary failure dimension;
- structural-role slices were directionally favorable;
- probability bands around `q_market=0.3-0.5` contained material negative pockets;
- spread effects were heterogeneous rather than uniformly positive or negative.

The two cross-tabs resolve the main ambiguity:

### Chronology × spread

In B4, the failure is concentrated in the tightest spread bucket:

```text
B4 | spread=(0,0.01]      raw-Candidate-B log-loss delta = -0.007979
B4 | spread=(0.01,0.02]   raw-Candidate-B log-loss delta = +0.011286
B4 | spread=(0.02,0.05]   raw-Candidate-B log-loss delta = +0.011765
B4 | spread=>0.05          raw-Candidate-B log-loss delta = +0.031467
```

So the late-block failure is not a generic chronological deterioration. It is strongly associated with the much larger concentration of tight-spread states in B4.

### Probability × spread

The probability failure is not explained by tight spreads alone. In the `q_market=[0.4,0.5)` band, Candidate B is materially worse at wider spreads:

```text
q=[0.4,0.5) | spread=(0.02,0.05]   delta = -0.032191
q=[0.4,0.5) | spread=>0.05          delta = -0.022122
```

But just above 0.5 the sign can reverse; for example:

```text
q=[0.5,0.6) | spread=>0.05          delta = +0.043191
q=[0.6,0.7) | spread=>0.05          delta = +0.051828
q=[0.7,0.8) | spread=>0.05          delta = +0.052443
```

This is evidence that the effect of spread depends on the market's own probability. It motivates a probability × spread interaction. It does **not** establish a profitable trading rule or guarantee that the future candidate will beat the raw midpoint.

## 6. Final Candidate-C hypothesis

The initial Checkpoint-14 draft proposed a market-logit × TTC interaction. The completed diagnostics do not support retaining that term: every TTC anchor was directionally favorable for Candidate B, while the strongest heterogeneity is jointly in market probability and spread.

The final predeclared Candidate C therefore tests a narrower hypothesis:

> The useful transformation of the raw KXBTCD midpoint depends on contemporaneous quoted spread, and the spread effect is asymmetric across the market's own probability.

Candidate C is deliberately smaller than the initial draft:

```text
model_id = kxbtcd_market_spread_interaction_logistic.v1
predeclaration contract = kxbtcd_candidate_c_predeclaration.v2
predeclaration fingerprint = d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322
```

Predeclared learned features:

```text
market_logit
    = ln(clip(q_market,0.001,0.999) / (1-clip(q_market,0.001,0.999)))

spread
    = yes_ask - yes_bid

market_logit_x_spread
    = market_logit * spread
```

The linear predictor is:

```text
z = beta0
  + beta1 * standardized(market_logit)
  + beta2 * standardized(spread)
  + beta3 * standardized(market_logit_x_spread)
```

and `p_yes = sigmoid(z)`.

The exact fit objective is:

```text
mean_over_fit_events(mean_binary_log_loss_within_event)
+ lambda/2 * (beta1^2 + beta2^2 + beta3^2)
```

The intercept is unpenalized. All three non-intercept standardized coefficients are L2-penalized.

The optimizer is frozen as deterministic damped Newton with:

- maximum 100 iterations;
- L2-gradient tolerance `1e-8`;
- Armijo constant `1e-4`;
- minimum step scale `2^-40`;
- singular Hessian => fail closed;
- non-convergence => fail closed.

Feature standardization is fit-fold-only. Each non-intercept feature uses the mean and population standard deviation computed from the current fit block(s). A zero-variance feature fails closed. Validation/future-block statistics must never be used for scaling.

## 7. Features deliberately excluded from Candidate C

Candidate C does **not** include:

- absolute strike as a learned term;
- a learned time-to-close term;
- structural-role one-hot variables;
- probability-band one-hot variables;
- spread-band one-hot variables;
- external Coinbase, Kraken, BRTI, or perpetual features;
- trend/momentum indicators;
- realized/implied-volatility indicators;
- sub-second lead/lag variables;
- future/settlement fields; or
- execution/PnL variables.

The diagnostic bins remain diagnostics only. Candidate C uses continuous pre-outcome variables rather than hard-coding post-hoc bucket boundaries into the model.

## 8. Frozen development-selection protocol

All 231 already-exposed events are development data. They are sorted by `utc_week_start` and divided into five contiguous chronological week blocks, `B0` through `B4`. Unique weeks are assigned so block week counts differ by at most one; earlier blocks receive any remainder. Weeks are never shuffled or split across blocks.

Before any Candidate-C fit, the exact week-to-block mapping must be derived from the frozen 231-event development set **without outcomes**, serialized, and SHA-256 fingerprinted. That mapping becomes part of Candidate-C fit provenance.

Candidate-C tuning uses four rolling-origin folds:

| Fold | Fit blocks | Score block |
|---|---|---|
| 1 | B0 | B1 |
| 2 | B0+B1 | B2 |
| 3 | B0+B1+B2 | B3 |
| 4 | B0+B1+B2+B3 | B4 |

Allowed L2 penalties:

```text
0.01, 0.1, 1, 10
```

There are no class weights. Each event contributes equal total weight inside every fit/score partition.

Lambda selection uses the lowest pooled out-of-fold event-weighted log loss across score blocks B1-B4. An exact tie selects the larger lambda.

## 9. Development metrics and advancement gate

Primary metric:

```text
pooled out-of-fold event-weighted log loss
```

Secondary metrics:

- pooled out-of-fold event-weighted Brier score;
- per-fold event-weighted log loss;
- per-fold event-weighted Brier score;
- fixed 0.10-wide calibration bins; and
- event-level Candidate-C versus raw better/worse/tie counts.

Candidate C may advance beyond development only if **all** are true:

1. selected Candidate-C pooled OOF log loss is strictly lower than the raw midpoint on the same OOF events;
2. selected Candidate-C pooled OOF Brier score is less than or equal to the raw midpoint; and
3. Candidate C has strictly lower log loss than the raw midpoint in at least 3 of the 4 rolling score blocks.

A tie on the primary metric fails. Secondary metrics cannot override a primary failure.

Checkpoint 14 does not run this gate because Candidate C is not fit in Checkpoint 14. These rolling-origin scores are an internal development-selection mechanism, not a new untouched test.

## 10. Future role of the 64-event locked test

The 64-event locked test remains the only outcome-sealed terminal block.

It may be opened only in a later explicit checkpoint after:

1. the Candidate-C specification and fingerprint are frozen;
2. the exact week-block map is frozen without outcomes;
3. the rolling-origin development evaluation is complete;
4. the development advancement gate passes;
5. selected lambda and full-development scaling rules are frozen; and
6. the final development fit is frozen.

The locked test is then a **one-time terminal evaluation**. Its primary rule is:

```text
Candidate-C locked-test event-weighted log loss
<
raw-midpoint locked-test event-weighted log loss
```

A tie fails. Once opened, those 64 events become exposed and cannot be reused as an untouched test for later candidates. No post-open redesign on the same test is permitted.

## 11. Checkpoint-14 authorization boundary

Checkpoint 14 permits only offline failure diagnostics on the existing exposed development outcomes and freezing this future-candidate research contract.

Checkpoint 14 does **not** authorize:

- Candidate-C fitting;
- locked-test outcome access;
- new outcome requests;
- paper execution or a paper broker;
- demo execution;
- real-money execution;
- order placement/cancellation; or
- transfers.

All existing credential and read-only rules remain unchanged.

## 12. Next checkpoint boundary

A later checkpoint may implement **Candidate-C development evaluation only** under the exact v2 predeclaration above.

Before that fit begins, it must first freeze and fingerprint the deterministic week-to-block mapping. Candidate C must then be evaluated only under the predeclared rolling-origin folds, lambda grid, metrics, and advancement gate.

The locked test stays sealed unless and until Candidate C passes the development gate and a separate later checkpoint explicitly authorizes the one-time terminal evaluation.

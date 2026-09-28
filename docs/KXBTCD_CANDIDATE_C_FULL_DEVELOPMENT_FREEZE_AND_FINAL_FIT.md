# KXBTCD Candidate-C Full-Development Freeze and Final Fit

Status: **Checkpoint 16 completed — full-development preprocessing and final Candidate-C model frozen; locked test remains sealed**

## Purpose

Checkpoint 16 performed only the already authorized transition from the passed Candidate-C development gate to a fully frozen final development model. It did not open, inspect, score, summarize, or otherwise use the 64-event locked-test outcomes.

Frozen identity:

```text
candidate = kxbtcd_market_spread_interaction_logistic.v1
predeclaration fingerprint = d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322
week-map fingerprint = 6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4
selected lambda = 0.01
development = 231 already outcome-exposed events / 5,364 rows
```

Candidate B remains rejected under D-014. Its later pooled development result does not reverse its original Checkpoint-13 validation failure.

## Canonical Windows validation before final fit

Repository baseline:

```text
HEAD = a2c0b5ddbf90f432acbc9e345f99fd224cc00885
origin/main = a2c0b5ddbf90f432acbc9e345f99fd224cc00885
```

Validation:

```text
focused Checkpoint-16 tests = 15 passed in 0.73s
full repository regression = 653 passed, 22 subtests passed in 19.49s
source registry = PASS
Sources = 18
Validated sources = 12
Unresolved settlement sources = 1
```

No unexpected pre-existing worktree paths were present before the Checkpoint-16 replacement files.

## Stage 1 — full-development preprocessing freeze

The scaler was computed before the final fit from all and only the 5,364 already outcome-exposed development rows.

Feature order:

```text
market_logit
spread
market_logit_x_spread
```

Feature definitions:

```text
market_logit = ln(clip(q_market,0.001,0.999)/(1-clip(q_market,0.001,0.999)))
spread = yes_ask - yes_bid
market_logit_x_spread = market_logit * spread
```

Preprocessing uses ordinary unweighted row-level means and population standard deviations (`ddof=0`). Event weighting is not applied to scaling; equal event weighting remains an objective/metric rule.

Frozen means:

```text
market_logit = 0.053181741488340019
spread = 0.17633482475764356
market_logit_x_spread = 0.006538779033484236
```

Frozen population standard deviations:

```text
market_logit = 3.2168919026338747
spread = 0.21442166056343254
market_logit_x_spread = 0.32259958139407791
```

Tracked freeze artifact:

`configs/kxbtcd_candidate_c_full_development_freeze.json`

Fingerprint:

`d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`

At freeze time:

```text
final fit performed = no
locked-test outcomes opened = 0
locked-test evaluation = no
network requests = 0
execution enabled = no
orders placed = 0
```

## Stage 2 — one-time final development fit

After the preprocessing freeze was serialized and fingerprinted, the final-fit command revalidated the freeze and wrote a one-time local attempt receipt before invoking the optimizer.

The fit used exactly:

```text
features = market_logit, spread, market_logit_x_spread
lambda = 0.01
fit scope = B0+B1+B2+B3+B4
development events = 231
development rows = 5,364
objective = equal total event weight + frozen L2 penalty
optimizer = deterministic damped Newton
```

No new feature search, lambda search, alternate preprocessing, optimizer change, external BTC feature addition, or post-result tuning was performed.

The fit converged in 6 Newton iterations.

Penalized full-development training objective:

`0.1226739682345051`

This value is the final penalized training objective on the exposed development pool. It is not an untouched validation/test score and must not be compared as though it were a new out-of-sample metric.

## Frozen final model

Tracked inference artifact:

`configs/kxbtcd_candidate_c_final_model.json`

Final model fingerprint:

`13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`

Coefficient order:

```text
intercept
market_logit_z
spread_z
market_logit_x_spread_z
```

Coefficients:

```text
0.10194908608881083
2.0752015786995628
0.017616475889079299
1.9669079012140323
```

Inference is frozen as:

```text
z_market_logit = (market_logit - 0.053181741488340019) / 3.2168919026338747
z_spread = (spread - 0.17633482475764356) / 0.21442166056343254
z_market_logit_x_spread = (market_logit_x_spread - 0.006538779033484236) / 0.32259958139407791

linear_predictor =
    0.10194908608881083
    + 2.0752015786995628 * z_market_logit
    + 0.017616475889079299 * z_spread
    + 1.9669079012140323 * z_market_logit_x_spread

p_yes = sigmoid(linear_predictor)
```

Because the model includes an interaction and standardized features, individual coefficient magnitudes should not be interpreted as isolated causal effects.

## One-time fit receipt

Local receipt:

`data/analysis/kxbtcd_candidate_c_final_fit/final_fit_attempt.json`

Canonical result:

```text
status = fit_completed
started_at_utc = 2026-08-15T22:24:14.130390Z
completed_at_utc = 2026-08-15T22:24:14.346515Z
selected lambda = 0.01
freeze fingerprint = d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3
final model fingerprint = 13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f
```

The final artifact validator passed without invoking another model fit.

## Safety boundary

Checkpoint 16 closed with:

```text
locked-test outcomes opened = 0
locked-test evaluation performed = no
network requests = 0
execution enabled = no
orders placed = 0
paper execution = no
demo execution = no
real-money execution = no
```

No locked-test feature-density analysis was used to redesign or tune Candidate C.

## Interpretation

Checkpoint 16 establishes a reproducible, frozen final Candidate-C model for later inference. It does not add new evidence that Candidate C generalizes beyond the Checkpoint-15 rolling-origin development results because all 231 rows used here are development data.

The only remaining untouched terminal evaluation block is the 64-event locked test.

## Next checkpoint boundary

A separate Checkpoint 17 may explicitly authorize the **one-time terminal locked-test evaluation**.

Checkpoint 17 must:

1. load only the already frozen final-model artifact and preprocessing state;
2. make no feature, lambda, preprocessing, optimizer, or calibration changes;
3. open the 64 locked-test outcomes only once;
4. score Candidate C and the raw midpoint on the same locked-test events;
5. apply the already frozen terminal primary rule:
   `Candidate-C locked-test event-weighted log loss < raw-midpoint locked-test event-weighted log loss`;
6. treat a tie as failure;
7. record that the locked test becomes permanently exposed after opening; and
8. prohibit redesign or another untouched-test claim on those 64 events.

Execution remains out of scope.

# KXBTCD Candidate-E Conditional-Alpha Reliability v1 Exact Predeclaration

## Checkpoint 21N-I

Status: **PREDECLARATION ONLY — NOT FIT AUTHORIZED**.

This checkpoint freezes the smallest defensible learned reliability baseline before any conditional-alpha fit or outcome scoring.

Parent architecture fingerprint:

`bb7ebb7b12a9b817465e9e522d65b2f5a129f9e5aaa12a1c8ac6e5fd666a6742`

Parent Strategy-v2 result closeout fingerprint:

`02b8aab23161419abd1cdf02c79072f070067ed28f16ef186959e6fc5b3f5ee4`

Frozen Candidate-E Champion-Final fingerprint:

`b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`

## Research question

The model asks one narrow question:

> Given the causal market/BTC state at this decision point, how much of Candidate E's disagreement with Kalshi should be trusted?

The answer is a state-specific reliability weight `alpha_i`.

`alpha_i = sigmoid(gamma_0 + gamma^T X_i)`

`p_adj_i = q_i + alpha_i * (pE_i - q_i)`

`q_i` is the contemporaneous Kalshi YES midpoint and `pE_i` is the frozen Candidate-E probability representation used for that historical score stage.

Because `0 < alpha_i < 1`, `p_adj_i` must remain between Kalshi and Candidate E. The model cannot extrapolate beyond both endpoints.

## Important historical-lineage rule

Champion-Final was ultimately fitted using exposed H1/H2/H3/C1/C2/C3 evidence. Therefore Champion-Final must **not** be regenerated retroactively on those same historical outcomes and used as though it were out-of-sample.

Historical reliability supervision must use only the already-frozen OOF/OOS Candidate-E predictions from the same Candidate-E specification that were available before each score stage.

Development prediction SHA-256s:

- H1_OOF: `867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16`
- H2: `4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6`
- H3: `091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380`

Later fixed prediction sources, if separately authorized:

- C1: `a15dda96dfdf0255eef627867807f25a9576c0a0d019b32a46ef3e4d6a79e82f`
- C2: `598894d19d6fb4e141f71cdb05e53738f83b0b19e905701ca9398d07a0d093b7`
- C3: `cce62dbd9fa1bec99494721c9bf583a397dcfb8d1c8777028700914473652e50`

Champion-Final remains the frozen future prospective/live read-only Candidate-E model. This historical cross-fitting rule is an anti-leakage requirement, not a Candidate-E refit.

## Exact v1 feature vector

The reliability model has exactly four continuous causal features.

### 1. Absolute Candidate-E versus market disagreement

`abs_candidate_market_disagreement = abs(pE_yes - q_yes)`

where:

`q_yes = (yes_bid + yes_ask) / 2`

Only magnitude is used. Signed disagreement and side indicators are excluded so exposed YES/NO diagnostics cannot become a disguised hard rule.

### 2. Contemporaneous spread

`spread_t = yes_ask - yes_bid`

The quote must be valid, two-sided, uncrossed, causal, and the exact contemporaneous state associated with the Candidate-E decision row.

### 3. Absolute five-minute BTC return

`abs_r_5m = abs(r_5m)`

where the already-frozen causal Candidate-E return is:

`r_5m = 10000 * ln(S_t / S_t_minus_300s)`

The absolute value measures movement magnitude without introducing a directional BTC rule.

### 4. Continuous time to close

`ttc_minutes = float(ttc_target_minutes)`

Allowed values remain exactly:

`55, 50, 45, 40, 35, 30`

TTC is one continuous predictor. v1 does not learn six independent TTC alphas or TTC dummy coefficients.

## Explicit feature exclusions

v1 does not use:

- signed Candidate-E minus market disagreement;
- separate YES/NO reliability models or side indicators;
- structural-role indicators;
- recent Kalshi midpoint movement/range features;
- recent public trade/activity features;
- open interest or taker imbalance;
- calendar/block identity;
- hardcoded T-55 or other TTC buckets;
- direct `q_yes` as an additional learned predictor;
- direct `pE_yes` as an additional learned predictor;
- future quotes/BTC state;
- settlement outcome as a feature;
- realized P&L, fills, latency, depth, queue, or execution information.

Those exclusions prevent the first baseline from recreating the broad failed Model2 feature search or post-hoc Strategy-v2 diagnostics.

## Scaling

All four features are z-scored using only the current fit partition.

For `E` fit events and `n_e` eligible states in event `e`:

`w_i = 1 / (E * n_e)`

Every event therefore has equal total weight.

For feature `j`:

`mu_j = sum_i w_i * x_ij`

`var_j = sum_i w_i * (x_ij - mu_j)^2`

`z_ij = (x_ij - mu_j) / sigma_j`

The weighted population variance is used. Score-partition statistics cannot influence the scaler.

A non-finite statistic or standard deviation `<= 1e-12` fails closed.

No clipping, winsorization, ranking, imputation, feature selection, or interaction search is permitted.

## Alpha parameterization

The exact model is:

`eta_i = gamma_0 + gamma_disagreement*z_disagreement_i + gamma_spread*z_spread_i + gamma_abs_r5m*z_abs_r5m_i + gamma_ttc*z_ttc_i`

`alpha_i = sigmoid(eta_i)`

There are exactly five learned parameters:

1. `gamma_0`
2. `gamma_disagreement`
3. `gamma_spread`
4. `gamma_abs_r5m`
5. `gamma_ttc`

All five start at zero. Therefore the starting model is exactly:

`alpha_i = 0.50`

for every state.

Training is free to move the intercept and slopes, so the final model may produce a different alpha for every state. The `.50` value is the deterministic nested starting/reference model, not a constraint on the learned average alpha.

The same alpha model is used symmetrically for YES and NO:

`p_adj_no = 1 - p_adj_yes`

No alpha clipping is permitted. If floating-point evaluation does not satisfy strict `0 < alpha < 1`, evaluation fails closed.

## Training objective

The target is the binary KXBTCD settlement outcome, not realized trade P&L.

For each fit partition:

`L(gamma) = sum_i w_i * binary_log_loss(y_i, p_adj_i) + (lambda/2) * sum_j gamma_j^2`

All five gamma parameters, including the intercept, are L2-regularized.

This choice is intentional: stronger regularization pulls the model back toward all-zero gamma, which is global alpha `0.50`.

No class weighting, random sampling, shuffling, or profit weighting is allowed.

## Frozen lambda grid

The exact grid is:

- `0.001`
- `0.01`
- `0.1`
- `1.0`
- `10.0`

No lambda zero and no additional values are candidates.

## Frozen optimizer

Implementation must use deterministic full-batch BFGS with:

- initial gamma: all zeros;
- initial inverse-Hessian approximation: 5x5 identity;
- maximum iterations: 500;
- gradient L2 tolerance: `1e-8`;
- Armijo backtracking line search;
- Armijo constant: `1e-4`;
- initial step scale: `1.0`;
- rejected-step multiplier: `0.5`;
- minimum step scale: `2^-40`;
- standard BFGS inverse-Hessian update;
- required curvature `y^T s > 1e-12`;
- no warm starts between lambdas;
- non-descent direction, line-search failure, non-finite state, or non-convergence: fail closed;
- no new numerical/ML dependency.

No optimizer change is permitted after outcome results are seen.

## Rolling-origin development procedure

Development remains exactly:

- H1_OOF: 1,070 events / 31,656 rows
- H2: 750 / 22,354
- H3: 750 / 22,409
- total: 2,570 events / 76,419 rows

The development row universe must match the already-frozen Model2 causal state universe exactly:

- feature-row SHA-256: `0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c`
- preparation fingerprint: `2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`

No outcome-dependent row addition/deletion is allowed.

### Fold 1

Fit: H1_OOF

Score: H2

### Fold 2

Fit: H1_OOF + H2

Score: H3

For each lambda, pool the 1,500 H2+H3 score events and compute event-equal log loss.

Select the lambda with minimum pooled H2+H3 event-equal log loss.

Exact numerical tie: choose the larger lambda.

No secondary metric may override lambda selection.

## Fixed probability benchmarks

Exactly three benchmarks are required on identical rows:

1. Kalshi midpoint: `alpha=0`, `p=q`.
2. Global alpha `.50`: `p50=q+0.50*(pE-q)`.
3. Candidate E: `alpha=1`, `p=pE`.

No `.25`, `.75`, intermediate global-alpha search, or fitted intercept-only global-alpha search is allowed.

Global alpha `.50` is the primary complexity benchmark because zero gamma nests it exactly.

## Development probability advancement gate

Every condition must pass:

1. pooled H2+H3 conditional-alpha event-equal log loss is strictly lower than Kalshi;
2. strictly lower than Candidate E;
3. strictly lower than global alpha `.50`;
4. pooled H2+H3 Brier is no worse than all three benchmarks;
5. conditional alpha strictly beats `.50` log loss separately in H2;
6. conditional alpha strictly beats `.50` log loss separately in H3;
7. median event-level `.50 minus conditional` log-loss delta is strictly positive;
8. every fit converges and all values are finite;
9. every alpha is strictly inside `(0,1)` and every adjusted probability is between q and pE;
10. no lineage, timing, causal-feature, evidence-firewall, or contamination violation occurs.

A primary tie fails.

## Development economic evaluation: anti-leakage rule

A learned model may **not** be refit on all H1/H2/H3 and then judged economically on those same fitted events.

Therefore development economics use only the selected-lambda rolling-origin score predictions:

- Fold-1 predictions on H2;
- Fold-2 predictions on H3.

This creates a 1,500-event out-of-fold economic score set.

Sort those events by `event_close_time_utc`, then `event_ticker`, and split into exactly five contiguous 300-event blocks B0-B4.

This differs from Strategy-v2's old 5x514 block layout because Strategy-v2 had no learned reliability fit. Reusing the old full-development blocks for a learned conditional model would create in-sample economic evaluation.

## Frozen downstream quoted-entry policy

For each out-of-fold conditional-alpha state:

- anchor order: 55, 50, 45, 40, 35, 30 minutes;
- roles remain q10/q30/q50/q70/q90 for the opportunity search, but role is not a reliability-model feature;
- YES purchase price = `yes_ask`;
- NO purchase price = `1 - yes_bid`;
- YES probability = `p_adj_yes`;
- NO probability = `1 - p_adj_yes`;
- standard entry fee = `ceil_cent(0.07 * P * (1-P))`;
- adjusted net edge = probability - purchase price - fee;
- qualify iff adjusted net edge `>= 0`;
- first qualifying anchor only;
- within that anchor choose largest adjusted net edge;
- exact tie: market ticker ascending, then YES before NO;
- one whole contract maximum per event;
- otherwise ABSTAIN;
- no re-entry, adding, averaging, side switching, sizing optimization, stops, targets, or early exit;
- research accounting holds the selected side to settlement.

This remains historical quoted-entry screening, not a fill claim or paper broker.

## Development economic advancement gate

Every condition must pass:

- at least 100 entries across H2+H3;
- at least 20 entries in H2;
- at least 20 entries in H3;
- base pooled mean net P&L/event including abstentions as zero > 0;
- +1c stressed pooled mean net P&L/event > 0;
- base mean P&L/event > 0 in at least 4/5 chronological 300-event blocks;
- newest B4 base mean P&L/event > 0;
- H3 base mean P&L/event > 0.

Global alpha `.50` Strategy-v2 economics remain frozen 21N-H context only. The conditional-alpha checkpoint does not reopen the closed global-alpha family as another economic alpha search.

Stress policy:

- base: +0c;
- advancement stress: +1c;
- +2c/+3c diagnostics only;
- recalculate fee at stressed price;
- stressed price outside [0,1] invalidates the whole scenario rather than being capped or omitted.

## Evidence roles

### H1_OOF / H2 / H3

Fully exposed development evidence only.

### C1 + C2

C1+C2 outcomes were already opened for Model2 and are not globally fresh.

They are **not authorized in 21N-I**.

If and only if the complete H-development probability and economic gates pass, a later checkpoint may:

1. fit the selected lambda once on all H1_OOF+H2+H3;
2. freeze that model/scaler and implementation;
3. evaluate it once on C1+C2 with no retuning.

C1+C2 then serve only as non-fresh confirmation/falsification. Failure rejects v1; no repair is allowed.

The future C1+C2 probability confirmation gate is already frozen here:

- pooled log loss < Kalshi, Candidate E, and alpha `.50`;
- pooled Brier <= all three;
- conditional log loss < alpha `.50` separately in C1 and C2;
- median event-level `.50 minus conditional` log-loss delta > 0;
- all numerical and lineage invariants pass.

The future C1+C2 economic confirmation gate is:

- same quoted-entry policy;
- at least 20 entries total;
- base pooled mean P&L/event > 0;
- +1c pooled mean P&L/event > 0;
- base mean P&L/event > 0 in at least 4/5 contiguous 200-event blocks;
- newest block > 0.

### C3

C3 is globally exposed to the prior Candidate-E lifecycle, but remains locked against conditional-alpha development.

It is not authorized in 21N-I and may not influence features, preprocessing, lambda, optimizer, gates, or C1+C2 decisions.

Only after C1+C2 confirmation PASS may a later checkpoint explicitly authorize a one-time conditional-alpha-specific C3 holdout.

The future C3 probability gate is already frozen:

- log loss < Kalshi, Candidate E, and alpha `.50`;
- Brier <= all three;
- median event-level `.50 minus conditional` log-loss delta > 0;
- all numerical and lineage invariants pass.

The future C3 economic gate is:

- same quoted-entry policy;
- at least 20 entries;
- base mean P&L/event > 0;
- +1c mean P&L/event > 0;
- base mean P&L/event > 0 in at least 4/5 contiguous 100-event blocks;
- newest block > 0.

C3 failure rejects v1 with no repair.

### Protected historical reserve

Remains sealed.

It does not open automatically even if C3 later passes. Any reserve use requires a separate predeclaration and explicit authorization.

## Failure and contamination protections

v1 closes without subgroup rescue if a required probability/economic gate fails.

Do not:

- refit Candidate E;
- generate Champion-Final in-sample historical supervisory predictions;
- add/remove/transform features after results;
- add signed disagreement, side, TTC buckets, structural role, activity features, or block rules as repair;
- search alpha .25/.75/intermediate global alphas;
- train on P&L;
- use quote/fee/fill economics as the probability target;
- use future data or execution information;
- impute missing required causal state;
- retune lambda, optimizer, model, or gates on C1+C2/C3;
- rescue failure with a post-hoc subgroup.

## Safety

Checkpoint 21N-I performs no model fit and no outcome scoring.

It opens no new outcomes, accesses no C1/C2/C3 conditional-alpha evidence, accesses no protected reserve, uses no network, submits no orders, and performs no paper/demo/real execution.

The next checkpoint may implement and independently validate the frozen mechanics and outcome-blind row materialization only. Fitting remains prohibited until that implementation is safely closed.

## Predeclaration fingerprint

`742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`

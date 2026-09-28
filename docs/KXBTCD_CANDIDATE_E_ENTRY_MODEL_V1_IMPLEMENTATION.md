# Candidate-E Entry Model v1 — Checkpoint 21M Implementation Preparation

## Status

Checkpoint 21M implements the deterministic machinery frozen by Checkpoint 21L. This document is an implementation record, not a new model design and not a Model-2 performance result.

At bundle preparation time, the canonical GitHub `main` closeout state was:

- current `main` / receipt commit: `cf3c2613a2a06350cf3ef7fa67ff11214e1bf72d`
- Checkpoint-21L content commit: `b65e03ceaab2c5c404bf363ad28ba180f5eb16d9`
- receipt checkpoint ID: `checkpoint_21l`
- prior canonical regression evidence recorded by the receipt: 906 passed + 22 subtests

### Bookkeeping clarification

Commit `b65e03ceaab2c5c404bf363ad28ba180f5eb16d9` was accidentally given the message:

`Checkpoint 21M — Candidate-E Entry Model v1 Implementation and Development Evaluation Preparation`

Its contents are the completed Checkpoint-21L predeclaration closeout. This is a naming-only metadata mistake. Git history must not be rewritten. Receipt commit `cf3c2613a2a06350cf3ef7fa67ff11214e1bf72d` remains the canonical closeout receipt for Checkpoint 21L.

## Frozen scientific contract preserved

This implementation does not redesign D-021L-01 through D-021L-06.

Model 2 remains exactly:

`kxbtcd_candidate_e_entry_residual_logistic.v1`

with:

`logit(p2) = logit(p_candidate_e) + beta' x`

where the Candidate-E logit has fixed coefficient 1 and the learned residual contains exactly 21 L2-penalized coefficients:

- 1 residual intercept
- 11 continuous features
- 5 TTC indicators with T-55 as the reference
- 4 structural-role indicators with q50 as the reference

All 21 learned residual coefficients, including the intercept, are penalized.

The frozen lambda grid remains:

`0.001, 0.01, 0.1, 1, 10`

The development tuning chronology remains:

1. fit H1_OOF, score H2
2. fit H1_OOF + H2, score H3
3. select lambda by pooled H2 + H3 event-equal log loss
4. exact numerical tie selects the larger lambda
5. only after the preparation freeze is accepted may one selected-lambda development fit use H1_OOF + H2 + H3

C1/C2 are not development-fitting evidence. C3 is not opened for Checkpoint-21M Model-2 evaluation. The protected 4,676-event reserve remains denied.

## 21M-A timestamp-alignment clarification discovered before fitting

The first real development materialization attempt failed on state `KXBTCD-25APR2823|KXBTCD-25APR2823-T93999.99|TTC30|q50` because the initial 21M implementation incorrectly required an archive candle ending at the scheduled decision minute. The frozen Candidate-E row instead carries `decision_target_utc=2025-04-29T02:30:00Z`, `kalshi_quote_end_period_ts=1745893740` (02:29:00Z), and `kalshi_quote_staleness_seconds=60`. The execution archive contains that exact 02:29 candle.

This is consistent with the pre-existing Candidate-E historical materialization contract: quote selection used the latest valid real two-sided quote with `end_period_ts <= scheduled target` and no more than 60 seconds of staleness, while the decision time remains the scheduled TTC target. Therefore 21M reconstructs the exact already-frozen Candidate-E quote timestamp. It does not broaden eligibility, search for a nearest quote, or use a future candle.

The Checkpoint-21L prose saying the quote candle ends "at the decision timestamp" is treated as imprecise shorthand for the exact frozen Candidate-E contemporaneous quote state. This clarification was made outcome-blind, before any Model-2 label attachment, fitting, P&L, C3 evaluation, or protected-reserve access.

## Implementation architecture

Checkpoint 21M deliberately separates data preparation from outcome attachment and fitting.

### Stage A — outcome-blind materialization and freeze

`src/kxbtcd_candidate_e_entry_model_v1_materialization.py` joins only the already-exposed development state identities/probabilities with the reusable read-only execution archive.

Inputs:

- Candidate-E historical pre-outcome rows
- Candidate-E H1 OOF prediction rows
- Candidate-E H2 prediction rows
- Candidate-E H3 prediction rows
- reusable execution-archive allow-list
- one-minute quote candles
- public trades

Only H1_OOF, H2, and H3 identities are indexed for development materialization. Validation-stage identities are skipped rather than indexed for development use. Any unrecognized/protected stage fails closed.

Prediction inputs are projected onto identity plus Candidate-E probability before feature construction. A prediction-file `outcome` field cannot affect feature values, row eligibility, chronology, or feature fingerprints.

Outputs:

- `candidate_e_entry_model_v1_development_features.csv`
- `candidate_e_entry_model_v1_development_event_map.csv`
- `candidate_e_entry_model_v1_preparation_freeze.json`

The feature CSV contains no outcome column.

The preparation freeze binds:

- source-file SHA-256 values
- implementation-file SHA-256 values
- persisted feature-CSV SHA-256
- persisted event-map CSV SHA-256
- type-stable row fingerprints
- deterministic event-map fingerprint
- explicit safety flags

This allows the prepared feature universe to be accepted before any real Model-2 development fit is performed.

### Stage B — label attachment and rolling-origin evaluator machinery

`src/kxbtcd_candidate_e_entry_model_v1.py` contains a separate `attach_development_labels` function. It requires an exact `state_id` match to the already-frozen feature universe. Outcomes therefore cannot decide which states exist or how their features are computed.

The same module implements the frozen development evaluator, but Checkpoint 21M preparation does not invoke it on real project outcomes. Synthetic fixtures exercise the machinery only.

## Exact frozen continuous features

The 11 continuous predictors are:

1. `r_5m`
2. `spread_t`
3. `mid_move_1m`
4. `spread_change_1m`
5. `bid_range_1m`
6. `ask_range_1m`
7. `log1p_volume_1m`
8. `log1p_open_interest`
9. `log1p_trade_count_5m`
10. `log1p_contracts_5m`
11. `taker_imbalance_5m`

For the exact one-minute quote candle identified by the already-frozen Candidate-E `kalshi_quote_end_period_ts`:

`spread_t = yes_ask_t - yes_bid_t`

`mid_move_1m = ((bid_close + ask_close) - (bid_open + ask_open)) / 2`

`spread_change_1m = (ask_close - bid_close) - (ask_open - bid_open)`

`bid_range_1m = bid_high - bid_low`

`ask_range_1m = ask_high - ask_low`

`log1p_volume_1m = log(1 + volume)`

`log1p_open_interest = log(1 + open_interest)`

Timestamp reconstruction follows Candidate E's frozen historical quote-selection semantics rather than inventing a new state. The scheduled `decision_target_utc` remains the decision time, while the selected Kalshi quote may end at that minute or up to 60 seconds earlier. The materializer therefore requires all of the following:

- `kalshi_quote_end_period_ts <= decision_target_utc`;
- `decision_target_utc - kalshi_quote_end_period_ts == kalshi_quote_staleness_seconds`;
- staleness is in `[0, 60]` seconds;
- the archive contains the exact candle at `kalshi_quote_end_period_ts`;
- that candle's close matches the frozen Candidate-E YES bid/ask.

There is no nearest-candle substitution, later-candle substitution, forward fill, interpolation, or synthetic quote repair. A missing exact frozen quote candle fails closed.

For public trades, the causal window is exactly:

`decision_time - 300 seconds < trade_time <= decision_time`

Then:

`log1p_trade_count_5m = log(1 + trade_count)`

`log1p_contracts_5m = log(1 + sum(count_fp))`

`taker_imbalance_5m = (YES_taker_contracts - NO_taker_contracts) / (YES_taker_contracts + NO_taker_contracts)`

with imbalance defined as 0 when the denominator is 0. A zero-trade window is a valid observed zero, not missing data.

## Preprocessing and event weighting

Continuous features use fit-partition-only event-equal weighted population z-scaling.

If event `e` has `n_e` rows and a fit partition contains `E` events, each row receives weight:

`w_ei = 1 / (E * n_e)`

so each event contributes total mass `1 / E` regardless of how many rows it contains.

For each continuous feature:

`mu = sum(w_i * x_i)`

`sigma = sqrt(sum(w_i * (x_i - mu)^2))`

Scoring partitions never influence their fit partition's `mu` or `sigma`. Non-finite values or `sigma <= 1e-12` fail closed. There is no imputation, clipping, winsorization, or unpredeclared transform.

## Deterministic optimization

The residual-logistic objective is event-equal weighted binary log loss plus L2 penalty on all 21 learned residual coefficients.

The solver:

- initializes every residual coefficient at zero, which is exactly the unchanged Candidate-E baseline
- uses dense deterministic Cholesky Newton solves
- uses Armijo backtracking with `c = 1e-4`
- starts line-search scale at 1 and halves rejected scales
- rejects scales below `2^-40`
- stops when gradient L2 norm is `<= 1e-8`
- permits at most 100 Newton iterations
- fails closed on non-finite arithmetic, invalid Cholesky factorization, failed line search, or non-convergence

No stochastic optimizer or random seed is involved.

## Development-evaluation machinery

The implemented evaluator reproduces the frozen two-fold rolling-origin procedure:

- Fold 1: H1_OOF fit -> H2 score
- Fold 2: H1_OOF + H2 fit -> H3 score

For every frozen lambda it pools the scored H2/H3 events and computes event-equal log loss and Brier score. Lambda selection uses log loss only; exact ties select the larger lambda.

The evaluator also supports the frozen full-development refit after lambda selection, but Checkpoint 21M does not run that refit on real project data until the outcome-blind preparation artifacts are independently validated and accepted.

## Fail-closed conditions

Materialization fails closed for, among other conditions:

- missing/duplicate Candidate-E state identity
- wrong prediction schema or candidate ID set
- changed frozen stage row/event counts
- missing pre-outcome source state
- stage/event/market identity mismatch
- missing exact decision candle
- duplicate candle key
- invalid quote ordering
- inconsistent candle OHLC range
- duplicate public-trade identity
- non-YES/NO taker outcome side
- non-finite or negative activity values where prohibited
- invalid TTC/structural role
- non-interior Candidate-E probability
- non-strict development-stage chronology
- output schema mismatch
- source/output/code hash mismatch in validation
- any safety-flag change

The optimizer separately fails closed on numerical violations described above.

## Isolated implementation validation

Before packaging, the implementation was exercised only on synthetic fixtures in an isolated container:

- Python 3.13.5
- pytest 9.0.2
- result: 25 passed
- Python byte-compilation: PASS

The tests cover:

- event-equal row/event weights
- event-equal scaling
- exact 21-parameter reference coding
- known positive-definite Cholesky solve
- deterministic optimizer output
- Candidate-E no-clipping rule
- exact post-freeze label attachment
- whole-event chronology
- exact larger-lambda tie rule
- deterministic rolling-origin evaluator on synthetic data
- L2 shrinkage of the full residual vector including intercept
- exact candle feature formulas
- strict five-minute trade-window endpoints
- outcome-firewall invariance
- missing exact-candle fail-closed behavior
- duplicate-trade rejection
- selected trade stage/event identity enforcement
- exact decision-minute boundary enforcement
- protected/unrecognized stage rejection
- H1 rejected-momentum row exclusion
- CSV round-trip-stable scientific fingerprints
- prepared-output byte-hash binding
- independent persisted-artifact rederivation
- independent source-to-feature rematerialization with bound source/code hashes
- prepared-output tamper rejection

These are implementation tests only. They are not evidence that Model 2 improves forecasting, has positive EV, or is profitable.

## Safety status

Checkpoint 21M preparation remains read-only.

- Strategy-v1 P&L calculated: no
- real Model-2 development fit performed by this preparation bundle: no
- C3 opened for Model-2 evaluation: no
- protected 4,676-event reserve accessed: no
- paper execution added: no
- demo execution added: no
- real execution added: no
- `docs/RISK_POLICY.md` changed: no

## Canonical acceptance still required

The 25-test result above is isolated pre-integration evidence. It does not replace validation in the user's canonical Windows Python 3.11 repository.

The next acceptance slice is:

1. apply this bundle to canonical `main` at receipt `cf3c2613a2a06350cf3ef7fa67ff11214e1bf72d`;
2. apply the deterministic documentation update;
3. run the focused 21M tests in the canonical environment;
4. run the full repository regression suite;
5. only after those pass, materialize the real H1_OOF/H2/H3 outcome-blind feature universe and independently validate its preparation freeze;
6. do not attach development outcomes or fit Model 2 until that preparation freeze is accepted.
<!-- CHECKPOINT21M_REAL_PREPARATION_ACCEPTED_20260819 -->
## Real preparation acceptance

The canonical Windows implementation and real outcome-blind preparation are now
accepted for the development stage.

Post-correction tests:
- 29 focused tests passed in 1.27 seconds
- 935 repository tests + 22 subtests passed in 30.75 seconds

The real development freeze contains 76,419 rows across 2,570 events and is bound
by preparation fingerprint
`2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`.
An independent validator rematerialized the features from the seven frozen sources
and returned PASS, including implementation-hash verification.

This supersedes the earlier "Canonical acceptance still required" status for the
preparation slice only. It does not close Checkpoint 21M and does not constitute a
Model-2 performance result. The next permitted step is exact-state attachment of
already-exposed H1_OOF/H2/H3 outcomes followed by the frozen rolling-origin
development evaluation. C1/C2 validation, C3, Strategy-v1 P&L, the protected
reserve, and all execution remain closed.

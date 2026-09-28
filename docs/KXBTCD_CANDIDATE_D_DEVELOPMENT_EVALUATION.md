# KXBTCD Candidate-D Development Evaluation

**Checkpoint:** 18C
**Status:** IMPLEMENTATION PREPARED — RESULT PENDING
**Candidate:** `kxbtcd_market_logit_recalibration.v1`
**Frozen predeclaration fingerprint:** `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`
**Week-map fingerprint:** `ba93f6a063c616a34437d6f9d208e39b85c993868c71ea78db8b40a70ec23dff`

## Purpose

Checkpoint 18C implements the already-frozen Checkpoint-18B Candidate-D development stability screen. It does **not** redesign Candidate D.

## Inputs

The evaluator uses:

1. the frozen Checkpoint-12 pre-outcome development dataset solely to validate the 58 UTC-week chronology and seven-block map before labels are loaded; and
2. the canonical Checkpoint-13 train+validation development predictions/outcomes for the 231 exposed development events.

Checkpoint-17 terminal data are not an input.

## Candidate D

The implementation exactly follows the predeclaration:

```text
market_logit = logit(clip(q_market, 0.001, 0.999))
logit(p_D) = market_logit + alpha + delta * market_logit
```

Raw is nested at `alpha=0`, `delta=0`.

No spread, interaction, scaling, regularization, or hyperparameter search is used.

## Why the market logit is an offset

Writing the model as:

```text
logit(p_D) = market_logit + correction
```

makes the raw market the zero-correction baseline. `alpha` supplies a common shift and `delta * market_logit` changes the overall calibration slope. This is algebraically identical to `alpha + (1+delta)*market_logit`, but the offset form makes the frozen raw nesting explicit.

## Objective

Each event receives equal total fit weight. If an event contributes `n` rows, each row receives `1/(number_of_events * n)` weight. The same equal-event convention is used for log loss and Brier scoring.

## Chronology

The committed `configs/kxbtcd_candidate_d_week_blocks.json` contains the exact 58-week outcome-blind map implied by the Checkpoint-18B freeze:

- block weeks: `9 / 9 / 8 / 8 / 8 / 8 / 8`
- block events: `35 / 36 / 32 / 32 / 32 / 32 / 32`
- scored blocks: B2-B6
- scored events: 160

Before outcomes are loaded, the evaluator reconciles this map to the frozen pre-outcome dataset and fails closed if the week/event structure changed.

## Frozen folds

1. B0+B1 → B2
2. B0+B1+B2 → B3
3. B0+B1+B2+B3 → B4
4. B0+B1+B2+B3+B4 → B5
5. B0+B1+B2+B3+B4+B5 → B6

## Optimizer

The code implements the frozen deterministic damped-Newton contract:

- initialize `alpha=0`, `delta=0`;
- maximum 100 iterations;
- gradient L2 tolerance `1e-8`;
- Armijo constant `1e-4`;
- minimum step scale `2^-40`;
- singular Hessian, non-descent direction, failed line search, non-convergence, or nonfinite values fail closed.

No optimizer setting is tuned from Candidate-D results.

## Frozen development gate

All conditions must pass:

1. pooled OOF log loss strictly beats raw;
2. pooled OOF Brier is no worse;
3. at least 4 of 5 score blocks strictly beat raw on log loss;
4. B6 strictly beats raw on log loss;
5. median event-level raw-minus-D log-loss delta is positive;
6. all five fits converge and are finite;
7. all five fitted market-logit slopes are positive.

Coefficient variation is reported but is not given a post-hoc threshold.

## Outputs

A successful run writes:

- `candidate_d_development_summary.json`
- `candidate_d_fold_scores.csv`
- `candidate_d_fold_coefficients.csv`
- `candidate_d_oof_predictions.csv`
- `candidate_d_event_scores.csv`

under `data/analysis/kxbtcd_candidate_d_development/<UTC timestamp>/`.

## Interpretation boundary

A development PASS is only evidence that the frozen simple calibration survived the exposed-development stability screen. It does not constitute an untouched validation result, demonstrate profitability, or authorize execution.

Any later terminal evaluation requires a separately frozen final model and genuinely future untouched events. The Checkpoint-17 terminal block remains permanently prohibited.

## Safety

The evaluator contains no network client and no execution path. It records zero terminal rows/labels/features, zero network requests, and zero orders.

<!-- CHECKPOINT18C_CANDIDATE_D_RESULT_20260815 -->
## Checkpoint 18C result — Candidate D fails the frozen development advancement gate

Run: `data/analysis/kxbtcd_candidate_d_development/20260815T234004Z`
Evaluation-result fingerprint: `b72617517d7bbc3bc1e01ff332496efaf5ba0c64c5eb445f82574e63fa4a47ab`

The frozen Candidate-D exposed-development screen completed without implementation, lineage, convergence, terminal-firewall, network, or execution failures.

### Pooled result

- development scope: 231 events / 5,364 rows
- scored OOF scope: 160 events / 3,726 rows
- raw event-weighted log loss: `0.15456664732282768`
- Candidate-D event-weighted log loss: `0.15159108042312835`
- raw-minus-D log-loss delta: `+0.002975566899699328`
- raw event-weighted Brier: `0.037893942261917626`
- Candidate-D event-weighted Brier: `0.026426318458628383`
- raw-minus-D Brier delta: `+0.011467623803289244`
- median event raw-minus-D log-loss delta: `+0.04671924978445033`
- better / worse / tie events: `149 / 11 / 0`

### Chronological block result

- B2 log-loss delta: `+0.093203479823316726`
- B3 log-loss delta: `+0.0061807888233462449`
- B4 log-loss delta: `+0.076486093656489507`
- B5 log-loss delta: `-0.029863425409502709`
- B6 log-loss delta: `-0.13112910239515319`

Candidate D therefore won only `3/5` score blocks. The latest B6 block also failed. These are exactly the two frozen advancement failures:
- `fewer_than_4_of_5_score_block_log_loss_wins`
- `latest_B6_log_loss_not_strictly_better`

B5 still improved Brier by `+0.0084444935043224527` while losing log loss, whereas B6 worsened Brier by `-0.0067525021571954863` as well as log loss. This is consistent with increasingly costly confidence errors and a stronger late-period breakdown by B6, but that mechanism is an interpretation rather than a separately validated causal claim.

### Coefficient stability

All five fits converged and all market-logit slopes were positive:

`3.1982462074078875, 3.4689767579266322, 2.6971700475935849, 2.7317860853200795, 2.3714201483058033`

The fitted model consistently sharpened the raw market because every slope exceeded the raw benchmark slope of `1`. This descriptive fact does not authorize a post-hoc slope cap, regularization change, or Candidate-D retune on this same screen.

### Decision

**Candidate D development advancement result: FAIL.**

Candidate D does not advance to a final development fit or prospective terminal evaluation under this specification. Do not repair, retune, regularize, cap, or otherwise modify Candidate D and then claim the same 160-event score set as a fresh advancement test.

This result does not establish that all market calibration is useless. It establishes only that this frozen two-parameter successor did not meet its predeclared temporal-stability requirement.

Checkpoint-17 terminal data remained unused: 0 terminal rows / labels / features; network requests 0; execution disabled; orders 0.

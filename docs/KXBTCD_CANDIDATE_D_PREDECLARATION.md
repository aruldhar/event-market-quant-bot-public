# KXBTCD Candidate-D Predeclaration

**Checkpoint:** 18B
**Status:** FROZEN DESIGN — NO CANDIDATE-D FIT PERFORMED
**Candidate ID:** `kxbtcd_market_logit_recalibration.v1`
**Predeclaration fingerprint:** `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`
**Date frozen:** 2026-08-15

## Purpose

Checkpoint 18A found that Candidate C had broad historical development improvement but materially weakened in the latest development block, was highly sensitive to the weakest regularization choice, and used spread to create large probability corrections without an independent BTC-state signal. Candidate D is therefore intentionally simpler.

This document freezes Candidate D **before any Candidate-D fit, score, or hyperparameter search**.

## Evidence boundary

Allowed design evidence is the already-exposed 231-event / 5,364-row development pool and Checkpoint-18A diagnostics from `20260815T231543Z`.

The Checkpoint-17 64-event terminal block remains permanently exposed and prohibited as successor-design or optimization evidence. Its aggregate historical fact — Candidate C failed the terminal gate — may be retained, but no terminal rows, labels, features, predictions, residuals, slices, or event-level results may be loaded.

## Exact model

Let `q_market` be the Kalshi midpoint probability.

1. Require `q_market` in `[0,1]`.
2. Clip only for the model transform to `[0.001, 0.999]`.
3. Compute:

```text
market_logit = ln(q_clipped / (1 - q_clipped))
```

Candidate D is:

```text
logit(p_D) = market_logit + alpha + delta * market_logit
```

Equivalently:

```text
logit(p_D) = alpha + (1 + delta) * market_logit
```

The raw market is nested exactly at:

```text
alpha = 0
delta = 0
```

There is **no feature scaling**, **no spread feature**, **no market-logit × spread interaction**, and **no other feature**.

The raw benchmark probability used for metrics remains the original `q_market` midpoint, not the clipped transform.

## Fit objective and optimizer

Fit `alpha` and `delta` by event-weighted binary log loss:

- each event receives equal total weight;
- rows within an event share that event weight equally;
- no regularization;
- no hyperparameter grid;
- no hyperparameter search.

Initialize at the raw benchmark: `alpha=0`, `delta=0`.

Use deterministic damped Newton with:

- maximum iterations: `100`
- gradient L2 tolerance: `1e-8`
- Armijo constant: `1e-4`
- minimum step scale: `2^-40`
- non-convergence: fail closed
- singular Hessian: fail closed

## Frozen seven-block chronological layout

The 58 unique development UTC weeks are sorted ascending and divided into seven contiguous blocks, with earlier blocks receiving the two remainder weeks. Layout construction is outcome-blind.

| Block | Weeks | Events | First UTC week | Last UTC week |
|---|---:|---:|---|---|
| B0 | 9 | 35 | 2025-03-17 | 2025-05-12 |
| B1 | 9 | 36 | 2025-05-19 | 2025-07-14 |
| B2 | 8 | 32 | 2025-07-21 | 2025-09-08 |
| B3 | 8 | 32 | 2025-09-15 | 2025-11-03 |
| B4 | 8 | 32 | 2025-11-10 | 2025-12-29 |
| B5 | 8 | 32 | 2026-01-05 | 2026-02-23 |
| B6 | 8 | 32 | 2026-03-02 | 2026-04-20 |

Frozen rolling-origin development folds:

1. fit B0+B1 → score B2
2. fit B0+B1+B2 → score B3
3. fit B0+B1+B2+B3 → score B4
4. fit B0+B1+B2+B3+B4 → score B5
5. fit B0+B1+B2+B3+B4+B5 → score B6

The scored development set is exactly 160 events: 32 in each of B2-B6.

These are **exposed development events**. This protocol is a stability screen, not an untouched test.

## Frozen metrics

Primary metric:
- pooled OOF event-weighted log loss.

Secondary metric:
- pooled OOF event-weighted Brier score.

Also report:
- raw and Candidate-D log loss/Brier by score block;
- event-level raw-minus-D log-loss deltas;
- median event-level delta;
- fitted `alpha`, `delta`, and slope `1+delta` for every fold;
- convergence and finite-value checks.

Primary ties fail.

## Frozen development advancement gate

Candidate D passes the development screen only if **all** conditions hold:

1. pooled raw-minus-D event-weighted log-loss delta is strictly `> 0`;
2. pooled raw-minus-D event-weighted Brier delta is `>= 0`;
3. Candidate D strictly beats raw log loss in at least **4 of 5** score blocks;
4. Candidate D strictly beats raw log loss in the **latest B6 block**;
5. median event-level raw-minus-D log-loss delta is strictly `> 0`;
6. all five fits converge and all parameters, scored probabilities, and metrics are finite;
7. every fitted market-logit slope `1 + delta` is strictly `> 0`.

A development PASS means only that Candidate D may proceed to a separately frozen final development fit and prospective-test design. It is not validation, profitability evidence, or execution authorization.

## Instability and fail-closed rules

Automatic failure:
- optimizer non-convergence;
- singular Hessian;
- nonfinite parameter, prediction, or metric;
- any fitted `1+delta <= 0`;
- changed/missing canonical lineage or block membership;
- any access to prohibited terminal data.

Coefficient drift is reported, but no post-hoc numeric drift threshold may be invented after seeing the results.

## Future untouched-test boundary

- Checkpoint-17 terminal events can never be reused.
- New terminal membership must be predeclared before outcomes are opened.
- New test events must be genuinely future relative to this Candidate-D design freeze.
- The stricter preferred boundary is that terminal-eligible event start times occur after the later Candidate-D **final-model freeze timestamp**.
- Terminal sample size remains unresolved and must be frozen separately before terminal collection/scoring. It may not be chosen from observed terminal outcomes.

## Safety

Checkpoint 18B authorizes **design freeze only**. It does not authorize Candidate-D fitting, network collection for this development screen, paper execution, demo execution, orders, transfers, or real-money execution.

# KXBTCD Candidate-E Conditional-Alpha Reliability v2 Predeclaration

## Checkpoint 21N-M-A

Status: **PREDECLARATION ONLY — REAL v2 FIT NOT AUTHORIZED**.

Candidate: `kxbtcd_candidate_e_conditional_alpha_reliability.v2`

Predeclaration fingerprint:

`6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8`

Parent v1 predeclaration fingerprint:

`742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`

## Why v2 exists

Conditional-alpha v1 remains permanently closed as `FAIL_OPTIMIZER_CONTRACT`.
Its first required BFGS sequence failed at lambda `0.001`, Fold 2 because the
predeclared absolute curvature rule `y^T s > 1e-12` failed before the strict
gradient convergence criterion was met.

That failure is not reclassified or rescued. v2 is a separately versioned
successor created only after post-failure numerical diagnostics established that
the same five-parameter objective can be solved cleanly by the project's existing
damped-Newton pattern.

## Simple optimizer interpretation

All optimizers were trying to minimize the **same loss**. They differed only in
how they chose the next gamma step.

- **BFGS** estimates curvature from the history of previous moves. It reached the
  neighborhood of the optimum quickly, but its curvature-update quantity became
  too small for the frozen v1 rule. The experiment therefore stopped exactly as
  predeclared.
- The **skip/restart BFGS diagnostics** showed that merely ignoring tiny curvature
  or resetting the BFGS map does not solve the problem; both spent 470 of 500
  later iterations in the safeguard state and still missed the gradient target.
- The exploratory **nonlinear-CG run** produced `beta=0` throughout the reported
  path, so it effectively behaved like steepest-descent gradient descent. It was
  stable but much too slow.
- **Newton** calculates the local curvature directly from the exact Hessian. With
  only five parameters, solving that 5x5 system is cheap. The exact Hessian was
  independently checked against finite differences, and damped Newton passed all
  10 frozen lambda/fold fit cases in at most 9 iterations.

Newton does not change what solution is optimal. It is a different numerical
route to the same frozen objective.

## Scientific contract inheritance

v2 inherits **every scientific rule from v1 unchanged except the optimizer**.
This includes the conditional-alpha formula, four features, exclusions, scaler,
five parameters, all-zero initialization, event-equal loss, L2 treatment, lambda
grid, rolling-origin folds, lambda-selection metric, probability benchmarks,
probability gate, economic policy/gate, and evidence firewalls.

No feature, lambda, threshold, gate, subgroup, side, TTC, role, or economic rule
is changed by 21N-M-A.

## Exact v2 optimizer

For each fit partition and each frozen lambda:

1. Start all five gamma values at zero.
2. Calculate the exact frozen objective and analytic gradient.
3. Calculate the exact analytic 5x5 Hessian of that same objective.
4. Add the frozen L2 curvature `lambda` to all five Hessian diagonal terms,
   because all five gamma parameters including the intercept are regularized.
5. Solve `H * delta = gradient` using the project's deterministic dense Cholesky
   solve.
6. Require `gradient^T delta > 0`.
7. Propose `gamma_new = gamma - step * delta`.
8. Use Armijo backtracking with `c1=1e-4`, initial step `1`, shrink factor `.5`,
   and minimum step `2^-40`.
9. Converge only when the gradient L2 norm is `<= 1e-8`.
10. Stop with failure after 100 iterations if convergence has not occurred.

Fail closed on non-finite state, Cholesky/non-positive-definite Hessian failure,
non-descent direction, line-search failure, or non-convergence.

There is **no** Hessian jitter, diagonal loading, pseudoinverse, BFGS fallback,
gradient-descent fallback, CG fallback, warm start, or optimizer choice by lambda.

## Numerical design evidence already exposed

These diagnostics are architecture-development evidence only. They may not be
used to claim v2 predictive performance.

- v1 hard failure: lambda `.001`, Fold 2, gradient/tolerance `132.35`,
  `y^T s = 7.5065e-13`.
- skip-small-curvature diagnostic: 500 iterations, 470 skips, no convergence.
- identity-Hessian-reset diagnostic: 500 iterations, 470 resets, no convergence.
- exploratory nonlinear-CG path: 500 iterations, reported `beta=0`, no convergence.
- analytic gradient: finite-difference check PASS.
- analytic Hessian: finite-difference check PASS; max absolute error about
  `2.34e-11` at the origin and `1.86e-12` near the v1 failure point; Cholesky
  PASS at both tested points.
- exact hard-case damped Newton: PASS in 8 iterations.
- full numerical qualification matrix: **10/10 PASS**, maximum 9 iterations;
  only one case required one half-step backtrack.

No lambda was selected from these diagnostics. No H2/H3 prediction metrics,
probability gate, conditional-alpha P&L, C1/C2/C3 score, or reserve result was
opened for v2.

## Evidence roles and contamination boundary

H1_OOF/H2/H3 remain fully exposed development evidence. Today’s diagnostics make
no fresh-validation claim.

C1+C2 are not authorized in 21N-M-A. C3 remains locked against conditional-alpha
development. The protected reserve remains sealed.

## Safety

The phase remains read-only. No order submission/cancellation, paper broker,
demo execution, real-money execution, portfolio transfer, or risk-policy change
is authorized.

## Next checkpoint

Checkpoint **21N-M-B** may implement and independently test the exact v2 Newton
mechanics only. It must not run the real v2 rolling-origin lambda selection,
probability gate, economic evaluation, C1/C2/C3 evaluation, or reserve access.

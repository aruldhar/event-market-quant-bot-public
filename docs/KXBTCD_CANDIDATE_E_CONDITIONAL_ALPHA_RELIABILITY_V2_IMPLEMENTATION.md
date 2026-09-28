# KXBTCD Candidate-E Conditional-Alpha Reliability v2 Implementation Freeze

## Checkpoint 21N-M-B

Status: **IMPLEMENTATION ONLY — REAL v2 FIT NOT AUTHORIZED**.

Predeclaration fingerprint:

`6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8`

Implementation fingerprint:

`459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd`

## What changes

Only the numerical optimizer changes relative to the permanently failed v1.

v2 reuses the frozen v1:

- four-feature vector;
- event-equal scaler;
- five-parameter conditional-alpha map;
- binary-settlement objective;
- L2 regularization on all five gamma parameters;
- lambda grid;
- probability mapping and downstream scientific rules.

The new module adds:

1. the exact analytic 5x5 Hessian;
2. a deterministic dense Cholesky solve;
3. damped Newton steps with the frozen Armijo line search;
4. strict fail-closed behavior with no jitter, diagonal loading, pseudoinverse, or fallback optimizer.

## Why this is an optimizer-only implementation

The objective is unchanged:

`p = q + sigmoid(gamma^T x) * (pE - q)`

`L = event_equal_binary_log_loss + (lambda/2) * ||gamma||^2`

Newton changes only how the same minimum is found.

For one row, with `a = sigmoid(eta)` and `d = pE-q`:

`dp/deta = d*a*(1-a)`

`d2p/deta2 = dp/deta*(1-2a)`

The row's scalar curvature in eta is:

`d2loss/dp2 * (dp/deta)^2 + dloss/dp * d2p/deta2`

That scalar multiplies `x x^T`, with event-equal row weight. L2 contributes `lambda` to all five diagonal Hessian elements.

## Fail-closed rules

The implementation stops rather than silently changing algorithms when:

- the Hessian or other numerical state is non-finite;
- Cholesky cannot factor the exact Hessian;
- the Newton direction is non-descent;
- Armijo cannot find an acceptable step before `2^-40`;
- gradient norm remains above `1e-8` after 100 iterations.

There is no jitter, diagonal loading, pseudoinverse, BFGS fallback, gradient-descent fallback, CG fallback, or optimizer selection by lambda/fold.

## Evidence firewall

21N-M-B contains no real-data fit or evaluation CLI.

This checkpoint does not:

- select lambda;
- score H2/H3 conditional-alpha predictions;
- run the probability gate;
- calculate conditional-alpha P&L;
- access C1/C2;
- access C3;
- access the protected reserve;
- authorize paper, demo, or real execution.

H1/H2/H3 remain fully exposed development evidence. v1 remains permanently `FAIL_OPTIMIZER_CONTRACT`.

## Acceptance target

Before any later real v2 fit:

- implementation validator PASS;
- finite-difference Hessian unit test PASS on synthetic rows;
- synthetic Newton convergence tests PASS;
- Cholesky fail-closed tests PASS;
- full repository regression PASS;
- source registry PASS;
- safe closeout with clean synchronized `main`.

# KXBTCD Conditional-Alpha Reliability v1 — Optimizer-Failure Recording Repair

## Checkpoint 21N-L

Repair fingerprint:

`276fdf07803d083a67d94e6c5b923fcbf06392c4db4fb33cd1d9c1f3a954a865`

The first real H-development attempt reached the frozen BFGS fitter and failed at:

- lambda: `0.001`
- fold: `2`
- fit stages: `H1_OOF + H2`
- intended score stage: `H3`
- error: `BFGS positive-curvature requirement y^T s > 1e-12 failed`

Fold 1 at lambda 0.001 had converged in 40 iterations. Fold 2 did not satisfy the
frozen convergence tolerance before the positive-curvature requirement failed.

## Scientific interpretation

This is already a predeclared development failure. The optimizer contract requires
every fit to converge and requires `y^T s > 1e-12` unless the new gradient has
already converged.

The repair does **not** alter that result. It only converts the thrown exception
into a deterministic persisted scientific artifact:

`FAIL_OPTIMIZER_CONTRACT`

The repaired evaluator stops immediately at the same required-fit failure. It does
not try later lambdas, select lambda, score the probability gate, calculate new
conditional-alpha P&L, or fit the full H-development model.

## Forbidden repairs

No change is made to the frozen BFGS implementation, curvature threshold, gradient
tolerance, line search, lambda grid, features, scaling, event weights, or gates.
There is no skip-on-failure, fallback optimizer, or rescue refit.

## Evidence firewall

The first failed run created no partial output artifacts. H1/H2/H3 are already
development-exposed evidence. C1+C2 remain unauthorized for conditional alpha,
C3 remains locked, and the protected reserve remains sealed. Execution remains
prohibited.

After this repair is tested and safely closed, rerun the exact same H-development
command once so the failure can be persisted and independently reproduced.

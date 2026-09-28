# KXBTCD Candidate-E Conditional-Alpha Reliability v1 — Implementation Freeze

## Checkpoint

**21N-J-A — implementation freeze before real outcome-blind materialization**

Implementation fingerprint:

`566f085ef78e8045a75a1dc3781255a2dcae30f23d04ba317ab56e87ac18f5a6`

Parent exact predeclaration:

`742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`

## Purpose

This checkpoint converts the frozen 21N-I statistical design into deterministic,
network-free code while keeping project outcomes inaccessible to the new model.

The implementation is not evidence that conditional alpha improves forecasting
or trading economics. It only establishes that the future experiment has a
specific executable interpretation.

## Inputs and outputs

### Core model mechanics

Inputs:
- the four frozen raw features;
- fit-partition scaler statistics;
- a five-element gamma vector;
- later, only when separately authorized, binary settlement outcomes.

Outputs:
- `alpha = sigmoid(gamma^T x)`;
- `p_adj_yes = q + alpha * (pE - q)`;
- deterministic scaler/optimizer/model objects;
- the frozen downstream quoted-entry choice when supplied adjusted probabilities.

Failure modes are fail-closed: non-finite state, alpha saturation to exactly zero
or one, invalid quote/probability bounds, invalid scaler variance, non-descent
BFGS direction, line-search failure, non-convergence, or failed curvature after
the new gradient has not already converged.

### Outcome-blind materialization

The future real-data materializer does **not** invent a new history.

It requires:
1. the exact frozen 21M Model-2 preparation receipt;
2. the exact 76,419-row Model-2 feature CSV whose file SHA-256 is
   `0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c`;
3. the exact preoutcome source already bound by that preparation receipt.

It projects only:
- `abs(pE_yes-q_yes)`;
- `spread_t`;
- `abs(r_5m)`;
- continuous TTC.

`q_yes` is reconstructed from the same frozen two-sided quote as
`(yes_bid + yes_ask)/2`. The parent Model-2 `spread_t` must exactly agree with
that preoutcome bid/ask up to `1e-12`; otherwise materialization fails closed.

Candidate-E probabilities and `r_5m` are **not regenerated**.

## Why reuse the 21M row universe

This isolates the research question.

If conditional alpha had a different timestamp alignment, different missing-data
policy, or different BTC materialization, a later performance difference could
come from the data pipeline rather than the reliability model. Projecting the
same frozen causal state universe makes the model comparison interpretable.

## BFGS implementation

Every lambda starts from:

`gamma = [0,0,0,0,0]`

so alpha begins at `.50` for every row. The inverse-Hessian approximation begins
as the 5x5 identity.

Frozen constants:
- max iterations: 500
- gradient L2 tolerance: `1e-8`
- Armijo `c1`: `1e-4`
- initial step: `1`
- backtrack multiplier: `.5`
- minimum step: `2^-40`
- positive curvature: `y^T s > 1e-12`
- no warm starts

Implementation interpretation of the frozen positive-curvature requirement:
after an accepted step, first check the new gradient for convergence. If the fit
is not converged and `y^T s <= 1e-12`, fail closed rather than skip/reset the
BFGS update.

## Evidence firewall

21N-J-A must not:
- read real conditional-alpha outcomes;
- fit gamma on project data;
- select lambda;
- calculate conditional-alpha P&L;
- access C1/C2 for conditional alpha;
- access C3;
- access the protected reserve;
- use network access;
- place, cancel, or simulate orders.

The real outcome-blind materializer exists as code but is fail-closed until
`docs/LAST_CHECKPOINT_CLOSEOUT.json` records a safely closed 21N-J-A containing
the required implementation paths. This makes the phase boundary executable,
not merely procedural.

## Acceptance sequence

1. Apply the 21N-J-A bundle.
2. Run the implementation validator and focused synthetic tests.
3. Run the full repository regression and source-registry validator.
4. Safely close/push 21N-J-A.
5. Only then begin 21N-J-B and run the real outcome-blind materialization.
6. Independently rematerialize and validate the 76,419 rows.
7. Safely freeze 21N-J-B.
8. Only a later checkpoint may attach already-exposed H-development outcomes and
   run the predeclared rolling-origin fits once.

No profitability claim is made.

# KXBTCD Candidate-E Conditional-Alpha Reliability v2 Development Evaluator

## Checkpoint 21N-M-C

Status: **EVALUATOR IMPLEMENTATION ONLY — DO NOT RUN REAL v2 DEVELOPMENT YET**.

Parent v2 predeclaration:

`6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8`

Parent v2 Newton implementation:

`459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd`

Evaluator implementation fingerprint:

`bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`

## Purpose

Wire the already-frozen H1_OOF/H2/H3 development experiment to the new v2
exact-Hessian Newton fitter without opening any new evidence or running the
formal v2 evaluation during this checkpoint.

## What is inherited unchanged

The evaluator reuses the frozen v1:

- exact prepared 76,419-row state universe and its hashes;
- H1_OOF/H2/H3 label-source hashes;
- exact state-ID label attachment;
- event-equal scoring;
- five-lambda grid and two rolling-origin folds;
- pooled H2+H3 log-loss lambda selection;
- larger-lambda exact tie rule;
- Kalshi, Candidate-E, and alpha-.50 probability benchmarks;
- complete probability gate;
- one-contract first-qualifying-anchor entry policy;
- fee rule and +0c/+1c/+2c/+3c quote stress;
- five contiguous 300-event H2+H3 economic blocks;
- complete economic gate;
- full H1+H2+H3 fit only after both gates pass.

The only learned fitter used by v2 is
`fit_conditional_alpha_v2`, already frozen in 21N-M-B.

## Sequential evidence policy

The real run, after this checkpoint is safely closed, must proceed:

1. validate exact prepared-state and H-label hashes;
2. fit all five lambdas on Fold 1 and Fold 2 with v2 Newton;
3. select lambda by pooled H2+H3 event-equal log loss;
4. score the full frozen probability gate;
5. **only on probability PASS**, calculate the frozen quoted-entry economics;
6. **only if both gates PASS**, fit selected lambda on H1_OOF+H2+H3.

If a required Newton fit fails, stop. No jitter, fallback optimizer, skipped
lambda/fold, or solver repair is allowed.

## Evidence interpretation

H1/H2/H3 are fully exposed development evidence. The post-v1 optimizer
diagnostics already inspected numerical convergence on these fit partitions.
Therefore a v2 PASS would be development evidence only, not fresh validation.

C1+C2 remain unauthorized at this stage. C3 remains locked against
conditional-alpha development. The protected reserve remains sealed.

No network access or execution is used.

## Important: economics remain conditional

The v2 evaluator does **not** calculate P&L unless the selected v2 model first
passes the complete probability gate. This preserves the evidence-minimizing
sequence frozen in 21N-I.

## After 21N-M-C closeout

Exactly one formal H-development run may be made using the frozen local paths.
The CLI itself verifies that the latest closeout receipt is 21N-M-C and contains
all required evaluator files.

That run is the next checkpoint. It is not part of 21N-M-C.

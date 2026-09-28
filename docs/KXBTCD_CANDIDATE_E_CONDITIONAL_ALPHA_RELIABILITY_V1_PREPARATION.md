# KXBTCD Candidate-E Conditional-Alpha Reliability v1 — Outcome-Blind Preparation Closeout

## Checkpoint

**21N-J-B — outcome-blind development preparation accepted**

Preparation-closeout fingerprint:

`f1b0caed9d83d8657bd916422b17dde4e239cbc41a5de880ed78a51217cdffb1`

Frozen conditional-alpha preparation fingerprint:

`a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46`

## What was accepted

The conditional-alpha development feature table was materialized from the exact frozen
Checkpoint-21M state universe after Checkpoint 21N-J-A had been safely closed.

The materializer produced:

- 2,570 development events;
- 76,419 feature rows;
- H1_OOF: 1,070 events / 31,656 rows;
- H2: 750 events / 22,354 rows;
- H3: 750 events / 22,409 rows.

Feature-row fingerprint:

`590ab13567821839fb0d404ed4813d328fc4e68ee1a61fd39038d3f8624a42fe`

Persisted CSV SHA-256:

`268c756f82f6be2b53f5fee1f212ad0ecd1d02459547861cc5c3b3623357472f`

## Parent lineage

The accepted projection is cryptographically bound to:

- Checkpoint-21M preparation fingerprint
  `2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`;
- parent feature CSV SHA-256
  `0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c`;
- parent preoutcome CSV SHA-256
  `32ce45e30d2b8c9d57fe68940e4bc791fec76e061ae01b5f07f042f4a9169028`;
- Checkpoint-21N-J-A implementation fingerprint
  `566f085ef78e8045a75a1dc3781255a2dcae30f23d04ba317ab56e87ac18f5a6`.

Candidate-E historical probabilities and `r_5m` were not regenerated.

## Independent validation

The independent preparation validator rematerialized all 76,419 rows from the
parent inputs and reproduced the persisted feature-row fingerprint and preparation
fingerprint exactly.

Validation result: **PASS**.

This is reproducibility evidence only. It is not evidence that conditional alpha
improves probability forecasts or trading economics.

## Evidence firewall

21N-J-B used no settlement outcome field and performed no gamma fit, lambda
selection, probability gate, realized P&L calculation, C1/C2 access, C3 access,
protected-reserve access, network request, paper/demo/live execution, or order
action.

## Next checkpoint

The next checkpoint must first freeze and validate the exact H1_OOF/H2/H3
label-attachment and rolling-origin development-evaluation orchestration.

Only after that evaluator/orchestration checkpoint is safely closed may the
already-exposed H-development labels be attached and the predeclared gamma/lambda
development procedure be run once.

C1+C2 remain closed to conditional alpha. C3 remains locked. The protected
reserve remains sealed. Execution remains prohibited.

No profitability claim is made.

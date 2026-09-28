# KXBTCD Candidate-E Entry Model v1 — Development Evaluation Implementation

## Status

Checkpoint 21M pre-evaluation implementation. **No real Model-2 development outcomes are opened by this document or its installation tests.**

The accepted pre-outcome boundary is Git commit:

`cc91a15ae65954370279025d1afe6c857c8d899b`

Accepted preparation fingerprint:

`2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`

The frozen development universe remains 2,570 events / 76,419 rows:

- H1_OOF: 1,070 events / 31,656 rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows

## Purpose

The Model-2 mathematics was frozen before outcomes. This checkpoint substep adds only the deterministic real-data orchestration needed to attach the already-exposed H1_OOF/H2/H3 settlement labels to those frozen states and execute D-021L-04 exactly.

The orchestration is frozen and committed **before** any real development evaluation is run.

## Inputs

Only five logical inputs are authorized for the real development evaluation:

1. accepted outcome-blind development feature CSV;
2. accepted preparation-freeze JSON;
3. frozen H1 OOF Candidate-E prediction/evaluation CSV;
4. frozen H2 Candidate-E prediction/evaluation CSV;
5. frozen H3 Candidate-E prediction/evaluation CSV.

The preparation receipt already binds the three prediction-source hashes. The runner verifies those hashes before label attachment.

C1, C2, C3 and the protected reserve are not CLI inputs.

## Exact label attachment

The label source is projected to:

- stage;
- state_id;
- event_ticker;
- market_ticker;
- outcome.

Rows whose `candidate_id` is not the frozen Candidate-E ID are ignored. This matters for H1 OOF because its historical output also contains the rejected momentum challenger.

The Candidate-E state set must match the already-frozen feature state set exactly. Missing states, extra states, duplicate Candidate-E states, cross-stage states, incomplete identities, conflicting labels, or non-binary outcomes fail closed.

Outcome values do not alter feature construction, row eligibility, chronology, scaling feasibility, or the accepted preparation fingerprint.

## Frozen rolling-origin procedure

No scientific rule changes from D-021L-04:

1. fit H1_OOF, score H2, for every lambda in `{0.001, 0.01, 0.1, 1, 10}`;
2. fit H1_OOF+H2, score H3, for every frozen lambda;
3. pool H2+H3 by event-equal log loss;
4. select the minimum pooled log loss; exact ties choose the larger lambda;
5. fit one H1_OOF+H2+H3 development model at the selected lambda.

The Candidate-E logit offset coefficient remains exactly one. All 21 residual coefficients remain L2-penalized including the intercept. Scaling remains fit-only and event-equal. The deterministic damped-Newton solver and dense Cholesky implementation are unchanged.

## Development diagnostics

For the selected lambda, the runner also reports Model-2 versus Candidate-E event-equal log loss and Brier diagnostics on:

- H2 using the H1_OOF fit;
- H3 using the H1_OOF+H2 fit;
- pooled H2+H3.

These are **development diagnostics**, not the D-021L-05 advancement gate. No claim of profitability or validation success may be made from them.

## Persisted outputs

The real evaluation runner writes:

- `candidate_e_entry_model_v1_development_evaluation.json`
- `candidate_e_entry_model_v1_development_lambda_scores.csv`
- `candidate_e_entry_model_v1_development_receipt.json`

The receipt binds source hashes, implementation hashes, output hashes, selected lambda, evaluation fingerprint, and explicit safety flags.

The independent validator re-reads the same frozen sources, independently reattaches labels, reruns the complete deterministic development evaluation, and requires exact equality with the persisted result.

## Safety boundary

This substep does not authorize or calculate:

- C1/C2 Model-2 validation;
- C3 Model-2 evaluation;
- protected-reserve access;
- Strategy-v1 P&L;
- paper trading;
- demo trading;
- real-money trading;
- orders, cancellations, transfers, or portfolio actions.

The next scientific decision after a validated development result is to record the selected lambda and development diagnostics. Only then may the separately frozen D-021L-05 C1+C2 validation gate be considered.

<!-- CHECKPOINT21M_VALIDATED_DEVELOPMENT_RESULT_20260819 -->
## Validated development result

The real development lifecycle is now complete and independently validated.

Selected lambda: `0.01`.

Pooled H2+H3 event-equal log loss:
- Model-2: `0.03736587903471904`;
- Candidate E: `0.03740705507861643`;
- Candidate-E-minus-Model-2: `+0.0000411760438973896`.

H2 improved; H3 worsened slightly. The aggregate gain is small. This result is used
only to freeze the development-selected Model-2 before validation; it is not the
D-021L-05 validation gate and is not evidence of profitability.

Exact coefficients/scaler and all provenance are frozen in
`configs/kxbtcd_candidate_e_entry_model_v1_development_freeze.json`.

Development-freeze fingerprint:
`a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e`.

C1+C2 may now be considered only under the already-frozen five-condition validation
gate. No retuning or post-hoc Model-2 repair is permitted.

<!-- CHECKPOINT21M_C1C2_VALIDATION_PREPARATION_NOTE -->
## C1+C2 validation preparation

The development-selected Model-2 remains unchanged. The 1,000-event C1+C2
validation universe was prepared outcome-blind with stage-native Candidate-E
baselines and the frozen execution archive.

Validation-preparation fingerprint: `25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22`.

No C1/C2 Model-2 outcome or validation score was read/calculated in this step.

# Candidate-E Entry Model v1 — C1+C2 Validation Evaluator Freeze

## Status

Implementation frozen before Model-2 C1+C2 outcome access.

Validation implementation fingerprint:

`8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`

## Parent evidence

- Model-2: `kxbtcd_candidate_e_entry_residual_logistic.v1`
- selected lambda: `0.01`
- development freeze:
  `a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e`
- C1+C2 preparation:
  `25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22`
- 1,000 validation events / 28,894 rows
- five chronological 200-event blocks V0..V4

## Fixed evaluator

The evaluator applies the exact 21 development coefficients and 11 development
scaler statistics. It performs no fit, rescaling, lambda selection, feature
selection, or threshold search.

Candidate E remains the mandatory benchmark.

The six historical C2 probability endpoints are preserved without clipping.
Their exact finite latent logits come from the frozen validation-offset sidecar
and are used as the coefficient-1 Candidate-E offset. Binary log loss is computed
stably from logits; Brier is computed from stable-sigmoid probabilities.

## Validation gate

PASS requires all five:

1. pooled Model-2 event-equal log loss < Candidate-E;
2. pooled Model-2 event-equal Brier <= Candidate-E;
3. Model-2 log-loss wins in at least 4/5 blocks;
4. Model-2 wins newest block V4;
5. median event Candidate-E-minus-Model-2 log-loss delta > 0.

Primary log-loss ties fail. Brier ties satisfy condition 2.

## Outcome firewall

During implementation freeze:
- C1/C2 outcome rows read for Model-2: false
- validation scores calculated: false
- C3 opened for Model-2: false
- protected reserve accessed: false
- Strategy-v1 P&L calculated: false
- execution enabled: false

The real evaluator must persist an attempt journal before reading its first C1/C2
outcome row. An interrupted attempt can resume only with the exact same frozen
implementation.

## Post-outcome resume amendment D-021M-11

The first real C1+C2 Model-2 attempt permanently opened outcomes but produced no
score because the evaluator incorrectly looked for an existing safety flag at the
preparation-freeze top level instead of under `candidate_e_baseline`.

Original evaluator fingerprint: `8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`.

The accepted repair changes only that lookup and exact provenance/resume controls.
Fresh attempts are prohibited; only the same persisted attempt may resume after
the repair is committed and pushed.

Resume-repair fingerprint: `fee1063a637c99749e47d67bbb553a480d3e72037be1cb9015b26b67f2275aed`.

## Final C1+C2 result

The same persisted attempt resumed under D-021M-11 and completed deterministically.

Validation gate: **FAIL**.

- evaluation fingerprint: `15a6557736204ca58039906434f8b7e83bca719f14cd0a3b4c9b9094e42ce033`
- receipt fingerprint: `5e37a7abab6065414be00761ac79e09e853e587ab3ccf153e9f5a74081b11e2a`
- result closeout fingerprint: `f27dba7fc5fcf9726a3699b8e611646d0d93b77a3dfdb8050048767a97c36ff7`
- Model-2 log-loss wins: `1/5`
- newest-block win: `False`

Model-2 v1 is rejected. C3 remains sealed for this model. No post-hoc C1+C2
repair, retune, or rescore is authorized.

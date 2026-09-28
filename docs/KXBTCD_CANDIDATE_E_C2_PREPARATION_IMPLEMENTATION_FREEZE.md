# KXBTCD Candidate-E C2 Preparation Implementation Freeze

## Checkpoint

21E-A — Candidate-E C2 preparation implementation freeze.

## Purpose

Freeze the implementation that may later perform the next two evidence-state
transitions, before either occurs:

1. fit the unchanged Candidate-E Distance specification exactly once on the
   already-exposed H1+H2+H3+C1 evidence (3,500 events) and freeze Champion-R1;
2. only after Champion-R1 is safely closed, materialize/freeze C2 outcome-blind.

This checkpoint itself performs neither action.

## Frozen parent state

- Checkpoint-21A lifecycle fingerprint:
  `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- Checkpoint-21D receipt commit:
  `8c32e6f28f0bf625487c46be3f6306f409d8cfd4`
- C1 result fingerprint:
  `5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19`
- C1 result-closeout fingerprint:
  `3a66e7d980334474d4d836f80bc2aca56932baab1040fa393dee9764a3ee737e`
- C1 is permanently exposed and passed.
- C2 and C3 remain untouched.

## Frozen Champion-R1 fit scope

Champion-R1 must remain exactly
`kxbtcd_btc_distance_offset_logistic.v1`.

Its only permitted fit scope is:

- H1: 1,500 events / 36,314 rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows
- C1: 500 events / 14,887 rows
- total: 3,500 events / 95,964 rows

No C2 row or outcome may enter the fit. No feature selection, candidate
selection, regularization search, hyperparameter search, or specification
change is permitted.

## Frozen C2 reserve boundary

C1 consumed strict queue indices `[3200,3706)`. Therefore C2 starts exactly at
index `3706`.

The absolute Checkpoint-21A maximum end-exclusive remains `4931`; it is not
reset after C1. Thus C2+C3 together may inspect at most `1,225` additional
candidate identities while preserving at least 4,500 never-materialized events.

The C2 collector:

- has no arbitrary start-index argument;
- reconstructs progress only from completed hashed C2 chunks;
- accepts at most 100 candidate identities per invocation;
- stops at the exact 500th eligible C2 event;
- checks the absolute reserve boundary before every candidate event;
- never opens outcomes;
- never materializes C3.

## Current checkpoint firewall

At 21E-A freeze:

- Champion-R1 fits: 0
- C2 materialization requests: 0
- C2 outcomes opened: 0
- C3 materialized/opened: 0
- network requests: 0
- execution/orders: disabled / 0

After this implementation is safely closed and pushed, the next authorized
action is the network-free Champion-R1 fit. C2 materialization must wait until
that model artifact is separately closed and pushed.

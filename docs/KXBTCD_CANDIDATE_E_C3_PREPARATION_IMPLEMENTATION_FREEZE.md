# KXBTCD Candidate-E C3 Preparation Implementation Freeze

## Checkpoint

21G-A — Champion-R2 / C3 preparation implementation freeze.

## Purpose

Freeze the deterministic implementation that may:

1. fit Champion-R2 on already exposed evidence only;
2. freeze Champion-R2 before C3 reserve access;
3. materialize C3 outcome-blind only after R2 is separately closed;
4. freeze exactly 500 eligible C3 events without opening outcomes.

This checkpoint itself performs **zero** model fits, **zero** network requests,
**zero** C3 materialization, and **zero** C3 outcome access.

## Frozen parent state

- Checkpoint-21A protocol fingerprint:
  `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- Checkpoint-21F-B closeout receipt commit:
  `05c9b7fca4e399d1f8047514f681691d579839f1`
- C2 result fingerprint:
  `ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62`
- C2 result closeout fingerprint:
  `5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf`
- Champion-R1 fingerprint:
  `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`

## Champion-R2 fit contract

The model specification is unchanged:

`kxbtcd_btc_distance_offset_logistic.v1`

Formula:

`logit(p) = logit_clip_0.001(q_market) + beta_distance * d_BTC`

Fit evidence:

- H1: 1,500 events / 36,314 rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows
- C1: 500 events / 14,887 rows
- C2: 500 events / 14,007 rows
- total: **4,000 events / 109,971 rows**

All R2 outcomes are already exposed. C3 rows/outcomes must remain zero.

No feature selection, candidate selection, momentum term, regularization change,
objective change, optimizer change, or hyperparameter search is permitted.

## C3 reserve contract

C3 begins exactly at strict queue index **4222**.

The Checkpoint-21A absolute boundary remains end-exclusive **4931**. It is not
reset after C2.

Therefore C3 may inspect at most:

`4931 - 4222 = 709`

candidate identities.

C3 target:

- exactly 500 eligible events;
- five chronological 100-event blocks;
- no arbitrary start index;
- progress reconstructed only from validated contiguous C3 chunks;
- outcomes remain sealed.

If 500 eligible events cannot be obtained before index 4931, C3 fails closed
rather than violating the protected 4,500-event untouched-tail floor.

## Checkpoint-21G-A safety state

- Champion-R2 fit: not performed
- C3 materialization: not performed
- C3 outcomes opened: 0
- network requests: 0
- execution/orders: disabled / 0

After 21G-A is safely closed and pushed, the next action is Champion-R2 fit
only. C3 must remain untouched until Champion-R2 is separately frozen and
safely closed.

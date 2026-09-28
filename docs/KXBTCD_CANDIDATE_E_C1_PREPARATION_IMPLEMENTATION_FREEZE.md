# KXBTCD Candidate-E C1 Preparation — Checkpoint 21B-A

**Status:** implementation/design freeze only. No Champion-R0 fit has been executed by this checkpoint, no C1 reserve event has been materialized, and no C1/C2/C3 outcome has been opened.

## Purpose

Checkpoint 21A decided the evidence architecture. Checkpoint 21B-A turns only the first step of that architecture into executable, testable code **before** touching the strict reserve.

The next evidence sequence is intentionally split:

1. **21B-A:** freeze implementation bytes only.
2. **21B-B:** after 21B-A is safely committed and pushed, fit and freeze the unchanged Distance champion on the already-exposed 3,000 H1+H2+H3 events. This is network-free.
3. **21B-C:** only after Champion-R0 is itself safely closed, materialize C1 outcome-blind from the strict tail and freeze its 500-event cohort.
4. **Later checkpoint:** freeze the C1 outcome evaluator before any C1 outcome is opened.

This separation means a C1 result cannot influence the code that decided which C1 events were selected or how the entering champion was fit.

## Champion-R0

Champion-R0 keeps exactly `kxbtcd_btc_distance_offset_logistic.v1`:

`logit(p) = logit_clip_0.001(q_market) + beta_distance * d_BTC`

The only authorized R0 operation is one deterministic refit of that already-selected one-parameter specification on all exposed H1+H2+H3 evidence:

- 3,000 events;
- 81,077 rows;
- no new candidate;
- no new feature;
- no hyperparameter search;
- no C1 row or outcome in the fit.

The R0 coefficient is therefore a parameter update using already-exposed evidence, not another model-selection experiment.

## C1 strict-tail allocation

The frozen untouched queue contains 9,431 identities. Checkpoint 19H-C canonically materialized queue indices `0..3199`, so the strict never-materialized tail starts at index `3200` with 6,231 candidate identities.

C1 selection is deterministic:

- begin at queue index 3200;
- evaluate candidates chronologically under the unchanged Coinbase-primary Candidate-E historical eligibility contract;
- accept the first 500 eligible events;
- stop materialization immediately after the 500th eligible event;
- assign those 500 events to B0-B4, exactly 100 events each;
- do not materialize C2 or C3 in this checkpoint.

There is deliberately **no arbitrary start-index CLI argument** on the C1 collector. Each run derives its next index from validated completed prior C1 chunks. This prevents skipping an inconvenient period or peeking farther into the reserve.

## Reserve runway

Checkpoint 21A requires at least 4,500 strict untouched candidate identities after all C1-C3 confirmation. With 6,231 strict-tail identities initially, the entire confirmation path may materialize at most 1,731 candidate identities.

Therefore the absolute queue end bound for the combined C1-C3 path is:

`3200 + 1731 = 4931` (exclusive).

Every C1 collection event checks this bound fail-closed. C1 itself does not reserve a fixed number of ineligible events; it simply walks chronologically until the 500th eligible event or until the hard runway would be violated.

## Why the collector stops inside a chunk

A normal fixed-size chunk could cross the 500th eligible event and accidentally materialize some C2 candidates. The C1 collector instead treats `--max-events` as an upper bound. If the 500th eligible event occurs earlier, the collector ends immediately on that event.

This preserves more untouched evidence and makes the C1/C2 boundary causal rather than convenient.

## Safety boundary

Checkpoint 21B-A and the later 21B-B preparation remain read-only:

- no C1 outcomes during 21B-A;
- no C1 outcomes during R0 fit or C1 pre-outcome materialization;
- no C2/C3 materialization during C1 preparation;
- no paper/mock broker;
- no demo orders;
- no real orders, cancellations, or transfers.

The later strategy and full live mock-execution architecture accepted in Checkpoint 21A remains downstream and separately gated.

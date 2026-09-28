# Checkpoint 19G — Candidate-E Historical Pre-Outcome Materialization Contract

## Purpose

Checkpoint 19G freezes how the exact Checkpoint-19F outcome-untouched KXBTCD queue is turned into Candidate-E feature rows **before any new Candidate-E label is opened**. It is an engineering/data-contract checkpoint, not a model-fit or performance checkpoint.

Frozen contract fingerprint:

`cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145`

## Facts inherited from prior checkpoints

- Checkpoint 19F froze 9,431 outcome-untouched modern-regime KXBTCD events after excluding 307 prior outcome-exposed events.
- Candidate E remains the two-model family frozen in 19E: distance-only or distance-plus-5m-momentum, both using raw Kalshi probability as a fixed logit offset.
- Historical BTC primary is Coinbase one-minute close; Kraken exact-minute PostTrade is the mandatory verifier.
- Historical construction is exact-minute and causal: no future interpolation, nearest-neighbor rescue, carry-forward, or source substitution.
- Candidate E uses six scheduled TTC targets: 55m, 50m, 45m, 40m, 35m, 30m, and five structural strike roles q10/q30/q50/q70/q90.

## New 19G clarifications frozen before large-scale collection

### Eligible anchor

An anchor is eligible when:

1. Coinbase and Kraken both provide the exact current historical minute required by the frozen schedule;
2. Coinbase and Kraken both provide the exact five-minute lookback minute;
3. current cross-source disagreement is at most 5 bp;
4. lookback cross-source disagreement is at most 5 bp; and
5. at least one of the five structural KXBTCD markets has a valid real two-sided YES quote at or before the scheduled anchor within the frozen 60-second staleness cap.

The contract deliberately does **not** require all five structural markets to have a valid quote at every anchor. That stronger rule was never frozen in 19F/19E and would discard events based on a new post-hoc coverage threshold. Only valid common rows are materialized. The already-frozen H1/H2/H3 block gates still require all five structural roles and all six TTC targets to be represented in each required score/evaluation block.

### Eligible event

An event is eligible if at least four of its six scheduled anchors are eligible. Ineligible events do not fill H1/H2/H3 and are replaced by later events from the same frozen untouched chronological queue.

### Reserve accounting

Canonical materialization may inspect at most the first 4,431 events of the frozen 9,431-event queue. This guarantees at least 5,000 later events remain outside Candidate-E canonical materialization. The final freezer counts every canonical queue event actually materialized, including extra events at the end of the last chunk.

## Unavoidable historical-market outcome fields

Kalshi historical market responses may include settlement/result fields even when the research task only needs rules, close time, market ticker, and strike metadata. Raw-first policy requires preserving the original source response unchanged.

19G therefore freezes a mechanical firewall:

- raw responses are archived unchanged;
- research code immediately projects each market object onto an explicit metadata allow-list;
- result/settlement fields cannot affect branch decisions, structural selection, derived rows, logs, or fingerprints;
- unit validation must show that flipping forbidden outcome-bearing fields while holding allowed metadata fixed leaves the projected metadata unchanged;
- operators must not manually inspect H1/H2/H3 result values in raw files;
- dedicated outcome attachment remains a later gated step.

This is a source-transport constraint, not permission to use outcomes.

## Chunked collection

Large historical collection uses bounded canonical chunks rather than one giant run. Each chunk:

1. takes an explicit contiguous zero-based slice of the frozen untouched queue;
2. has its own raw-first run manifest and runtime log;
3. validates the complete KXBTCD ladder and settlement semantics;
4. selects q10/q30/q50/q70/q90 structurally without outcomes or quote availability;
5. fetches one Kalshi candlestick window per selected strike;
6. reconstructs the exact Coinbase/Kraken current and 5m lookback state for each TTC target;
7. writes event, anchor, and common-row CSV artifacts;
8. records zero Candidate-E outcome accesses, zero fits, and zero orders.

Engineering-smoke chunks are written to a separate noncanonical directory and are never accepted by the final freezer.

## Final offline freeze

After enough completed canonical chunks exist, the offline freezer:

- verifies completed chunk manifests and their contract identity;
- requires an exact non-overlapping contiguous queue prefix beginning at index 0;
- selects the first 1,500 eligible events for H1, next 750 for H2, next 750 for H3;
- creates frozen chronological block maps;
- attaches stage/block IDs and event-equal row weights;
- validates required block coverage of all five strike roles and all six TTC targets;
- fingerprints the cohort map, common Candidate-E row universe, and exclusions;
- writes a freeze summary stating that outcomes remain unopened and Candidate E remains unfitted.

No H1 outcome may be opened until the Checkpoint-19H final pre-outcome freeze passes. H2/H3 remain sealed under the 19F sequential firewall.

## Failure modes

Hard failures stop the current chunk: unclear/wrong settlement regime, close-time mismatch, API/schema errors, duplicate/ambiguous identities, timestamp problems, raw-persistence errors, or fingerprint drift.

Outcome-blind eligibility exclusions may replace an event: fewer than five distinct structural markets, missing valid quote anchors, missing exact Coinbase/Kraken minutes, cross-source disagreement above 5 bp, or fewer than four eligible anchors.

## Authorization

Read-only historical collection and offline transformation only. Candidate-E fitting, new Candidate-E outcome access, paper execution, demo execution, order creation/cancellation, transfers, and real-money execution remain prohibited.

<!-- CHECKPOINT19H_SMOKE_VALIDATION_20260817 -->
## Implementation smoke evidence

A two-event noncanonical smoke was completed before canonical Checkpoint-19H collection.

Successful run:
`collect_kxbtcd_candidate_e_historical_materialization_chunk_20260817T082547653987Z_48b89ca0`

- queue range `[0,2)`
- events processed: 2
- eligible events: 2
- common Candidate-E rows: 30
- outcomes accessed: 0
- Candidate-E fits: 0
- orders: 0

The first smoke attempt identified an effective Windows path-length problem because the long collector run_id was repeated as both a smoke-directory component and a filename prefix. Smoke paths were shortened by removing the redundant directory component. Run identity and lineage remain unchanged, and canonical materialization semantics were not modified.

A dedicated regression test now protects this Windows path behavior.

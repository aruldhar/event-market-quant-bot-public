# KXBTCD Predexon Segment-Safe Replay Design

## Status

Checkpoint 21N-O repaired design freeze candidate. Read-only historical replay only.

## Purpose

Determine whether Predexon historical Kalshi order-book deltas can support
conservative short-horizon microstructure research without silently carrying
invalid book state across collector/source/session discontinuities.

This checkpoint does not establish strategy profitability, authorize execution,
or reopen protected Candidate-E forecast evidence.

## Evidence evolution

The original one-market audit established the paid-delta mapping and showed
682 exact adjacent snapshot transitions before a displayed sequence decrease.
The initial conservative implementation therefore treated every displayed
snapshot sequence decrease as a hard boundary.

A later frozen 20-contract sample across four already-purchased KXBTCD hourly
events disproved that heuristic as a universal boundary rule:

- 8,210 / 8,273 adjacent snapshot pairs reconciled exactly (99.2385%);
- verified-time rate across sampled snapshot spans was 88.4224%;
- the intentionally worst inspected contract had 4,376 / 4,397 exact pairs;
- all 585 observed `live_early -> websocket` sequence-decrease transitions on
  that worst contract reconciled exactly;
- the three same-source sequence decreases on that contract failed replay;
- one 33.255-minute unreconciled gap dominated the contract's excluded time.

Therefore sequence metadata is useful for diagnosis but is not authoritative
for replay continuity. Actual ordered book reconstruction is authoritative.

## Segment-safe replay contract v2

A historical replay segment is valid only when all of the following hold:

1. The segment begins from a trusted full order-book snapshot.
2. Paid delta rows are applied in `(timestamp, sequence)` order.
3. `side=yes` changes the YES bid at exact `price_dollars`.
4. `side=no` changes the equivalent YES ask at `1 - price_dollars`.
5. Paid `price_dollars` and `delta_fp` are exact fixed-point values. They are
   not repaired with floating tolerance; a delta that would create negative
   resting size fails closed.
6. Same-millisecond snapshot boundaries are handled only through legal ordered
   prefix/suffix cuts; deltas are never reordered.
7. Snapshot quantity comparison permits at most `1e-9` contracts solely for
   JSON snapshot serialization noise.
8. Displayed snapshot sequence decreases are diagnostic metadata only. They do
   not create a boundary when the actual book transition reconciles exactly.
9. Any adjacent full-snapshot pair that cannot be reconciled exactly is a hard
   segment boundary.
10. Book state is never carried across an unreconciled pair.
11. Research windows crossing an unreconciled pair are excluded rather than
    filled, repaired, interpolated, or inferred.
12. `PASS_SEGMENT_SAFE_REPLAY` means the fail-closed segmentation contract was
    applied safely. It does not imply that every segment has sufficient duration
    or density for a later strategy experiment.
13. Replay remains read-only.

## Failure modes

- Missing or malformed trusted seed snapshot -> no segment.
- Backward snapshot timestamp -> fail.
- Unexpected delta side -> fail.
- Paid delta producing negative resting size -> fail.
- Unreconciled adjacent snapshot pair -> terminate segment before the pair.
- Displayed sequence decrease with exact reconstruction -> retain interval and
  record the decrease as diagnostic metadata.
- Vendor/session semantics that cannot be reconciled deterministically -> do not
  claim continuity through that interval.

## Accepted exploratory source evidence

The already-purchased 2026-07-10 paid shard contains 623 KXBTCD contracts across
four hourly events. A free snapshot census found at least one snapshot for all
623 contracts. The frozen 20-contract stratified sample then established the
reconciliation evidence above without purchasing additional paid data.

These four events are exploratory/development evidence only. The 623 contracts
are not 623 independent events. Future fresh-event purchases, if any, must be
reserved for later evaluation after the strategy methodology is frozen.

## Next research boundary

After this repaired replay contract is implementation-tested and Checkpoint
21N-O is safely closed, the next checkpoint may design an exploratory
Candidate-E executable-edge / realizability baseline using only verified replay
windows from the already-purchased shard.

That future historical replay must explicitly model fees, spread, available
depth, latency, partial fills, missed fills, and uncertainty before making any
economic claim. No order placement, live paper broker, demo execution, or
real-money execution is authorized.

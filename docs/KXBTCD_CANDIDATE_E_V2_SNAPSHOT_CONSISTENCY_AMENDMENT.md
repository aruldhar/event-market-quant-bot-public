# Checkpoint 21N-Y-A4 — Bounded Snapshot Consistency Repair and Coverage Gate

## Problem and resulting behavior

The completed Y-A3 run reconstructed 47 tickers and generated 60 outcome-blind
Candidate-E V2 scenarios. Its remaining 748 failed snapshot pairs include two
source-consistency patterns: mixed-source snapshots ordered incorrectly within
the same millisecond, and isolated snapshots that conflict with the paid updates
and the snapshots around them. This amendment creates a separately recorded
snapshot view for strictly qualified cases. Original source files, Y-A3 caches,
strategy paths and all ancestor freezes remain unchanged.

This checkpoint implements the repair planner and an incremental coverage gate.
It does not implement a new execution-cache builder, rerun strategy scenarios,
open settlements, calculate strategy P&L, or change execution authorization.
A coverage gate PASS means the proposed changes passed the checks below. It does
not mean every gap is resolved or that the proposed view is an execution timeline.

## Parent and evidence bindings

Parent checkpoint: 35b778a4f68d7d221536358599683706019230d8.
Parent receipt/main: 1116a023cac865a9aeac13db041e710e4632395e.
Parent replay-precision fingerprint:
82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370.

Completed Y-A3 coverage SHA256:
5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab.
Completed Y-A3 outcome-blind path SHA256:
3b1bfadd61f003343d385fc1f62b6192ce5b53fda87d3f1977d84f604ebb4780.
All-ticker screening audit SHA256:
7b1265b2ffcc87841f7e193b89e34ddbd9b602ec8b150af13472952e4478ce6c.
All-ticker forensic report SHA256:
a9bfe9d389611b192a186024c1301563d71bdcd649a891401a223434c03bd188.

The Windows forensic run accounted for all 748 failures without a pair-replay
resource bound: 236 rejected all cuts for negative resting quantity; 512 had
executable replay with snapshot-level mismatches. Independently, 148 pair checks
were reproduced from portable raw extracts and 668 reported cut chains checked.
One of 17 portable windows omitted its oversized raw-row extract; the Windows
pair replay itself was completed. Local omission experiments supported 125
isolated-snapshot endpoint chains (250 original pairs), plus 15 ordering cases.
Those hypotheses were not automatically approved repairs. The rules below are
narrower, especially for long and non-strict timestamp contexts.

## Rule O — Same-millisecond ordering

- Consider a maximal consecutive equal-timestamp group only if an internal
  original Y-A3 pair failed. There must be 2–4 snapshots from multiple named sources.
- Preserve original relative order within each source. Do not compare numeric
  sequence values across sources as a universal ordering authority.
- Require two unchanged anchor snapshots on each side. The anchors' timestamps
  must strictly surround the group's timestamp and increase on each side.
- Require the complete context to span no more than 120 seconds.
- Enumerate every source-order-preserving permutation. Use the unchanged frozen
  paid-delta replay and zero comparison tolerance. Exactly one ordering must admit
  exactly one globally consistent cut chain across the local context.
- Retain every snapshot. The proposed view changes only its equal-time order.

## Rule Q — Isolated conflicting snapshot quarantine

- Consider exactly one snapshot whose two incident original Y-A3 pairs failed.
- Require a five-snapshot context, two snapshots on each side, with all five
  timestamps strictly increasing and a total span of at most 120 seconds.
- The two outer control pairs must both be verified in the original Y-A3 coverage.
- After excluding only the middle snapshot from the proposed view, the remaining
  four snapshots must connect through exactly one consistent exact cut chain,
  applying every paid update selected by those legitimate boundary cuts.
- Source names must be present but neither the source name nor a numeric sequence
  drop determines authority. Same-source conflicts can qualify on the same exact
  replay evidence; a source label alone cannot qualify any exclusion.
- Record the original index, source identity, affected pairs, surrounding anchors,
  accepted chain and required cuts. Preserve the raw snapshot and its file hash.

The two-minute limit retains the prior bounded review window as an explicit
repair-policy limit. It is not enlarged to absorb the 24 long-context endpoint
matches. Long contexts, chains with multiple bad snapshots, ties in the five-point
quarantine context, or ambiguous matches remain unresolved. An accepted quarantine
is a conditional data-quality decision, not proof of which upstream feed is true
or of unrecorded activity between the retained anchors.

## Combination and fail-closed behavior

Compute both rule families against the original normalized Y-A3 view. Do not
iterate, use an earlier repair to qualify another, or select rules by trade results.
Reject every otherwise-qualified proposal whose original context intersects another
proposal's context. Record both ids and retain the affected original gaps.

Apply accepted non-overlapping proposals as index mappings into immutable source
snapshots. Recheck each accepted local chain and every newly adjacent pair. Export
ordering-only, quarantine-only and combined views from the same accepted proposal
set. Every remaining original failure must be preserved by identity; the gate fails
if a failure disappears outside an accepted proposal. Preserve singleton segments
and the total recorded snapshot time span. Report duration and failure counts for
each variant without comparing financial results.

An exact match for each individual pair is insufficient: two neighboring pairs
must agree on how many paid updates were consumed at their common snapshot. The
coverage report therefore exports required local cut chains. A future cache builder
must preserve those constraints, validate its complete chronological state stream,
and test its output before the strategy can use the new view. The existing Y-A3
cache builder is not silently redirected to this amendment.

## Data and computation bounds

Snapshot quantities retain Y-A3's 0.01-contract grid and at most 1e-9 representation
residue. Paid quantities are not rounded; negative resting quantity is not clamped.
All book comparisons use zero tolerance. Paid rows retain timestamp, sequence and
original file-row order for ties. No paid updates are deduplicated or reordered.

Per pair: at most 200,000 paid rows, 10,000 legal cut combinations and 2,000,000
rows-times-cuts of diagnostic work. A bound rejects the proposal and is reported;
it does not relax the comparison or suppress an unresolved gap.

The runner streams only six order-book columns into a disposable SQLite index
outside the repository. It verifies all 47 ticker identities, source hashes,
cache seals and coverage bindings; it loads one ticker's snapshots at a time.
It replays the changed neighborhoods and their controls. It reuses unchanged
Y-A3 pair classifications from the pinned coverage instead of rebuilding every
book state. Sources and caches are rehashed before reporting completion.

## Preserved unresolved evidence

The cluster on KXBTCD-26JUL1015-T63899.99 includes 239 failed pairs with no matching
paid updates in the available shard while snapshots changed. This is a coverage
absence in that input, not evidence that no provider could supply the missing data.
The late cluster on KXBTCD-26JUL1014-T63899.99 contains repeated material quantity
inconsistencies that the tested omissions did not resolve. Neither cluster is
blanket-quarantined. Other unsupported first-pair and same-time failures also remain.

## Validation and next gate

Regression fixtures contain bounded raw source examples for both ordering cases,
the earlier isolated conflict, all three later conflicts, and both unresolved
clusters. Synthetic tests cover inconsistent cuts, ambiguity, overlap, long windows,
multiple bad snapshots, resource bounds, singleton segments and freeze tampering.
These tests and the coverage gate do not establish generalization beyond July 10.

After the canonical safe closeout, run the coverage-only command documented in
AI_HANDOFF and upload its report plus terminal SHA256. Review the combined result
before implementing a separately validated new cache builder. Keep all 60 frozen
strategy scenarios, fees, entry/reentry/exit rules and the original gap fallback
policy unchanged. Settlement-dependent P&L remains closed pending validated paths
and the appropriate evaluator gate.

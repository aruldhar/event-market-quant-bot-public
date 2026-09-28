# Checkpoint 21N-Y-A3 — Snapshot Quantity Precision Repair

Status: implementation prepared and locally tested; canonical Windows validation,
safe checkpoint closeout, full-data cache rebuild and revised strategy paths pending.

## Verified baseline and evidence

GitHub main at review: d642ca401695cd03da2bd827998d2bead5b1f31f, the receipt-only
commit for e032985af6d1ce33a9a54e624359be34447ecc87 (21N-Y-A2). Receipt paths
match that implementation commit; its full Windows suite was 1,274 tests plus
22 subtests. The attached August 3 project documents were stale; current GitHub
files were read and used for this additive update. User worktree synchronization
is checked by the installer rather than assumed.

User-reported subsequent Y-B completion: 47 ticker caches; 60 policy scenarios;
original outcome-blind path SHA256
21dd58066b040f8bc897815f722cad9bb90b0ff6b9a6d18d6e9416279c85bc9f.
This original path is retained as an implementation-affected mechanics run.
It is not a completed economic evaluation.

Uploaded diagnostic SHA256 verified locally:
47caf2f93c736538db9a896a469f6a25fcdb247d2e67e89cf538675e4c8eeac5.
Its replay-module identities match the frozen parent. The embedded four snapshots
and nearby paid rows reproduce the 25ms failure at 16:06:11.887–16:06:11.912 UTC
for KXBTCD-26JUL1013-T64099.99. A snapshot contains 185.26999999999998;
subsequent exact updates leave 24.99999999999998, then subtracting 25.00 gives
-2E-14 and the exact negative-quantity guard fires. Thus the residue is already
present in the snapshot input; this diagnostic does not establish which upstream
component originally introduced it.

Correction to prior chat wording: normalized valid_combinations=9 means all nine
cut combinations execute without a negative quantity. Only cut (1,1) matches
both endpoint books exactly. Both neighboring control pairs already reconcile.
The new regression independently verifies these facts with zero tolerance.

## Accepted repair and rationale

Y-A1 normalized quantities after verified replay. This repair provides a separate
snapshot view before replay. It changes reconstruction semantics explicitly and
therefore uses a new amendment fingerprint and new artifacts. Frozen original
modules, old caches, raw sources and old results remain byte-for-byte unchanged.

For each snapshot size q, compute the nearest multiple q* of 0.01. Accept only
finite nonnegative q with abs(q-q*) <= 0.000000001. Use exact Decimal q* thereafter.
This tolerance comes from the existing Y-A1 grid audit (all 763,392 off-grid sizes
within 1e-9; all 5,644,964 paid deltas exactly on grid), not financial performance.
Reject materially off-grid sizes, negative sizes including tiny negatives,
nonfinite values, duplicate price levels, and unsupported quantity magnitudes
>=1e20 contracts. Remove normalized zero levels because they represent no resting
depth. Prices, timestamps, sequence order and source records are retained.

Paid deltas must be finite and exactly on 0.01; they are never rounded. The original
exact apply_delta still rejects every negative reconstructed quantity. Reconcile
normalized snapshots with the original legal millisecond-cut search, and independently
require identical results under zero comparison tolerance. A real one-cent mismatch,
missing update or absent end-of-evidence interval remains unverified. There is no
interpolation, no resumption across a genuine gap, and no new gap-duration threshold.

Inputs: preserved snapshots, paid deltas, original replay diagnostics and frozen
source/model/policy identities. Outputs: separately sealed SQLite caches, per-ticker
before/after replay audits, an outcome-blind coverage report, and (only with explicit
--simulate) all 60 revised outcome-blind policy paths. Any invalid quantity, original
baseline mismatch, hash change, incomplete cache or strict-audit disagreement stops
the run. No settlement reader or P&L evaluator is added.

The original disk builder is reused on normalized snapshot copies. Audits run for
one ticker at a time and history is still staged in SQLite. The extra snapshot view
and pair audits consume additional per-ticker memory/time, not an all-ticker timeline
copy; whole-process peak RAM is not guaranteed. Caches require a fresh build because
old segment boundaries were derived before normalization. New snapshots can merge
previously interrupted segments, and normalization may remove residue-only state
changes; these are disclosed consequences of the reconstruction correction.

## Artifacts and workflow

New cache root: data/analysis/predexon_credit_efficiency/v2_y_a3_replay_precision_cache.
Each cache includes normalization counts/examples, original/revised bounds,
changed pair results and all remaining unreconciled pairs, sealed with raw-source,
Y-A1, Y-A2 and Y-A3 identities. Original replay bounds are reproduced and checked
before new bounds are accepted. An old cache cannot pass the new audit check.

New runner: materialize_kxbtcd_candidate_e_v2_paths_replay_precision.py.
Default prepares the full deterministic dynamic ticker union and writes
coverage_full.json under the new cache root. --max-tickers N is a preparation-only
resource check. --simulate requires the complete union and always runs the same
five thresholds, three latencies and four events. The original output digest is
checked before source processing. Nonidentical output overwrites are rejected.

New path: data/analysis/predexon_credit_efficiency/july10_candidate_e_v2_outcome_blind_paths_replay_precision.json.
It records the new amendment, the coverage digest and the original path digest.
Candidate E, ATM +/-5, entry rules, size, fees, latency, liquidation/reentry, matched
hold and fresh validation gates remain the frozen parents. The disk-policy body
continues to pass the existing AST identity guard.

Next local action: install this additive ZIP and run scripts/validate_checkpoint21n_y_a3.ps1.
After canonical validation, close the checkpoint through the existing safe closeout
script (including the full Windows suite). Only then prepare new caches and inspect
the coverage report, including the larger gaps, before --simulate and before any
separate settlement/P&L evaluator work. A successful 25ms regression does not prove
the later roughly 33-minute interval is repairable.

## Validation and limitations

Assistant environment: Python 3.12/Linux. Focused regression suite includes the
actual diagnostic snapshot/update fixture, strict cut (1,1), unchanged adjacent
controls, exact-grid path equivalence, same-millisecond snapshots, genuine gaps,
end-of-evidence, cent mismatches, tolerance boundaries, invalid/negative quantities,
paid-grid strictness, zero removal, duplicate levels, cache sealing/reuse,
changed identities, interruption/resume, output firewall, partial-scoring prohibition,
frozen parent checks and inherited disk/IOC/policy equivalence.

Canonical full July 10 files and Windows runtime are on the user's PC. No all-47
rebuild, revised Candidate-E scoring or P&L was performed here. The n=4 July 10
sample remains development/mechanics evidence; it cannot establish strategy
profitability or fresh-domain generalization. No network market-data requests,
purchases, orders, demo execution or paper broker are introduced.

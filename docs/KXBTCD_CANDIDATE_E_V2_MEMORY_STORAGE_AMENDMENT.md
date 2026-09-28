# Checkpoint 21N-Y-A2 — V2 memory/storage amendment

## Problem and scope

The Y-A1-amended Y-B materializer kept all selected paid rows, all raw replay
timelines, and a growing normalized copy alive simultaneously. Its timestamp
validator then failed to allocate a set, raising MemoryError. The user later
interrupted the command. This attempt failed before its scenario loop; the
earlier Y-B attempt's nonstructural scoring exposure remains on record.

This amendment changes storage and traversal only. It does not change the
strategy, outcomes policy, source evidence, quantity quantum/tolerance, fees,
latencies, or interpretation of four-event July 10 evidence. The original Y-A
and Y-A1 files and their fingerprints remain frozen and validated.

## Exact equivalence contract

1. Load paid deltas and snapshots for one deterministic ticker at a time.
2. Call the frozen audit/reconciliation, snapshot conversion, delta application,
   legal millisecond boundary-cut, and book-comparison functions unchanged.
3. Stage raw states in SQLite using timestamp as primary key and replacement
   semantics. This is the original dictionary's final-write-wins rule, including
   authoritative snapshots and multiple boundary observations at one millisecond.
4. Read timestamps in ascending order, validate bounds/order, and compress
   adjacent equal RAW books exactly as Y-A does.
5. Apply the unchanged Y-A1 quantity canonicalizer to each retained raw state.
   Do not compress a second time after normalization. Normalization may make
   adjacent books equal; their original retained timestamps remain available.
6. Store lossless Decimal strings, never floats or pickle. Disk lookup returns
   the final state at or before a requested timestamp, with the requested
   timestamp attached, exactly as the original right-continuous lookup does.
7. Yield full-depth changes for liquidation, suppressing adjacent equal
   canonical books exactly as the original state_changes method does. A
   generator replaces an eagerly built tuple; the frozen consumer only iterates.
8. The disk clock reads indexed top signatures using the original strict minute
   interval bounds, availability transitions, causal BTC windows, and ordering.
9. The adapted simulate_policy function body is AST-identical to frozen Y-A.
   All economic/decision helper functions are aliases of the original functions;
   only decision_clock resolves to the equivalent disk implementation.

The new disk builder does not instantiate a second all-history
VerifiedSegmentTimeline or allocate sorted(set(timestamps)). It validates
strictly increasing timestamps during the ordered disk read.

## Storage, failure, and resume

Cache directory:
`data/analysis/predexon_credit_efficiency/v2_y_a2_ticker_cache/`

Each ticker cache is sealed only after reconstruction, normalization, and
comparison to the existing frozen per-ticker replay segment boundaries. Its
seal records the database SHA-256, raw-snapshot hash, replay-artifact hash,
paid-shard hash, and both amendment identities. Source files are never changed.
Changing a source or corrupting cache bytes stops the run.

The cache is a derived convenience, not new market evidence. File bytes may
differ between SQLite versions; semantic equivalence and per-cache integrity
are distinct checks. Resume verifies the existing cache's exact bytes and
identities, rather than assuming a cache is valid because a filename exists.

Ctrl+C preserves completed sealed tickers. Normal exception cleanup removes
only the current temporary build and its journal. A process kill or failed
rename can leave a temporary file, orphan cache, or stale RUNNING.lock; inspect
the stopped process and preserve/rename the affected item before rebuilding.
The runner never accepts an orphan as completed. It never removes raw evidence.

SQLite uses a 1 MiB page-cache target per connection, disk temporary storage,
and no memory mapping. Reconstructed book history is kept on disk. Per-ticker
source rows and the inherited audit's slices still reside in Python, so this
is not a fixed process-RAM cap. Disk space and runtime depend on actual data;
disk I/O can be slower than an in-memory run with ample RAM. Preparation emits
stage/count messages and a 15-second heartbeat.

Final result:
`data/analysis/predexon_credit_efficiency/july10_candidate_e_v2_outcome_blind_paths_memory_safe.json`

The result preserves the legacy schema, policy result structure, full dynamic
ticker union, and all 60 scenarios. It adds a memory amendment fingerprint and
uses a separate filename. Writing is atomic and rejects non-identical overwrite.
An interrupted preparation or simulation never claims a completed final result.

## Validation and run sequence

The ZIP includes a source/hash freeze validator and synthetic tests for replay
equivalence, normalization, duplicate millisecond boundaries, hard source gaps,
right-continuous lookup, clock equivalence, YES/NO fills, partial/missed fills,
liquidation, re-entry, cache corruption, interrupted builds, cache reuse, and
output protection. The policy-body identity check runs in the freeze validator.
New-file hashes canonicalize CRLF to LF so the repository's Windows PowerShell
checkout rule is supported. Parent source hashes retain their existing exact
byte semantics.

The full real July 10 dataset is available only in the user's canonical Windows
repository. Synthetic tests do not establish actual dataset completion or a
peak-RAM guarantee. Check the canonical test output before closeout.

From the repository root:

```powershell
.\scripts\validate_checkpoint21n_y_a2.ps1
```

That script validates and tests the repair, then appends the permanent records.
It does not reconstruct July 10 books or score Candidate E. Safe closeout remains
required before real-data preparation:

```powershell
$newFiles = (Get-Content .\configs\kxbtcd_candidate_e_v2_memory_amendment.json -Raw | ConvertFrom-Json).frozen_files.PSObject.Properties.Name
$closeoutPaths = @($newFiles) + @(
  'configs/kxbtcd_candidate_e_v2_memory_amendment.json',
  'src/kxbtcd_candidate_e_v2_memory_amendment_freeze.py',
  'docs/PROJECT_STATE.md','docs/AI_HANDOFF.md','docs/DECISIONS.md',
  'docs/EXPERIMENT_LOG.md','docs/BACKLOG.md'
)
.\scripts\close_checkpoint.ps1 -Paths $closeoutPaths
```

Commit message: `Checkpoint 21N-Y-A2 — V2 Memory and Storage Amendment`

After clean closeout, first run just one deterministic ticker:

```powershell
.\.venv\Scripts\python.exe -u .\materialize_kxbtcd_candidate_e_v2_paths_memory_safe.py --max-tickers 1
```

Review that preparation's output/resource behavior before preparing all tickers:

```powershell
.\.venv\Scripts\python.exe -u .\materialize_kxbtcd_candidate_e_v2_paths_memory_safe.py
```

Only after preparation succeeds, explicitly run the policies:

```powershell
.\.venv\Scripts\python.exe -u .\materialize_kxbtcd_candidate_e_v2_paths_memory_safe.py --simulate
```

All modes remain offline and outcome-blind. Default preparation never scores.
`--max-tickers` cannot be combined with `--simulate`. Existing sealed ticker
caches are reused after exact checks. Inspect the final 60-scenario artifact
before any separately authorized outcome/P&L checkpoint.

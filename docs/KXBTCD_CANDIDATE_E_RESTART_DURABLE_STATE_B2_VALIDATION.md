# Candidate-E Z-E-B2 Identity and Raw-Reference Reconciliation Validation

<!-- CHECKPOINT21N_Z_E_B2_RECONCILIATION_20260904 -->

## Status

Checkpoint 21N-Z-E-B2 implements and validates the second offline slice of the
frozen restart/durable-state contract.

Parent Z-E-B1 receipt:

`f26221ce28c567d1664aedeb33b8e3ab9e9775e3`

Frozen restart-design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

## Implemented scope

B2 adds only offline reconciliation behavior:

- synthetic validation arm-manifest creation;
- validation arm-manifest / SQLite cohort identity reconciliation;
- exact arm Git-commit matching;
- create-exclusive restart-session raw segments;
- `runtime_session_id`;
- `raw_segment_id`;
- one-based `raw_record_index`;
- per-record payload and line hashes;
- exact decision -> raw-record references;
- atomic synthetic decision + source-watermark commit;
- offline raw-segment auditing;
- pending decision reconciliation;
- `VERIFIED` classification when referenced raw evidence exists exactly;
- `RAW_EVIDENCE_GAP` classification when referenced evidence is missing or
  crash-damaged;
- preservation of partial trailing raw bytes without truncation or rewrite.

## Explicitly not implemented

B2 does not:

- create or write the canonical prospective data path;
- arm the real 168-hour prospective cohort;
- perform Linux parent-directory fsync for a real arm manifest;
- connect Coinbase;
- connect Kalshi;
- execute the Candidate-E model;
- emit a live signal;
- create paper/demo/real orders;
- create fills or positions.

The Linux parent-directory fsync requirement remains frozen for later
production-host integration. The Windows B2 manifest helper is validation-only.

## Focused validator

Observed result:

```text
CANDIDATE-E Z-E-B2 RECONCILIATION: PASS
Synthetic arm/SQLite identity: PASS
Exact arm Git identity: PASS
Raw session identity: PASS
Raw segment create-exclusive: YES
Raw reference reconciliation: VERIFIED
Partial-tail policy: PRESERVE / NEVER TRUNCATE
Backfill allowed: NO
Canonical prospective paths: REFUSED
168-hour cohort: NOT ARMED
Coinbase: NOT CONNECTED
Kalshi: NOT CONNECTED
Signals: 0
Orders: 0 | Production writes: 0
```

Focused tests:

```text
14 passed in 1.26s
```

Compilation:

PASS.

`git diff --check`:

PASS.

## Crash semantics validated

### Raw persisted before decision commit

If a crash leaves valid raw evidence but no committed decision, the raw record
remains orphan audit evidence only.

B2 does not synthesize a decision afterward.

### Decision committed but final referenced raw record unavailable

If SQLite contains a pending decision whose referenced raw record is absent
from the post-crash raw segment, the decision becomes:

`RAW_EVIDENCE_GAP`

It is not reconstructed, replaced, or silently marked valid.

### Partial trailing raw bytes

A segment may contain complete newline-terminated JSON records followed by
partial trailing bytes after a crash.

B2:

1. verifies the complete records;
2. records that trailing bytes exist;
3. hashes the trailing bytes;
4. leaves the file byte-for-byte unchanged.

The damaged tail is never silently truncated.

## Identity semantics validated

A synthetic validation arm manifest must agree exactly with SQLite on:

- cohort ID;
- arm time;
- exact fixed end time;
- exact 168-hour duration;
- arm Git commit;
- manifest SHA-256;
- restart-design fingerprint;
- architecture fingerprint;
- Candidate-E fingerprint;
- prospective-week SHA;
- strategy ID;
- primary threshold;
- disabled execution mode.

The current Git commit must equal the arm Git commit exactly.

Mismatch fails closed.

## Acceptance interpretation

B2 validates offline arm-identity and raw-evidence reconciliation mechanics.

Together B1+B2 now establish:

- persistent runtime-session lifecycle;
- conservative clean/unclean downtime accounting;
- exact noncanonical arm identity;
- session-scoped raw segments;
- exact decision/raw references;
- fail-closed crash reconciliation;
- explicit no-backfill semantics.

B2 still does not validate the complete startup gate, clock gate, Coinbase gate,
Kalshi gate, within-session source-loss recovery, or long-running live restart
behavior.

No profitability conclusion is authorized.

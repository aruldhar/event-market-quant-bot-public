# Candidate-E Z-E-B1 SQLite Durable-State Core Validation

<!-- CHECKPOINT21N_Z_E_B1_SQLITE_CORE_20260904 -->

## Status

Checkpoint 21N-Z-E-B1 implements and validates the first offline slice of the
frozen restart/durable-state contract.

Parent Z-E-A receipt:

`ca539b12de88980ada4ae8e8b0f0ed574017b29f`

Frozen restart design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

## Implemented scope

B1 implements only:

- noncanonical validation SQLite databases;
- the frozen seven-table schema;
- `WAL` journal mode;
- `synchronous=FULL`;
- foreign keys enabled;
- 5-second-heartbeat-compatible session primitives;
- runtime session creation;
- same-boot and changed-boot session separation;
- within-session UTC/monotonic non-regression;
- clean shutdown recording;
- prior `RUNNING` session detection;
- transition of a prior crashed session to `UNCLEAN_DETECTED`;
- conservative process-discontinuity gap creation from the last durable
  heartbeat;
- clean-stop discontinuity gap creation;
- database-level prohibition of canonical backfill.

## Explicitly not implemented

B1 does not:

- create the canonical prospective database;
- arm the 168-hour cohort;
- connect Coinbase;
- connect Kalshi;
- evaluate Candidate E;
- emit live signals;
- create paper/demo/real orders;
- create fills or positions.

## Focused offline validator

Observed result:

```text
CANDIDATE-E Z-E-B1 SQLITE DURABLE CORE: PASS
SQLite journal: wal
SQLite synchronous numeric: 2 (FULL)
Sessions: 3
Clean discontinuity gaps: 1
Unclean discontinuity gaps: 1
Cross-session monotonic reset accepted: YES
Canonical prospective DB: NOT CREATED
168-hour cohort: NOT ARMED
Coinbase: NOT CONNECTED
Kalshi: NOT CONNECTED
Signals: 0
Orders: 0 | Production writes: 0
```

Focused tests:

```text
17 passed in 0.64s
```

Compilation:

PASS.

`git diff --check`:

PASS.

## Acceptance interpretation

B1 establishes the offline persistence/session-lifecycle foundation only.

It proves that:

1. SQLite is configured with the frozen durability pragmas.
2. each process gets a distinct runtime session;
3. monotonic clocks may reset between sessions without being compared across
   sessions;
4. monotonic/UTC time may not regress inside one session;
5. clean shutdowns are durable;
6. an unclean prior session is conservatively detected by the successor;
7. the unclean observation gap begins at the last durable heartbeat rather than
   pretending the exact crash instant is known;
8. canonical backfill remains forbidden.

This does not validate Coinbase/Kalshi restart gates, raw-reference crash
reconciliation, the full 17-case Z-E-B matrix, or prospective profitability.

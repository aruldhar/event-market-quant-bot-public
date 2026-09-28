# Candidate-E Z-E-B3 Restart Gate State Machine Validation

<!-- CHECKPOINT21N_Z_E_B3_RESTART_GATE_20260904 -->

## Status

Checkpoint 21N-Z-E-B3 implements and validates the third offline slice of the
frozen restart/durable-state contract.

Parent Z-E-B2 receipt:

`b3f54c89b3ab3f8794e4b9e2458b5538e4ab6477`

Frozen restart-design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

## Implemented scope

B3 adds only the offline restart-readiness state machine and clock gate:

- frozen state set:
  - `STARTUP_DISABLED`
  - `BLOCKED_IDENTITY`
  - `BLOCKED_COHORT`
  - `BLOCKED_DURABILITY`
  - `BLOCKED_CLOCK`
  - `BLOCKED_COINBASE`
  - `BLOCKED_KALSHI`
  - `BLOCKED_STRATEGY_RECONCILIATION`
  - `READY_READ_ONLY`
  - `COHORT_ENDED`
  - `FATAL`
- deterministic fail-closed gate precedence;
- unknown clock health -> `BLOCKED_CLOCK`;
- absolute clock offset `<= 250 ms` -> clock gate pass;
- absolute clock offset `> 250 ms` -> `BLOCKED_CLOCK`;
- every frozen ready requirement must pass before `READY_READ_ONLY`;
- execution mode not disabled -> `FATAL`;
- fixed cohort end -> `COHORT_ENDED`;
- runtime transition events persisted in SQLite;
- transition from `READY_READ_ONLY` to a blocked state immediately removes
  read-only signal eligibility;
- ready-gate regression opens a `PROSPECTIVE_OBSERVATION_GAP`;
- gap backfill remains prohibited;
- recovery requires a fresh full gate reevaluation;
- each return to `READY_READ_ONLY` increments readiness generation;
- no prior signal is reusable after a gate loss.

## Explicitly not implemented

B3 does not:

- connect Coinbase;
- connect Kalshi;
- measure production chrony health;
- compute Candidate-E probabilities;
- compute or persist Candidate-E signals;
- create the canonical prospective database;
- arm the 168-hour cohort;
- create paper/demo/real orders;
- create fills or positions.

Coinbase and Kalshi gate inputs are synthetic/offline in B3.

## Focused validator

Observed result:

```text
CANDIDATE-E Z-E-B3 RESTART GATE STATE MACHINE: PASS
Frozen state set: IMPLEMENTED
Startup default: STARTUP_DISABLED
Startup unhealthy clock: BLOCKED_CLOCK
Clock max absolute offset: 250 ms
250 ms boundary: PASS
Ready requires all frozen gates: YES
Ready gate regression disables eligibility: YES
Regression observation gap: RECORDED
Fresh full reevaluation after recovery: REQUIRED
Prior signal reusable: NO
Canonical backfill: NO
Canonical prospective DB: NOT CREATED
168-hour cohort: NOT ARMED
Coinbase: NOT CONNECTED
Kalshi: NOT CONNECTED
Candidate-E signal computation: NOT RUN
Orders: 0 | Production writes: 0
```

Focused tests:

```text
18 passed in 1.10s
```

Compilation:

PASS.

`git diff --check`:

PASS.

## Clock semantics validated

The B3 clock gate implements the frozen rule exactly:

- unknown / unavailable offset -> no signal;
- `abs(offset) <= 250 ms` -> clock gate may pass;
- `abs(offset) > 250 ms` -> no signal.

The exact `250 ms` boundary passes.

This is a gate contract only. B3 does not claim that the user's Windows clock
or a future Linux host currently satisfies the production clock requirement.

## Gate-regression semantics validated

If the runtime reaches `READY_READ_ONLY` and any required gate later fails:

1. signal eligibility becomes false immediately;
2. the prior signal cannot be reused;
3. a no-backfill `PROSPECTIVE_OBSERVATION_GAP` opens;
4. the runtime moves to the appropriate blocked state;
5. recovery requires a fresh evaluation of all current gates;
6. a later fresh `READY_READ_ONLY` state is a new readiness generation.

No old signal survives the gate loss.

## Acceptance interpretation

B1+B2+B3 now establish the offline restart foundation:

- durable process/session lifecycle;
- clean/unclean shutdown accounting;
- exact validation arm identity;
- exact raw evidence references;
- fail-closed crash evidence reconciliation;
- frozen restart state machine;
- frozen 250 ms clock gate;
- immediate readiness revocation on gate regression;
- explicit no-backfill recovery semantics.

The next unresolved engineering work is to feed **authoritative current
Coinbase/Kalshi readiness** into these already-frozen gates and validate the
remaining crash/restart cases. Production Linux chrony integration also remains
unvalidated.

No profitability conclusion is authorized.

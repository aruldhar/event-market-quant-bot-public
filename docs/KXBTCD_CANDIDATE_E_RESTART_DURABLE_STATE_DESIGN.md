# Candidate-E Restart-State and Durable-State Reconciliation Design

<!-- CHECKPOINT21N_Z_E_A_RESTART_DURABLE_DESIGN_20260904 -->

## Checkpoint 21N-Z-E-A

Design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

This checkpoint is design-only. It adds no restart runtime, no SQLite runtime,
no prospective cohort arm, and no order path.

### Frozen rules

- every process begins signal-disabled;
- every process receives a new runtime session ID;
- production Linux records `/proc/sys/kernel/random/boot_id`;
- current Coinbase/Kalshi/clock/signal state is rebuilt, never restored;
- old monotonic timestamps never establish new-session freshness;
- exact arm Git commit is required on restart;
- SQLite uses WAL + `synchronous=FULL`;
- the 168-hour prospective clock never pauses or extends;
- downtime is `PROSPECTIVE_OBSERVATION_GAP`;
- missed decisions/events are never backfilled or replaced;
- every restarted process opens new raw segments;
- crash-damaged raw evidence is preserved and classified, not silently rewritten;
- `READY_READ_ONLY` requires every frozen restart gate;
- current phase persists no order/fill/position state.

### Persistence

Durable audit/cohort/session/decision/gap information may survive restart.

Live source state does not survive restart. Coinbase builder state, heartbeat
freshness, continuity, Kalshi books, subscription SID, sequence-ready state,
ATM window, signal, and clock-health result must all be rebuilt.

### Cohort continuity

Process recovery is allowed inside the same already-armed cohort, but the cohort
itself is never re-armed. Its end remains exactly `arm_time + 168 hours`.

No downtime replacement, cohort extension, missed-event replacement, or
historical replay may be represented as live prospective evidence.

### Z-E-B validation

Z-E-B must implement this exact design and pass the 17 crash/restart cases
frozen in the JSON contract. Passing Z-E-B validates restart engineering only;
it does not establish profitability or authorize execution.

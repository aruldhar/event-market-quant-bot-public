# Checkpoint 21N-Z-E-B5-R4-A — Live Whole-Process Restart Design

## Status

Design freeze only. No live probe is run by this checkpoint.

Parent B5-R3 closeout receipt:

`dff89795c42e1ac3e7c22f065d84bf6b281bb047`

Design fingerprint:

`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`

## Why this test exists

B5-R2 proved live connection-generation rollover inside one process.
B5-R3 proved process-restart durability/reconciliation offline.

B5-R4 combines those two ideas across **two actual OS processes**.

The goal is to prove that after a real process crash, a successor process cannot
inherit readiness from the old process. It must rebuild fresh Coinbase and
Kalshi state before returning to `READY_READ_ONLY`.

## Exact bounded process sequence

### Process 1

1. Create/open a noncanonical validation durable-state store.
2. Create runtime session 1.
3. Connect to live Coinbase read-only market data.
4. Connect to authenticated Kalshi read-only order-book data.
5. Rebuild current source readiness from those fresh connections.
6. Reach `READY_READ_ONLY`.
7. Persist only validation/audit evidence and a ready marker.
8. Stay alive.

### Induced crash

The parent validation supervisor terminates process 1 **without** calling the
clean-shutdown path.

This is deliberate validation-only fault injection.

### Process 2

1. Open the same noncanonical validation durable-state store.
2. Create runtime session 2.
3. Detect session 1 as `UNCLEAN_DETECTED`.
4. Begin signal-disabled and not ready.
5. Reconcile pending raw durability evidence.
6. Prove neutral strategy state and `prior_signal_reusable=false`.
7. Establish brand-new Coinbase and Kalshi connections under session 2.
8. Rebuild current completed-minute / full-ladder / liveness state.
9. Reach `READY_READ_ONLY` only after all fresh gates pass.

## Required PASS evidence

The probe must prove all of the following:

- OS process IDs differ.
- Runtime session IDs differ.
- Process 1 is classified `UNCLEAN_DETECTED`.
- The successor starts blocked/not-ready before fresh sources.
- Coinbase state belongs to runtime session 2.
- Kalshi discovery/cache/liveness state belongs to runtime session 2.
- A fresh exact Coinbase completed minute is required.
- A fresh exact Kalshi full ladder plus current Pong is required.
- Prior signal reuse remains false.
- Process discontinuity is recorded with canonical backfill disabled.
- Execution mode remains disabled.
- Raw-artifact credential marker scan finds zero high-confidence secret markers.
- Orders remain zero.
- Production writes remain zero.

Any missing proof is a FAIL, not a warning.

## What this checkpoint does NOT claim

B5-R4 does **not** cover every operational category needed for the future
micro-production run.

It does not validate:

- host reboot;
- Linux production `boot_id` + chrony deployment;
- long-duration/soak stability;
- order submission;
- duplicate-order/idempotency handling;
- fill/cancel/position/cash reconciliation;
- kill-switch behavior under live order flow;
- partial/missed real fills;
- production write-endpoint failures.

Those remain separate blocking categories before the `$0.01` real-money run.

## Operational-safety completion rule

No single test is allowed to be described as proving every imaginable
operational failure.

Before micro-production authorization, every **known/predeclared** operational
category must either:

1. have explicit passing evidence, or
2. remain an explicit blocking unresolved item.

This prevents future chats from treating one successful restart test as a
blanket operational-safety certificate.

## Safety boundary

- current authorization: read-only;
- default invocation: zero network;
- live mode requires an explicit flag;
- canonical prospective database: not created;
- 168-hour read-only precursor: not armed;
- Candidate-E signals: 0;
- orders: 0;
- production writes: 0.

The long-term target remains the separately gated one-contract / `$0.01`
micro-production validation. This design does not authorize it.

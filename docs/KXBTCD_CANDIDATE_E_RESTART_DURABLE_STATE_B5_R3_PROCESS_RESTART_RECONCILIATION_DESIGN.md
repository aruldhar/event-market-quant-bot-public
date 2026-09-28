# Candidate-E Restart Durable State B5-R3-A — Process Restart and Strategy Reconciliation Design

## Purpose

Freeze the next restart slice before implementation.

Parent B5-R2 receipt:

`b7e034a6fdce10d42fca83e5d7e5ce182412e9fe`

Frozen parent identities:

- restart design: `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`
- production runtime architecture: `3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`
- B5-R3-A design fingerprint: `0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea`

## Key design decision

B5-R3 **does not add a persisted strategy-state table**.

That would conflict with the already-frozen read-only restart contract. Current
ATM window, Candidate-E probability, and current signal selection are live
derived state and must be rebuilt from fresh authoritative sources after every
process restart. Prior decisions remain durable audit evidence only. No fills,
positions, orders, cash state, or actionable prior signal are persisted in the
current phase.

## Gate separation

### Durability gate

The durability gate proves that the persisted record is safe to continue from:

1. SQLite integrity passes.
2. The prior process is classified as CLEAN or UNCLEAN_DETECTED.
3. Every `PENDING_RAW_DURABILITY` decision is reconciled.
4. Complete raw references become `VERIFIED`.
5. Missing/damaged references become `RAW_EVIDENCE_GAP`.
6. No pending decision remains.
7. A raw-evidence gap is preserved and excluded; it is never reconstructed or
   backfilled.

A previously reconciled `RAW_EVIDENCE_GAP` does **not** permanently poison a
new process. The frozen failure policy explicitly allows fresh recovery after
the affected old decision is classified and excluded.

### Strategy reconciliation gate

The strategy-reconciliation gate proves that the new process has no inherited
actionable strategy state:

- prior signal reusable = false;
- current ATM window is not restored;
- current Candidate-E probability is not restored;
- current selected ticker/side is not restored;
- no re-entry/action state is restored from an old process;
- no fill/position/order/cash state is loaded;
- execution mode remains disabled.

This gate is separate from source readiness. It may pass while Coinbase/Kalshi
are still blocked; the full state machine cannot reach `READY_READ_ONLY` until
fresh current source evidence also passes.

## Process restart orchestration

Every process start creates a new runtime session and a fresh gate state
machine beginning at `STARTUP_DISABLED`.

A new process may reach `READY_READ_ONLY` only after:

1. exact frozen identity/cohort checks;
2. durability reconciliation;
3. clock health;
4. fresh current-session/current-generation Coinbase state;
5. fresh current-session/current-generation Kalshi state;
6. neutral read-only strategy reconciliation;
7. execution mode disabled.

Old process monotonic timestamps, Coinbase builders, Kalshi caches, subscription
state, Pong evidence, ATM window, probability, and signal state are never used
as current evidence.

## Required offline restart matrix

The implementation must cover at least:

- clean prior process;
- unclean prior process;
- pending decision with complete raw evidence;
- pending decision with missing/damaged raw evidence;
- old-process Coinbase/Kalshi objects presented to the new process;
- non-neutral strategy-state reconciliation;
- full fresh-gate recovery to `READY_READ_ONLY`;
- post-ready gate regression and no-backfill gap;
- ended cohort;
- execution mode unexpectedly enabled.

## Implementation boundaries

Reuse:

- B1 SQLite/session lifecycle;
- B2 `reconcile_pending_decisions`;
- B3 restart gate state machine;
- B4 authoritative source-readiness evaluators;
- B5-R2 generation-aware source identity helpers for offline tests.

Do not add:

- network activity in this design checkpoint;
- canonical prospective DB;
- cohort arm;
- Candidate-E signals;
- paper/demo/real execution;
- order submission;
- schema migration;
- model or strategy retuning.

## Acceptance

Implementation must first pass an offline validator, focused restart tests,
adjacent B1-B5-R2 regression, and the full repository suite. Only after that
may a separately bounded process-level read-only restart probe be considered.

This design does not establish profitability or execution eligibility.

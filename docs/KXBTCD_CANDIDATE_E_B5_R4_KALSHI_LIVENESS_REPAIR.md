# Checkpoint 21N-Z-E-B5-R4-C — Kalshi Pong-Liveness Repair

## Status

Offline repair validation: **PASS**.

The repair must be safely closed and pushed before B5-R4 live validation is
rerun.

Parent B5-R4-B receipt:

`ebb122545c46b4c530b4c9f590a6e53489624e60`

Frozen B5-R4 design fingerprint remains unchanged:

`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`

## Failure that exposed the bug

First bounded B5-R4 live run:

`candidate_e_b5_r4_20260904T084136Z_85f2b505`

Process 1 behaved as intended:

- PID: `524`
- initial state: `BLOCKED_COINBASE`
- final state: `READY_READ_ONLY`
- Coinbase readiness: `PASS`
- Kalshi readiness: `PASS`
- Coinbase frames:
  - subscriptions: 1
  - last_match: 1
  - match: 164
  - heartbeat: 20
- Kalshi frames:
  - subscribed: 1
  - orderbook_snapshot: 188
  - orderbook_delta: 10,860
- Kalshi sequence gaps: 0

The supervisor then intentionally killed process 1 without clean shutdown.

Process 2 failed with:

`B5R4LiveProbeError: Kalshi current-connection Pong not received`

However, process 2 had already received substantial fresh source data:

- discovery raw records: 1
- Coinbase raw records: 146
  - subscriptions: 1
  - last_match: 1
  - match: 114
  - heartbeat: 30
- Kalshi raw records: 9,955
  - subscribed: 1
  - orderbook_snapshot: 188
  - orderbook_delta: 9,766

Therefore the successor Kalshi WebSocket was actively carrying application
market data. Because the B5-R4 worker sends its first manual Ping before
entering the receive loop, the accumulated Kalshi application frames also show
that at least the initial manual Ping/Pong proof succeeded. The observed
failure was a later periodic Pong timeout.

## Root cause

B5-R4 had accidentally implemented a stricter rule than the already-frozen B4
Kalshi transport-liveness contract.

Frozen B4 policy:

- client Ping interval: 15 seconds;
- Pong timeout: 5 seconds;
- current transport remains proven while the latest successful Pong is no more
  than 20 seconds old;
- after that age is exceeded, readiness becomes `KALSHI_PONG_STALE`.

Pre-repair B5-R4 behavior:

- manually Ping every 10 seconds;
- if any single manual Pong wait exceeded 5 seconds, raise immediately and
  terminate the source worker.

That meant one later Pong miss could kill the whole successor process even
while the last successful Pong was still inside the frozen B4 20-second
liveness window.

This was an implementation-policy mismatch, not evidence that the Kalshi
application-data reconnect itself had failed.

## Accepted repair

B5-R4 now follows the frozen B4 contract exactly:

1. Manual Ping cadence is 15 seconds.
2. Each manual Ping attempt uses a unique sequence payload.
3. A successful matching Pong is the only event that refreshes the recorded
   current-connection Pong timestamp.
4. A missed Pong never fabricates or refreshes liveness.
5. If no current-connection Pong has ever been proven, readiness remains
   blocked.
6. A missed Pong with a still-recent prior successful Pong does not directly
   terminate the worker.
7. The existing B4 source-readiness evaluator remains the sole authority:
   - age <= 20 seconds: liveness may remain `PASS`;
   - age > 20 seconds: `KALSHI_PONG_STALE`.
8. A real connection exception, authentication error, protocol error, sequence
   failure, or other source-worker exception remains fail-closed.

This repair does not weaken the fresh-Pong requirement. It removes an
accidental second policy that was stricter than the frozen source-readiness
contract.

## Regression evidence

User-run validation after the repair:

- focused B5-R4 tests: `30 passed in 1.32s`;
- integrated restart stack: `192 passed in 2.09s`;
- full repository suite:
  `1618 passed, 22 subtests passed in 72.01s`;
- full-suite exit code: `0`.

Five new focused regressions cover:

- unique manual Ping payloads;
- successful Pong as the only liveness refresh;
- one missed Pong with prior proof still inside the frozen age window;
- transition to `KALSHI_PONG_STALE` only after the frozen age expires;
- a missed first Pong never fabricating liveness.

## Safety boundary

The failed live run and this repair remain read-only.

- canonical prospective DB: not created;
- prospective cohort: not armed;
- Candidate-E signals: 0;
- orders: 0;
- production writes: 0;
- real-money execution: not authorized.

B5-R4 live validation is still incomplete. It must be rerun only after this
repair checkpoint is safely closed and pushed.

This checkpoint does not validate host reboot, Linux boot ID/chrony,
long-duration soak, order idempotency, fills, cancels, positions, cash,
kill-switches, partial fills, missed fills, or production write failures.

## Post-repair live validation

The required post-repair B5-R4 live rerun completed successfully.

Accepted run:

`candidate_e_b5_r4_20260904T090313Z_c3ff9837`

Key evidence:

- process IDs: `26580 -> 41280`;
- process 1 prior shutdown: `UNCLEAN_DETECTED`;
- process 2 initial state: `BLOCKED_COINBASE`;
- pending raw evidence: `1 examined / 1 verified / 0 pending`;
- process 2 fresh Coinbase: `PASS`;
- process 2 fresh Kalshi: `PASS`;
- process 2 final state: `READY_READ_ONLY`;
- process 1 Kalshi sequence gaps: `0`;
- process 2 Kalshi sequence gaps: `0`;
- process 2 shutdown: `CLEAN`;
- prior signal reusable: `False`;
- manual Pings/Pongs:
  - process 1: `3 / 3`, `0` timeouts;
  - process 2: `4 / 4`, `0` timeouts;
- raw secret marker hits: `0`;
- artifact hash mismatches: `0` across 18 recorded hash entries;
- canonical prospective DB: not created;
- cohort: not armed;
- signals: `0`;
- orders: `0`;
- production writes: `0`.

B5-R4 whole-process restart validation is therefore accepted as PASS for its
declared scope.

The successful live run did not contain a manual Pong timeout, so the repaired
missed-Pong-with-recent-prior-proof branch remains supported by focused offline
regression evidence rather than this specific live run.

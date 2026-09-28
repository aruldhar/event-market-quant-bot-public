# Candidate-E Restart Durable State B5-R2 — Bounded Live Reconnect Validation

## Scope

Checkpoint 21N-Z-E-B5-R2 validates connection-generation rollover and bounded
live read-only reconnect behavior for the frozen Candidate-E production-shaped
runtime architecture.

This checkpoint is engineering validation only. It does not establish
profitability, arm the 168-hour prospective cohort, create the canonical
prospective database, compute Candidate-E signals, or authorize paper, demo,
or real-money execution.

Parent checkpoint:

- B5-R1 checkpoint: `b455f8f27916d71ff5a7d01340cf53be8e5842b1`
- B5-R1 receipt: `4daa3a0e95994f7d687e4d47023d36563b8ca002`

Frozen parent architecture:

- restart/durable design fingerprint:
  `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`
- production runtime architecture fingerprint:
  `3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

## Accepted implementation

B5-R2 adds a validation-only generation controller and bounded live reconnect
harness.

Accepted behavior:

1. every Coinbase WebSocket connect/reconnect receives a new positive
   connection generation;
2. every Kalshi WebSocket connect/reconnect receives a new positive connection
   generation;
3. reconnect creates a fresh Coinbase minute builder and fresh Kalshi
   full-ladder cache;
4. explicit Coinbase disconnect blocks immediately rather than waiting for the
   application heartbeat stale timer;
5. explicit Kalshi disconnect blocks immediately;
6. old Coinbase builders cannot pass readiness after a new connection
   generation exists;
7. old Kalshi caches cannot pass readiness after a new connection generation
   exists;
8. a new Kalshi connection does not inherit prior snapshots, sequence state,
   subscription SID, or Pong evidence;
9. Kalshi transport uses the frozen 15-second client Ping / 5-second Pong
   timeout contract;
10. Pong evidence proves transport liveness only and cannot reconstruct,
    refresh, or heal the order book;
11. raw inbound transport evidence is persisted before JSON/state
    transformation;
12. the live harness contains no model-signal, P&L, order, cancellation,
    portfolio, or execution path.

The Kalshi `connection generation` and `cache generation` are different
counters. In the accepted live run, WebSocket connection generation rolled
`1 -> 2`, while each fresh cache's internal resync generation remained `0`
because neither connection experienced a sequence gap.

## Repair chronology

The first B5-R2 offline validator failed on a validation expectation, not on
runtime generation behavior.

The new Kalshi generation correctly began with no subscription acknowledgement
or snapshots. Frozen B4 gate precedence checks missing `subscription_sid`
before `resync_required` / full-ladder readiness. Therefore the correct first
blocking reason is `KALSHI_SUBSCRIPTION_SID_MISSING`, not
`KALSHI_FULL_LADDER_NOT_EXACT`.

Repair chronology:

- R1 corrected the offline-validator expectation and one post-reconnect test
  expectation; runtime reconnect code and live CLI logic were unchanged.
- the corrected offline validator then passed;
- the first combined B5-R2 + B4 focused test run produced `54 passed, 1 failed`;
  the remaining failure was one stale `before_snapshot` expectation with the
  same B4 precedence issue;
- the R2 repair installer refused safely because its exact two-line whitespace
  guard did not match the local file; it changed nothing;
- R3 matched only the unique stale assertion text and corrected that remaining
  test expectation;
- runtime reconnect logic, live CLI logic, offline validator semantics, and
  frozen B4 readiness logic were unchanged by R3.

## Offline validation

Final B5-R2 offline validator:

```text
CANDIDATE-E Z-E-B5-R2 RECONNECT HARNESS: PASS
Network requests in validator: 0
Credentials accessed in validator: NO
Coinbase connect/reconnect generations: 1 -> 2
Coinbase explicit disconnect: IMMEDIATE BLOCK
Old Coinbase builder after reconnect: REJECTED
Kalshi connect/reconnect generations: 1 -> 2
Kalshi explicit disconnect: IMMEDIATE BLOCK
Old Kalshi cache after reconnect: REJECTED
New Kalshi generation inherits old snapshots: NO
Kalshi Pong heals fresh book state: NO
Frozen Kalshi Ping/Pong: 15s / 5s
Canonical prospective DB: NOT CREATED
168-hour cohort: NOT ARMED
Signals: 0
Orders: 0 | Production writes: 0
```

Final focused B5-R2 + existing B4 readiness regression:

```text
55 passed in 0.61s
```

Full canonical Windows regression before live validation:

```text
1575 passed, 22 subtests passed in 79.19s (0:01:19)
```

Zero-network live-CLI preflight:

```text
CANDIDATE-E Z-E-B5-R2 LIVE RECONNECT PREFLIGHT: PASS
Network: NOT STARTED
Credentials: NOT ACCESSED
Live flag required: --live
Kalshi frozen Ping/Pong: 15s / 5s
Generations planned per source: 2
Canonical prospective DB: NOT CREATED
168-hour cohort: NOT ARMED
Signals: 0
Orders: 0 | Production writes: 0
```

## Bounded live read-only validation

Run:

`candidate_e_b5_r2_20260904T072848Z`

Output directory:

`data/analysis/candidate_e_b5_r2_live_reconnect/candidate_e_b5_r2_20260904T072848Z`

Selected event:

- event: `KXBTCD-26SEP0404`
- full ladder: 188 markets
- dwell: 8 seconds per connection generation

### Coinbase

Generation 1:

- subscriptions: 1
- `last_match`: 1
- matches: 26
- heartbeats: 8
- total raw Coinbase WS frames: 36
- seeded: true
- sequence healthy: true
- recovery required: false
- post-disconnect readiness reason:
  `COINBASE_WEBSOCKET_NOT_CONNECTED`

Generation 2:

- subscriptions: 1
- `last_match`: 1
- matches: 46
- heartbeats: 8
- total raw Coinbase WS frames: 56
- seeded: true
- sequence healthy: true
- recovery required: false
- old-generation rejection:
  `COINBASE_STATE_NOT_FROM_CURRENT_CONNECTION_GENERATION`
- post-disconnect readiness reason:
  `COINBASE_WEBSOCKET_NOT_CONNECTED`

Coinbase WS raw total: 92.

### Kalshi

Generation 1:

- subscription acknowledgements: 1
- authoritative order-book snapshots: 188
- order-book deltas: 1,221
- raw Kalshi WS frames: 1,410
- sequence gaps: 0
- full-ladder readiness before disconnect: PASS
- post-disconnect readiness reason:
  `KALSHI_WEBSOCKET_NOT_CONNECTED`

Generation 2:

- subscription acknowledgements: 1
- authoritative order-book snapshots: 188
- order-book deltas: 834
- raw Kalshi WS frames: 1,023
- sequence gaps: 0
- full-ladder readiness before disconnect: PASS
- old-generation rejection:
  `KALSHI_CACHE_NOT_FROM_CURRENT_CONNECTION_GENERATION`
- post-disconnect readiness reason:
  `KALSHI_WEBSOCKET_NOT_CONNECTED`

Kalshi WS raw total: 2,433.

Kalshi REST discovery raw records: 1.

### Raw artifact reconciliation

Expected source count:

`92 Coinbase WS + 2,433 Kalshi WS + 1 Kalshi REST = 2,526`

Independent offline audit:

- raw JSONL lines: 2,526
- valid JSON records: 2,526
- manifest `raw_record_count`: 2,526
- exact source-count total: 2,526
- manifest size: 2,361 bytes
- raw JSONL size: 2,168,703 bytes
- manifest SHA-256:
  `F64B7669223518F36AE326B8F04D67CF8C24620F0437A2E1FA9319866267B6B6`
- raw JSONL SHA-256:
  `C555C91708C788B8404360CB2DBCE954E6C15B4C50B8BAB37EF3572B620EE600`

Exact source counts:

```text
coinbase_exchange_ws: 92
kalshi_production_rest: 1
kalshi_production_ws: 2433
Total source records: 2526
```

High-confidence secret-marker scan over the raw JSONL:

```text
Authorization: 0
Bearer : 0
KALSHI-ACCESS-KEY: 0
KALSHI-ACCESS-SIGNATURE: 0
BEGIN PRIVATE KEY: 0
BEGIN RSA PRIVATE KEY: 0
```

No credential content was printed during the audit.

## Safety result

- canonical prospective database created: false
- 168-hour prospective cohort armed: false
- Candidate-E signals computed: 0
- orders: 0
- production writes: 0
- paper execution: not run
- demo execution: not run
- real-money execution: not run
- current risk authorization: unchanged

The live validation proves bounded connection-generation rollover and rebuild
behavior under one real read-only run. It does not prove long-duration runtime
stability, process-crash restart correctness, host-reboot correctness, Linux
chrony/boot-ID integration, or profitability.

## Next engineering target

Proceed to B5-R3 as an offline-first restart-orchestration and
strategy-reconciliation integration slice.

The next slice should bind actual current durable strategy reconciliation into
the frozen restart gate instead of supplying a synthetic PASS, exercise clean
and unclean process-restart matrices, preserve session-scoped monotonic
semantics, and prove that a new process must rebuild all current source state
before `READY_READ_ONLY`.

Do not arm the prospective cohort. Do not add paper, demo, or real-money
execution.

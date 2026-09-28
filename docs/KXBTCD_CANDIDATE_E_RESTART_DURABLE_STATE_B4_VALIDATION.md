# KXBTCD Candidate-E Restart/Durable State B4 Validation

Date: 2026-09-04 (America/Chicago)

## Scope

Checkpoint 21N-Z-E-B4 implements and validates current-source restart readiness under the frozen restart/durable-state design. It connects accepted Coinbase/Kalshi source-state objects and clock/boot evidence to the already-frozen B3 gate state machine without arming the 168-hour cohort and without adding order behavior.

Frozen restart-design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

Frozen production-runtime architecture fingerprint:

`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

Parent closeout receipt commit:

`c34f10ea340f1e123f94f4628b5fd34e35f42007`

## Implemented readiness evidence

### Boot identity

- Production uses Linux `/proc/sys/kernel/random/boot_id` only.
- Windows boot identity is not treated as production authority; Windows validation uses an explicitly injected synthetic UUID.
- A new runtime session never reuses old session monotonic freshness.

### Clock

- Chrony tracking output is parsed into clock evidence.
- The frozen gate is `abs(clock_offset_ms) <= 250`.
- Unknown, malformed, or unhealthy clock evidence blocks readiness.

### Coinbase

Readiness requires:

- the accepted `CoinbaseMinuteBuilder` state;
- current runtime-session identity;
- current WebSocket connection generation;
- healthy heartbeat/recovery state;
- exact current fully completed UTC minute state.

A builder from an old connection generation is rejected even if the process did not restart.

### Kalshi

Book correctness and transport liveness are independent gates.

Book correctness requires the accepted full-ladder cache to be current for the runtime session and connection generation, contain the exact expected event/book set, and retain authoritative snapshot/sequence correctness with no pending resynchronization.

Transport liveness requires current-connection Ping/Pong evidence. The frozen client Ping interval is 15 seconds and Pong timeout is 5 seconds, so the implementation derives a 20-second maximum accepted current-connection Pong age. This is a transport-health bound derived from the architecture contract, not a tuned market-activity threshold.

A quiet market is not declared stale merely because no order-book delta arrives. Conversely, a recent Pong never repairs a sequence gap, clears `resync_required`, or substitutes for a fresh authoritative snapshot.

## Repairs before acceptance

### B4-R1 — connection-liveness hardening

The initial B4 implementation had source/session freshness checks but did not explicitly bind Kalshi readiness to current WebSocket transport liveness or distinguish reconnect generations inside the same process.

R1 added:

- Kalshi current-connection Ping/Pong evidence;
- missing/stale Pong blocking;
- negative/regressing monotonic evidence failing closed;
- Coinbase and Kalshi current WebSocket connection-generation binding;
- explicit tests proving Pong cannot heal broken book/sequence state.

### B4-R2 — synthetic `LadderMarket` fixture repair

The first post-R1 validator attempt failed with:

`TypeError: LadderMarket.__init__() missing 4 required positional arguments: 'event_ticker', 'strike_rank_zero_based', 'event_market_count', and 'historical_structural_role'`

Root cause: the synthetic validator/test fixture still used an older two-field constructor while the committed `LadderMarket` dataclass requires six fields.

R2 updated only the synthetic validator/test fixtures with deterministic event ticker, rank, event-market-count, and `historical_structural_role=None`. Runtime readiness code did not change.

## Canonical validation evidence

### Source-readiness validator

Result: `PASS`.

Key output:

```text
CANDIDATE-E Z-E-B4 SOURCE READINESS: PASS
Boot identity adapter: PASS
Windows validation boot ID: EXPLICIT SYNTHETIC ONLY
Production boot ID: LINUX KERNEL ONLY
Chrony tracking adapter: PASS
Frozen absolute clock threshold: 250 ms
Coinbase accepted minute builder wired: YES
Exact current completed minute: REQUIRED
Coinbase recovery/heartbeat failures: BLOCK
Coinbase old connection generation: REJECTED
Kalshi accepted full-ladder cache wired: YES
Kalshi sequence gap: INVALIDATES / BLOCKS
Kalshi transport Ping/Pong liveness: REQUIRED
Kalshi stale/missing Pong: BLOCK
Kalshi Pong does not heal book state: YES
Old-session source state: REJECTED
Old-connection source state: REJECTED
Combined synthetic current sources: READY_READ_ONLY
Network requests in validator: 0
Canonical prospective DB: NOT CREATED
168-hour cohort: NOT ARMED
Candidate-E signal computation: NOT RUN
Orders: 0 | Production writes: 0
```

### Focused B4 tests

`33 passed in 4.30s`

### Adjacent restart/live-collector regression

Files covered B1 durable store, B2 reconciliation, B3 gate state machine, and the prospective live collector.

`67 passed in 2.75s`

### Full repository regression

`1508 passed, 22 subtests passed in 157.37s`

### Source registry

```text
Sources: 23
Quality policies: 1
Validated sources: 17
Unresolved sources: 0
Unresolved settlement sources: 1
Validation: PASS
```

### Post-validation implementation hashes

- `src/kxbtcd_candidate_e_restart_source_readiness.py`
  `9583a90a2b45d65b79881121d53adea6d647251bcf13da255156a00be2514b0c`
- `tests/test_kxbtcd_candidate_e_restart_source_readiness.py`
  `45110d3a9936e1f124cd6cfb8310bca40ae8393be76a35f44e01bbfd9620e9cd`
- `validate_kxbtcd_candidate_e_restart_source_readiness.py`
  `97c7d752c6e27f88e2ce60b214c84c1da13d17b0643a898fd795ceb1ed224ef0`

## Safety boundary

This checkpoint is read-only/offline validation.

- Network requests in B4 validator: 0
- Canonical prospective DB created: no
- 168-hour cohort armed: no
- Candidate-E signal computation run: no
- Paper/demo/real orders: 0
- Production writes: 0

`docs/RISK_POLICY.md` is intentionally unchanged because the authorization boundary did not change.

## Remaining work before prospective arm

B4 does not complete the full Z-E-B restart program. Remaining work includes:

- strategy-reconciliation current-state integration;
- explicit credential/redaction audit before live restart validation;
- real WebSocket connection-generation rollover on every connect/reconnect;
- restart during Coinbase recovery;
- restart during Kalshi snapshot recovery;
- live within-session source disconnect/recovery;
- Linux host-reboot boot-ID validation;
- fixed-cohort-end restart handling;
- the remaining frozen 17-case crash/restart matrix;
- bounded live read-only restart validation;
- Linux parent-directory fsync validation for eventual arm creation.

Additional repair slices are permitted whenever evidence exposes a defect. The B5 label is planning shorthand, not a deadline or a reason to weaken a gate.

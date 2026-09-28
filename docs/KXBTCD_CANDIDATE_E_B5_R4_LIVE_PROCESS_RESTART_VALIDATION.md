# Checkpoint 21N-Z-E-B5-R4 — Live Whole-Process Restart Validation

## Status

Post-repair bounded live validation: **PASS**.

This document records the accepted live evidence obtained after the B5-R4-C
Kalshi Pong-liveness repair.

B5-R4-C checkpoint:

`c173a5fd3c011b332e960bcda51cfc55295ea85a`

B5-R4-C closeout receipt:

`633745ee6a77be8b48c16abae6c5e0a2b9533e7b`

Frozen B5-R4 design fingerprint remains:

`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`

## Accepted live run

Run:

`candidate_e_b5_r4_20260904T090313Z_c3ff9837`

Output directory:

`data/analysis/candidate_e_b5_r4_live_process_restart/candidate_e_b5_r4_20260904T090313Z_c3ff9837`

Invocation:

```text
.\.venv\Scripts\python.exe .\collect_kxbtcd_candidate_e_b5_r4_live_process_restart.py --live --source-wait-seconds 120
```

The 120-second value was a bounded maximum source-readiness wait, not a fixed
run duration.

## Whole-process restart evidence

### Process 1

- PID: `26580`
- reached fresh read-only readiness before fault injection;
- Coinbase readiness: `PASS`;
- Kalshi readiness: `PASS`;
- Kalshi sequence gaps: `0`;
- manual Ping attempts: `3`;
- successful manual Pongs: `3`;
- manual Pong timeouts: `0`;
- last manual Pong classification:
  `PONG_RECEIVED_RECORD_CURRENT_TIME`.

The supervisor then deliberately terminated process 1 without the clean
shutdown path.

The successor later classified process 1 as:

`UNCLEAN_DETECTED`

This is the intended B5-R4 validation-only crash injection.

### Process 2

- PID: `41280`;
- distinct OS process from process 1;
- initial state: `BLOCKED_COINBASE`;
- pending durability decisions examined: `1`;
- pending raw evidence verified: `1`;
- pending decisions remaining after reconciliation: `0`;
- fresh Coinbase readiness: `PASS`;
- fresh Kalshi readiness: `PASS`;
- Kalshi sequence gaps: `0`;
- final state: `READY_READ_ONLY`;
- prior signal reusable: `False`;
- clean successor shutdown status: `CLEAN`;
- manual Ping attempts: `4`;
- successful manual Pongs: `4`;
- manual Pong timeouts: `0`;
- last manual Pong classification:
  `PONG_RECEIVED_RECORD_CURRENT_TIME`.

The successor therefore rebuilt its own current source state rather than
inheriting readiness from the killed process.

## Safety evidence

Final manifest:

- raw secret marker hits: `0`;
- canonical prospective DB created: `False`;
- cohort armed: `False`;
- Candidate-E signals computed: `0`;
- orders: `0`;
- production writes: `0`.

Current execution authorization remains **read-only**.

## Artifact-integrity evidence

The run produced an artifact hash map covering 18 saved artifacts.

Independent user-side SHA-256 verification compared every listed artifact with
its recorded expected hash:

- hash mismatches: `0`;
- hash entries checked: `18`.

The collector also validates its final live summary before writing
`manifest.json` and prints PASS only after all frozen B5-R4 assertions succeed.

## Interpretation

B5-R4 now provides live evidence for the exact category it was designed to
test:

1. process 1 can reach fresh read-only readiness;
2. process 1 can be killed without clean shutdown;
3. process 2 detects the prior unclean session;
4. process 2 begins blocked;
5. pending raw durability evidence is reconciled;
6. prior strategy signal state is not reused;
7. process 2 rebuilds fresh Coinbase state;
8. process 2 rebuilds a fresh Kalshi full ladder and current transport
   liveness;
9. process 2 reaches `READY_READ_ONLY` only after the fresh gates pass;
10. no order or production-write path is exercised.

## Relationship to the B5-R4-C repair

The first live attempt exposed an accidental immediate-fatal manual-Pong rule.
B5-R4-C aligned the worker with the frozen 15s Ping / 5s timeout / 20s
last-proven-Pong-age policy.

The accepted post-repair live run had 7 manual Ping attempts total and 7
successful matching Pongs, with zero manual Pong timeouts.

Therefore this live run proves the repaired runtime succeeds under normal
Ping/Pong behavior. It does **not** live-exercise the branch where one manual
Pong is missed while a previous successful Pong remains inside the frozen
20-second age window. That branch is covered by the accepted focused offline
regression tests.

## What B5-R4 does not prove

B5-R4 does not validate:

- actual host reboot;
- production Linux boot-ID handling;
- production chrony/clock-health deployment;
- long-duration soak stability;
- order submission;
- order idempotency / duplicate-order prevention;
- fill, cancel, position, cash, or exposure reconciliation;
- kill-switch behavior under order flow;
- partial or missed fills;
- production write-endpoint failures.

Those remain separate blocking operational categories before any real-money
micro-production authorization.

## Conclusion

**B5-R4 live whole-process restart validation: PASS.**

This is an operational-safety result only. It does not establish trading
profitability and does not authorize execution.

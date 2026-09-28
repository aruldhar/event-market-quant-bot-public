# Checkpoint 21N-Z-E-B5-R4-B — Live Whole-Process Restart Implementation Validation

## Status

Implementation-complete and locally validated offline. Safe checkpoint closeout
must complete before any `--live` invocation.

Parent B5-R4-A design receipt:

`7bad4d50def3e44744347aedb11dfabe3d21c1ba`

Frozen B5-R4 design fingerprint:

`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`

## Implemented scope

The B5-R4 implementation adds:

- a parent supervisor;
- two real Python child-process roles;
- an explicit supervisor-induced unclean termination of process 1;
- reuse of the same noncanonical validation SQLite durable-state store by
  process 2;
- successor crash classification and pending raw-evidence reconciliation;
- fresh Coinbase and authenticated read-only Kalshi rebuilding under the new
  runtime session;
- a requirement that the successor starts blocked before fresh source evidence;
- a requirement that fresh source readiness passes before `READY_READ_ONLY`;
- high-confidence secret-marker scanning of validation artifacts;
- fail-closed final manifest assertions.

Default CLI invocation remains zero-network and does not access credentials.
Live behavior requires the explicit `--live` flag.

## Offline validation evidence

Canonical user-run evidence:

- implementation contract validator: `PASS`;
- focused B5-R4 tests: `25 passed in 1.19s`;
- combined B1/B2/B3/B4/B5-R1/R2/R3/R4 restart stack:
  `187 passed in 2.95s`;
- zero-network CLI preflight: `PASS`;
- full repository suite:
  `1613 passed, 22 subtests passed in 65.90s`;
- full-suite exit code: `0`.

Zero-network preflight explicitly confirmed:

- network: not started;
- credentials: not accessed;
- two OS processes planned;
- induced unclean process termination planned;
- fresh completed Coinbase minute required after restart;
- fresh Kalshi full ladder + current Pong required;
- host reboot/clock validation not claimed by B5-R4;
- canonical prospective DB not created;
- cohort not armed;
- signals 0;
- orders 0;
- production writes 0.

## Implementation identities

- `src/kxbtcd_candidate_e_b5_r4_live_process_restart.py`
  `25f31feee7ea0f9918da8dbf7d9c5ff0194c89cc325adfb34967bd908df46b62`
- `collect_kxbtcd_candidate_e_b5_r4_live_process_restart.py`
  `0025c98c37ce5e9dce7a32cbd7d93498241c7bdfded9212693cae225acb846c8`
- `tests/test_kxbtcd_candidate_e_b5_r4_live_process_restart.py`
  `4681851857daab991dce949d5792ef845531d4f4c5aca596ff8791797ebaa713`
- `validate_kxbtcd_candidate_e_b5_r4_live_process_restart.py`
  `45f47f956fab66e5454ba7a7e32a25bf9a806b7031fa74a4b697c381e7257cb8`

## Safety boundary

This implementation does not add or authorize:

- Candidate-E signal computation;
- canonical prospective cohort arming;
- paper/demo execution;
- real-money order submission;
- order cancellation;
- fill/position/cash management;
- production write endpoints.

Current execution authorization remains read-only.

## Interpretation boundary

Passing the offline implementation tests proves that the intended B5-R4
orchestration and fail-closed assertions are internally consistent in the
test environment. It does **not** yet prove that a real crash/restart can rebuild
fresh Coinbase/Kalshi state successfully.

That evidence must come from the separately run bounded live B5-R4 validation
after this implementation checkpoint is safely closed and pushed.

B5-R4 also does not claim host reboot/Linux chrony validation, long-duration
soak stability, or execution-specific duplicate/fill/cancel/kill-switch
behavior. Those remain separate operational-safety categories.

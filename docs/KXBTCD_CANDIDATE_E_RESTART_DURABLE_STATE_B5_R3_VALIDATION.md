# Checkpoint 21N-Z-E-B5-R3 — Offline Process-Restart Reconciliation Validation

## Status

Implementation-complete and locally validated; safe checkpoint closeout remains
to be run.

Parent receipt:

`3041a628329c94914c297553139d0e52a7a5d94d`

Frozen B5-R3 design fingerprint:

`0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea`

Binding micro-production roadmap fingerprint:

`57e7e5c88bd296128927362119c0f3705d4be9ce5f0d8a13c1fd652ddd2e2677`

## Scope

B5-R3 integrates the already accepted durable-state, raw-evidence
reconciliation, restart gate, source-readiness, and reconnect-generation
components into one **offline process-restart orchestrator**.

This checkpoint adds no network client, Candidate-E signal computation, cohort
arming, paper/demo broker, order submission, cancellation, position state, or
P&L path.

## Accepted implementation behavior

The new process:

- receives a new runtime session identity;
- starts from `STARTUP_DISABLED`;
- classifies a prior process as `CLEAN` or `UNCLEAN_DETECTED`;
- records process discontinuities without canonical backfill;
- reconciles every `PENDING_RAW_DURABILITY` decision to `VERIFIED` or
  `RAW_EVIDENCE_GAP`;
- preserves and excludes damaged/missing evidence rather than reconstructing it;
- allows fresh recovery after a classified historical raw-evidence gap;
- requires neutral/non-actionable strategy restart state;
- restores no prior ATM window, Candidate-E probability, ticker/side selection,
  re-entry state, fill/position/order/cash state, or actionable signal;
- keeps `prior_signal_reusable=false`;
- rejects old-process Coinbase and Kalshi state through current runtime-session
  binding;
- reaches `READY_READ_ONLY` only after all fresh frozen gates pass;
- immediately blocks again if a gate regresses after readiness;
- treats an enabled execution mode as fatal.

No new persisted strategy-state table was added.

## Validation evidence

Canonical Windows user-run evidence before closeout:

- B5-R3 offline validator: `PASS`;
- focused B5-R3 tests: `13 passed in 1.85s`;
- adjacent restart-stack regression: `162 passed in 2.57s`;
- full repository regression:
  `1588 passed, 22 subtests passed in 63.19s`;
- pytest exit code: `0`.

The focused and adjacent coverage includes:

- clean restart;
- unclean restart;
- complete pending raw evidence;
- missing/damaged raw evidence;
- strategy-neutrality enforcement;
- execution-enabled fatal behavior;
- stale old-process Coinbase rejection;
- stale old-process Kalshi rejection;
- all-gate recovery to `READY_READ_ONLY`;
- post-ready gate regression;
- fixed-cohort-end handling.

## Implementation identities

- `src/kxbtcd_candidate_e_b5_r3_process_restart.py`:
  `4f0b795fcd02e13f76f4bbfa77c7604173d440b07bb54bb008d33ad504474ae4`
- `tests/test_kxbtcd_candidate_e_b5_r3_process_restart.py`:
  `d02eaeeca374c8baabbe282af822fbe2e42888e230052b56c92fc95a7f723605`
- `validate_kxbtcd_candidate_e_b5_r3_process_restart.py`:
  `5a2ff686acbc84dea217128255dbd643318c837184a0f4646c1263b45ccc4fb1`

## Safety state

- network requests in B5-R3 validator: `0`;
- canonical prospective database: not created;
- 168-hour read-only precursor: not armed;
- Candidate-E signals: `0`;
- orders: `0`;
- production writes: `0`;
- current execution authorization: read-only.

The binding long-term target remains the separately gated and explicitly
approved one-contract / `$0.01` micro-production validation. B5-R3 does not
authorize it.

## Next engineering slice

After safe closeout, run a **bounded live read-only whole-process restart probe**
that proves a new process rebuilds current Coinbase/Kalshi state across actual
transport reconnects before `READY_READ_ONLY`.

Do not arm a separate mandatory 168-hour read-only precursor and do not add
paper/demo/real execution in that probe.

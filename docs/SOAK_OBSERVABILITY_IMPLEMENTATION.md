# 21N-Z-F: durable observability component checkpoint

Date: 2026-09-06. Base Git HEAD: `2acbc7655b49f48a45b15246d63eb8036bb8b1d6`.
Status: offline component integration validated; B5-R5-B-B remains open.
AWS shakedown: NOT READY. No live transport or deployment was started.

## Changes

- `src/kxbtcd_candidate_e_soak_observability.py`: run-owned, exclusive telemetry
  directory; durable readiness, metric, latency, and source-event JSONL streams;
  exact on-disk latency index; final descriptive summary and artifact inventory.
- The strict metric sampler requires every field in `SAMPLE_FIELDS`; missing
  values are never replaced with zero. Unknown clock readings can remain null
  while blocked. Ready observations require consistent current clock evidence.
- Local latency observations use monotonic nanoseconds. Reports contain count,
  median, nearest-rank p95/p99, and maximum. A zero-count distribution contains
  null statistics. There is no invented latency acceptance threshold.
- Source-event records carry source, event, generation, and optional event ticker.
  They accept no raw payload, auth header, or credential fields.
- Counter/generation regressions, missing sampling cadence, inconsistent identity,
  write/fsync failures, out-of-band telemetry changes, and latency-index tampering
  prevent successful evidence sealing. Failures latch.
- `run_observed_soak` requires the observer and a raw-closure callback. The
  underlying lifecycle API retains its optional hooks for existing component tests.
- RUNNING precedes telemetry initialization and source startup. Source joins
  precede raw closure, final telemetry sealing, and manifest artifact hashing.
- `close_verified_runtime_archives` closes all source managers and inventories
  their newly closed descriptors and compressed files, including final partial
  hours, only after verification. Previously recovered sessions require explicit
  inventory treatment in production integration.
- The runner now excludes join/shutdown time from its final timing snapshot and
  surfaces exceptions raised by source supervisors during shutdown as failures.

## Interfaces and evidence limits

`SoakObservability` receives a strict `sample_metrics(now_ns)` callable, an explicit
`production` or `offline_fixture` mode, UTC/monotonic clocks, and the set of wired
latency producers. Source producers call `record_latency` and `record_source_event`.
The sampler must supply cumulative counts for the whole attempt, not counters
reset for each connection. Its source and host values must share the run's clock
and identity. Producers must be stopped before finalization.

This checkpoint supplies the persistence/validation/reporting consumer and its
lifecycle integration. It does NOT implement or certify actual source-counter,
transport-latency, Linux-resource, or storage-total sampler producers. Declaring a
producer name is not proof that production instrumentation is complete. The new
offline tests supply labeled fixtures. Do not use an empty/fake sampler or the
legacy unobserved lifecycle API as an AWS acceptance path.

The finalization sample is explicitly outside the measurement window. It uses
current monotonic time and captures final compression totals without extending
active readiness accounting. Whole-attempt byte rates include startup and are
not automatically the frozen active-window shakedown U/C inputs.

The summary always leaves empirical operational adequacy `NOT_ASSESSED`, AWS
qualification `NOT_ESTABLISHED`, and the canonical disk gate unresolved. It is
not an independent acceptance receipt: the enclosing terminal manifest and all
artifact hashes must also validate. A missing terminal manifest remains unqualified.

## Validation

- New observability tests: 50 passed.
- Combined soak plus clock-bridge/publisher regression: 227 passed in 10.58 seconds.
- Python 3.12.14, pytest 9.1.1, pyarrow 25.0.1, Windows offline environment.
- The combined test harness prohibited socket connect/connect_ex/create_connection.
- Tests cover completion with blocked intervals, exact quantiles, missing/invalid
  metrics, timeout, fatal readiness, final compression sampling, corrupt evidence,
  raw closure failure, actual four-source zstd artifact/manifest integration,
  concurrent writes, secret-marker rejection, and shutdown exceptions/timing.
- The checkout's Store-Python 3.11 virtual-environment launcher was unavailable
  to the Codex sandbox account. Tests used an isolated Python environment in the
  Codex task workspace; the original `.venv` was not replaced.
- PyPI network access was used only for installing test dependencies. No market
  or AWS networking occurred. No historical outcome archive or P&L test suite ran.
- Windows testing does not establish Linux directory-fsync, container, chrony
  publisher, or real-host performance behavior.

## Exact next implementation action

Wire and offline-test actual metric producers through the existing runtime core,
REST/WebSocket transports, source supervisors, segment managers, and real Linux
resource/clock-bridge adapters. Prove counter/event/latency coverage against
actual fake-transport activity; do not count an injected static dictionary as
production instrumentation. Verify cumulative storage totals include final
closure and distinguish startup from the active shakedown window. Establish
the complete required raw/recovery artifact inventory and the idle one-second
raw-fsync deadline. Then bind the mandatory observed path into the dedicated
CLI/Compose package and validate it before B5-R5-B-C.

The accepted clock amendment requires a systemd-managed host publisher and a
read-only evidence-file consumer, with matching boot/time namespace and evidence
age at most five seconds. Do NOT restore direct chronyd-socket mounting.

Frozen parent fingerprint:
`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`.
Clock amendment fingerprint:
`eaf9525f726f4beaad6f7f4bc3e3704534459a1033ec28a1c4656def7121813f`.
Neither frozen design file was changed.

## 21N-Z-F producer wiring work in progress

The local checkout now contains an uncommitted producer slice:

- `RuntimeMetricProducers` samples real Linux process/resource/disk readings,
  resolves the existing Linux boot/time-namespace identity adapter, and reads
  only the accepted host-published clock-evidence file. Missing Linux resource
  support, identity, or valid bridge evidence fails closed.
- Runtime-core source ingress updates cumulative message, heartbeat, Kalshi
  snapshot/delta/gap, reconnect, generation, and storage counters. REST
  adapters record request duration through the same core instance; WebSocket
  raw-first ingress records durable pipeline latency observations.
- Segment managers retain cumulative raw-write and compressed-write totals
  across final zstd closure so finalization reports storage written during the
  attempt rather than only files still present on disk.
- New offline tests drive a fake Coinbase WebSocket frame through the actual
  runtime core and exercise the sampler with injected Linux bridge/resource
  readers. They do not use static metrics dictionaries.

No network, AWS, Docker, settlement, signal, P&L, or execution action occurred.
The repository Python launchers were unavailable to the Codex sandbox account.
The user ran the focused producer/runtime/REST regression in the project
environment after two Windows-adapter repairs: **22 passed in 1.21 seconds**.
No socket-capable test path was used.

The user subsequently ran the broader offline soak, clock-bridge, and host
publisher regression in the same project environment: **229 passed in 18.34
seconds**. This remains an offline regression result; it does not authorize or
qualify AWS, Docker, market connections, settlement access, signals, P&L, or
execution.

After WebSocket-generation, reconnect-supervisor, and idle-fsync producer
wiring, the user reran that complete offline regression: **230 passed in 16.22
seconds**. The increased count includes the new producer/integrated-idle-fsync
coverage. No socket-capable test path was used.

The user also validated the new packaged-orchestrator lifecycle using fake
supervisors and a real core-owned raw archive: **60 passed in 5.79 seconds**.
The test proves terminal sealing occurs after archive closure and inventories a
real compressed raw artifact. No container or source transport was started.

Recovered descriptors are now included in the terminal artifact inventory;
the focused recovery/observability/orchestrator regression passed **68 tests in
5.92 seconds** in the project environment.

Final combined offline soak, clock-bridge, and host-publisher regression after
producer, package, orchestrator, idle-fsync, and recovery-inventory work:
**235 passed in 12.51 seconds**. This remains offline validation only.

Static Compose review now enforces the frozen service ID, non-root image user,
no privileges, dropped capabilities, no-new-privileges, a read-only host clock
file mount, no chronyd socket, and no automatic restart. The package tests
passed **3 tests in 0.33 seconds**. No Docker daemon action occurred.

Orders (paper/demo/production): 0. Production writes: 0. Signals: 0.
Settlement access: none. Strategy P&L: not run. No commit, push, or deployment.

## Recommended development setup

Open this exact checkout as a local Codex project for now: it contains substantial
untracked, unpublished soak work. A fresh clone of main does not contain it.
After preserving that work, prefer a development folder outside OneDrive and a
regular, accessible Python installation with a repository-specific environment.
Save its tested setup/test commands as local project actions. Use focused tasks
and short checkpoint notes; choose Terra for routine work and a stronger model
for difficult safety reviews. Changing clients or running locally does not make
agent usage free or create a separate plan allowance.

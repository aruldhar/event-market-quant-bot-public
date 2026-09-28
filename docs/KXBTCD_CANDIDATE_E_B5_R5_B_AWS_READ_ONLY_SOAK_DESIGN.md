# Checkpoint 21N-Z-E-B5-R5-B-A — AWS Read-Only Soak Design

## Status

Design freeze only. No live soak, credentials provisioning, signal computation,
or execution is performed by this checkpoint.

Parent closeout receipt:

`4039b8eebd4aefa8c2af9cc5f556acd61f6b9242`

Design fingerprint:

`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`

Config:

`configs/kxbtcd_candidate_e_b5_r5_b_aws_read_only_soak_design_v1.json`

## Purpose

Test whether the production-shaped AWS runtime can remain operational for a
meaningful continuous period while preserving every fail-closed invariant.

This is an engineering reliability experiment, not a strategy-performance or
profitability experiment.

## Frozen program

The validation sequence is:

1. implement and offline-test the dedicated soak runner and Docker Compose path;
2. run a 3,600-second AWS shakedown after first `READY_READ_ONLY`;
3. use shakedown evidence to freeze the empirical minimum-free-disk gate;
4. run an 86,400-second continuous AWS soak after first `READY_READ_ONLY`;
5. after the 24-hour timer completes, perform one separate controlled unclean
   process restart on the same host and require fresh reconciliation/readiness.

The active monotonic timer does not pause when sources or clock health become
blocked. Downtime therefore remains visible in the measured availability.

If the runtime cannot reach its first `READY_READ_ONLY` state within 300
seconds, the run terminates as `INITIAL_READINESS_TIMEOUT`. The active timer
never starts, measurement is incomplete, and that attempt cannot qualify as
either the shakedown or the canonical soak.

## Source behavior

Coinbase uses the already-frozen BTC-USD matches + heartbeat semantics.
Reconnect creates a new source generation and requires exact completed-minute
state before readiness may return.

Kalshi uses authenticated production order-book WebSocket data for the entire
selected KXBTCD event ladder. A sequence gap invalidates the ladder until
authoritative recovery completes.

KXBTCD event rollover is explicitly part of the soak. At rollover the runtime
blocks readiness, rediscovers the current event, invalidates the prior Kalshi
generation, opens a fresh generation, subscribes the new full ladder, and
requires fresh snapshots plus current Pong evidence before returning to ready.

## AWS clock and boot evidence

Synthetic clock evidence is prohibited.

The runner must use the real Linux boot-ID adapter and real chrony production
adapter. The existing frozen readiness boundary remains an absolute clock offset
of 250 ms.

An unhealthy, unknown, or stale clock blocks readiness. Production chrony
evidence used by the readiness gate may be no more than 5 seconds old. The
separate observability record is sampled every 60 seconds.

An unexpected Linux boot-ID change during the 24-hour continuous run is a hard
failure because the host rebooted during a test intended to remain on one boot.

## Storage

Raw source data must be persisted and flushed before transformation and fsynced
at least once per second.

Segments are aligned to UTC clock-hour boundaries. The first and final segment
may therefore be partial.

A closed segment is accepted only after this crash-safe sequence: fsync and
close the raw file, hash the uncompressed bytes, losslessly compress to a
temporary zstd file, fsync it, decompress it and prove the original SHA-256,
hash the compressed bytes, atomically rename it, atomically write its descriptor,
fsync the directory, and only then remove the redundant uncompressed copy.

An orphan temporary compressed file is never authoritative. Recovery recompresses
from the intact raw file. If neither an intact raw file nor a verified compressed
segment descriptor can establish the bytes, the run fails.

Raw data is segmented by source in one-hour segments. Closed segments are
losslessly zstd-compressed and retain SHA-256 hashes for both uncompressed and
compressed representations.

The numeric minimum-free-disk threshold is intentionally not guessed before
evidence, but its formula is predeclared now.

Let `U` be shakedown uncompressed bytes/hour and `C` be shakedown compressed
bytes/hour. Before the 24-hour run:

`required_free = max(10 GiB, ceil(1.5 * (24*C + 2*U) + 2 GiB))`

The shakedown supplies only `U` and `C`; it does not choose the formula. Any
implementation/storage-format change after that measurement invalidates the
numeric gate and requires another shakedown.


## Packaged runtime and credentials

The shakedown and accepted 24-hour run use the same Docker Compose service and
same Docker image digest. If implementation changes after the shakedown, that
shakedown is invalidated and must be repeated.

The runtime container is not privileged, does not use host networking, does not
mount the Docker socket, and does not receive a writable source-tree mount.

The Kalshi API-key ID is delivered only through the runtime environment and is
not persisted. The private key is exposed as one read-only file at
`/run/secrets/kalshi_private_key.pem`; it is never copied into the image or
runtime artifacts.

Real host chrony evidence remains mandatory. B5-R5-B-B must discover and freeze
the exact Amazon Linux chronyd control-socket path and expose only that narrow
control boundary to the container. There is no privileged-container or Docker
socket fallback. If real chrony cannot be read, readiness is blocked.

## Run manifest and immutable identity

Every attempt writes an atomic run manifest before live sources start.

The starting identity includes the run ID/role, design fingerprint, Git HEAD,
Docker image digest, real boot ID, requested active duration, UTC/monotonic start
times, initial free disk, and disabled execution mode.

The terminal manifest records actual duration, measurement completion,
safety/operational classification, zero order/write counts, and integrity
descriptors for every required artifact. Credential values are never recorded.

A changed image digest or an artifact size/hash mismatch is a hard failure.

## Observability

At minimum the soak records:

- readiness state/reason and blocked duration;
- source generations, reconnect attempts, recoveries, and event rollovers;
- Coinbase heartbeat/interarrival evidence;
- Kalshi sequence gaps, resyncs, Ping/Pong health, and RTT;
- REST and local receive/persist/apply/readiness processing durations;
- real chrony offset and boot identity;
- CPU, memory, host load, disk free space, bytes written, compression, and
  bytes/hour.

Latency is reported descriptively with median, p95, p99, and maximum values.
B5-R5-B does not invent a post-hoc profitability or latency threshold.

## PASS/FAIL interpretation

A source outage or clock problem is not automatically a safety failure if the
runtime correctly becomes `BLOCKED` and refuses stale readiness. That blocked
time is still counted against availability and can make AWS operationally
unacceptable.

Hard failures include any order/write, raw-persistence failure, leaked secret
marker, stale-generation readiness, readiness across an unresolved sequence gap,
readiness with an unhealthy clock, monotonic regression, unexpected host reboot,
premature process/container death before the active duration requested for that
run, or invalid closed raw segment.

Therefore the final report distinguishes:

- safety invariant PASS/FAIL;
- measurement completion;
- empirical operational adequacy.

A system may preserve safety correctly yet still be rejected for poor uptime,
latency, resource headroom, or storage behavior.

## Post-soak restart

The controlled process restart occurs only after the continuous 86,400-second
window completes.

The host-side supervisor sends `SIGKILL` to the already-running runtime
container after the 86,400-second measurement completes. Automatic container
restart is disabled for this validation.

The successor uses the same Compose service definition, exact Docker image
digest, durable-state volume, output volume, and host boot ID, but must have a
new container identity and OS process ID. It must detect the prior unclean
session, start blocked, reconcile pending durable evidence, establish brand-new
Coinbase and Kalshi generations, use real boot/chrony evidence, and reach
`READY_READ_ONLY` only from fresh source state.

## Facts

- B5-R4 already validated live whole-process restart behavior.
- B5-R5-A already validated the real AWS/Linux boot and chrony adapters.
- The AWS host baseline is `us-east-1`, physical AZ `use1-az4`.
- Current execution authorization remains read-only.

## Hypothesis being tested

The AWS production-shaped runtime can sustain a continuous 24-hour read-only
workload with bounded resources, auditable storage growth, acceptable source
behavior, and correct fail-closed recovery.

This is a hypothesis, not an accepted fact.

## Unresolved until evidence

- empirical raw/compressed bytes per hour;
- exact minimum-free-disk gate for the canonical 24-hour run;
- observed source uptime and reconnect frequency;
- observed AWS latency/jitter distributions;
- CPU/memory/storage headroom;
- whether any implementation defects emerge only under long duration.

## Safety boundary

- settlement outcomes: not accessed;
- strategy P&L: not run;
- Candidate-E signal computation: disabled for this infrastructure soak;
- paper/demo/production orders: 0;
- production writes: 0;
- execution mode: disabled;
- `docs/RISK_POLICY.md`: unchanged.

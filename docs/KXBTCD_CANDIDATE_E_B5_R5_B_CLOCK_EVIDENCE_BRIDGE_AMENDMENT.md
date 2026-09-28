# Checkpoint 21N-Z-E-B5-R5-B-B-A — Clock-Evidence Bridge Amendment

## Status

Design amendment only.

Parent closeout receipt:

`6b8148823b1eddfd8c894547c14f8500c2dd8553`

Frozen B5-R5-B-A soak design fingerprint:

`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`

Amendment fingerprint:

`eaf9525f726f4beaad6f7f4bc3e3704534459a1033ec28a1c4656def7121813f`

The closed B5-R5-B-A config is not modified.

## Why an amendment is required

B5-R5-B-A correctly froze the requirement for real Linux boot identity and real
chrony evidence, with stale or unhealthy clock state blocking readiness.

Its proposed container transport was a narrow bind mount of the host chronyd
control socket.

AWS testing established that this transport does not work in the production
host/container arrangement.

Host-side direct access to `/run/chrony/chronyd.sock` succeeds as both root and
the `chrony` user.

A Docker bridge container with only the socket bind-mounted can see the socket
but `chronyc` returns:

`506 Cannot talk to daemon`

Repeating the diagnostic with Docker host networking produces the same result.
Therefore host networking is not accepted as a repair.

## Accepted replacement

The replacement is:

**host systemd publisher -> atomic evidence file -> read-only container consumer**

The host publisher executes real:

`chronyc -n tracking`

against the AWS host's real chronyd.

It records the raw tracking output together with the real host boot ID, host time
namespace identity, UTC capture time, monotonic capture time, publisher identity,
return code, and publisher status.

The file is atomically replaced after fsync.

The runtime container receives only that evidence directory as a read-only mount.
It receives no chronyd Unix socket and requires neither privileged mode nor host
networking.

## Freshness and identity

The container evaluates evidence age as:

`container_monotonic_now - host_captured_monotonic`

The AWS experiment established that the normal Docker container and host share
the same Linux time namespace and showed consistent uptime.

Production acceptance nevertheless verifies the time-namespace identity rather
than assuming it.

To restore readiness, evidence must:

- be at most 5 seconds old;
- have nonnegative monotonic age;
- match the container's current Linux boot ID;
- match the container's current time namespace;
- report publisher PASS;
- contain successful real chronyc output;
- parse through the existing production chrony tracking parser as PASS.

Missing, malformed, stale, failed, boot-mismatched, or namespace-mismatched
evidence blocks readiness.

Synthetic evidence is a hard failure.

## SSM independence

Neither process may depend on the interactive AWS Session Manager shell.

The clock publisher runs under systemd.

The soak runtime runs detached under the Docker daemon.

B5-R5-B-B validation must explicitly demonstrate that an SSM session can end and
a later session observes the same still-running publisher/runtime identities.

This does not enable Docker automatic restart during validation. A runtime crash
must remain observable as a failure.

## Scope preserved

This amendment changes only the transport by which the container receives real
host chrony evidence.

It does not change:

- the frozen 250 ms absolute clock-offset gate;
- the 5-second evidence freshness requirement;
- Linux boot-ID requirements;
- source readiness or reconnect semantics;
- KXBTCD event rollover;
- soak durations;
- raw-storage rules;
- the disk-gate formula;
- post-soak restart behavior;
- model or strategy behavior;
- execution authorization.

## Empirical AWS evidence

Observed before this amendment:

- host chronyd running: PASS;
- real host chronyc tracking: PASS;
- host direct chronyd socket as root: PASS;
- host direct chronyd socket as `chrony`: PASS;
- bridge-network single-socket container: FAIL, `506 Cannot talk to daemon`;
- host-network single-socket container: FAIL, `506 Cannot talk to daemon`;
- host atomic evidence generation: PASS;
- normal bridge container evidence read: PASS;
- attempted container write to evidence mount: correctly rejected;
- host/container time namespace equality: PASS;
- host/container uptime consistency: PASS.

The disposable Docker diagnostics used container/package infrastructure network
access. They did not access Kalshi or Coinbase market-data endpoints.

Settlement outcomes were not accessed. Strategy P&L was not run. Orders and
production writes were zero.

## Next

After this amendment closes, B5-R5-B-B implements and offline-tests:

1. the host systemd publisher;
2. the fail-closed evidence consumer;
3. Docker Compose packaging;
4. the dedicated soak runner;
5. SSM-disconnect independence.

No one-hour AWS shakedown begins before that implementation closes cleanly.

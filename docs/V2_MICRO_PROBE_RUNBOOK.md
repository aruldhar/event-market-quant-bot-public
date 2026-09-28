# Candidate-E V2 micro-probe runbook

This runbook prepares a future explicitly approved production micro probe. It
does not authorize or provide an order-submission command.

The probe uses the frozen Candidate-E V2 primary `$0.02` net-edge rule and a
`0.01` contract quantity only when the selected market proves that increment.
The initial probe permits at most five IOC entry attempts while flat, no
re-entry, one reduce-only GTC protection exit, and a reconciled full-remainder
FOK handoff only when the retained total net-proceeds target is met.

Before creating any exact run request, record these facts in a reviewed
preflight receipt:

- selected market ticker and demonstrated quantity increment;
- immutable response hashes for the exact market metadata and fee schedule;
- the market's fractional-trading flag, exact `0.01` quantity increment, and
  legal price grid;
- fixed fee schedule identifier;
- cash-loss cap, order cap, and entry-attempt cap;
- kill-switch identifier and audit run identifier;
- accepted terminal 24-hour read-only soak identifier;
- accepted controlled-restart evidence identifier; and
- the user's explicit approval identifier for this exact run.

The offline `micro_probe_preflight` and `micro_probe_readiness` validators
reject absent or inconsistent facts. They contain no credential, network,
order, cancellation, fill, or production-write capability.

## Read-only live-shadow dashboard rehearsal

An accepted future read-only soak may publish atomic causal market snapshots to
a separate, networkless live-shadow sidecar. The sidecar uses the same collector
image but has no `.env`, Kalshi key, host-clock mount, or write access to raw
soak evidence. It reads the snapshot volume as read-only and writes its own
append-only simulation ledger plus a separate dashboard read model. A sidecar
failure cannot block or alter the collector.

The live Scenario Lab evaluates exactly five predeclared net-edge thresholds on
the same causal snapshots: `$0.00`, `$0.01`, `$0.02`, `$0.03`, and `$0.05`.
`edge_002` (`$0.02`) remains the frozen PRIMARY policy. Live policies use
`OBSERVED_SHADOW_PATH`; hypothetical 500 ms / 1000 ms latency sensitivity is
offline-only and must not appear in the live leaderboard.

Each hypothetical entry is sized to at most `$100.00` including simulated
fees. The dashboard records the largest visible `0.01`-contract increment that
fits that budget and a hypothetical IOC book walk only. Its P&L label is
`SIMULATED_OBSERVED_DEPTH_NOT_VENUE_REALIZED`; it does not prove a venue fill,
queue priority, hidden liquidity, cancellation race, or resting-order fill.
This rehearsal must remain separate from the exact `0.01` production probe
authorization above.

The simulation ledger and Grafana read model use separate Docker volumes.
Grafana must never mount the simulation-ledger volume or raw soak volume. It may
mount only the dedicated materialized read-model volume as read-only, plus its
own Grafana administrator password secret. Grafana is bound to localhost only
and accessed initially by SSH tunnel. Venue credentials are prohibited.

The dashboard read model is run-scoped operational evidence. Use a fresh
`shadow_dashboard_read_model` Docker volume for every qualification, soak, or
other run identifier; do not reuse a prior run's read-model volume. The
append-only simulation ledger remains authoritative if dashboard projection
must be reconstructed after a sidecar restart.

Any change to collector code, sidecar code, dashboard read-model code, Grafana
image/plugin versions, provisioning, Compose isolation, or runtime image/config
invalidates same-image qualification. A one-hour shakedown must qualify the
exact deployment that will be used for the subsequent 24-hour run. Do not
rebuild either runtime image between qualification and that run.

Controlled restart is a separate read-only proof after the terminal 24-hour
review. Start a fresh container and require fresh host-clock evidence, an exact
completed Coinbase REST-candle evidence, Kalshi discovery/snapshot recovery,
and a new `READY_READ_ONLY` lifecycle. Coinbase WebSocket matches and
heartbeats remain an append-only archive/diagnostic feed: a recoverable
WebSocket outage must be recorded and retried, but it must not block V2 while
the independent exact REST candle and Kalshi evidence remain current. Its
evidence must show a new run identifier and no orders, signals, or production
writes. It proves safe source recovery; it does not prove live position or
order recovery.

The offline `controlled_restart_proof` validator fails closed unless all of
those recovery facts and zero-activity counters are recorded.

Use `python -m src.kxbtcd_candidate_e_read_only_soak_acceptance_cli` after the
terminal review to create an acceptance receipt from the actual summary and
manifest. The CLI reads local evidence only; it does not contact a venue.

After an exact probe is separately authorized, its review must reconcile
authoritative venue order/fill/position facts against the append-only audit
record before discussing any scale-up. The offline reconciliation gate requires
the exact micro quantity, matching expected and venue-reported fees, and a
flat final position. Automatic scale-up is prohibited.

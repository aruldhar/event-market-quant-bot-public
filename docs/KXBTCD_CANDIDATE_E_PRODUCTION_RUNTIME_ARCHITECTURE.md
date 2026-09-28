# Candidate-E Production-Shaped Runtime Architecture

Checkpoint: 21N-Z-C

Architecture fingerprint:

`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

## Purpose

Freeze the runtime architecture intended to survive unchanged from read-only
prospective collection through later demo qualification and, only after separate
risk authorization, a micro-production probe.

This checkpoint is design-only. It adds no order path and does not arm the
168-hour prospective cohort.

## Scientific invariants

Candidate E remains frozen:

- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- Champion-Final fingerprint: `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- primary prospective net-edge threshold: `$0.02`
- strategy reference quantity: `1` contract
- prospective duration: `168` consecutive hours
- no retuning during the window
- downtime does not create replacement events or an extended window

## Coinbase reference transport

Primary prospective transport is the public Coinbase Exchange BTC-USD WebSocket
using `matches` plus `heartbeat`.

Candidate-E semantics do not change. The required value remains the exact close
of the last fully completed UTC one-minute Coinbase candle. Prospectively this is
constructed as the last Coinbase match, by Coinbase source-event time, inside the
exact completed minute.

Heartbeat sequence and last-trade identity are continuity evidence. Any detected
gap makes the relevant BTC state unavailable until missing trades are recovered
from Coinbase REST and the exact minute can be reconstructed.

An exact 60-second REST candle may seed startup/reconnect state. It is not the
routine once-per-minute live transport.

There is no carry-forward, nearest-neighbor substitution, future interpolation,
or alternate-source substitution. A completed minute containing no Coinbase trade
has no candle and is therefore missing required Candidate-E state.

## Kalshi transport

Retain the validated authenticated production order-book WebSocket and entire
selected-event ladder subscription.

Any sequence discontinuity invalidates all subscribed books. No signal is eligible
until authoritative snapshots rebuild the full ladder.

## Runtime and durability

The permanent deployment has separate market/strategy, dashboard, and future
execution-worker services.

Every raw feed frame is appended and flushed before transformation. Active raw
journals receive an fsync at least once per second. Any future execution intent
requires an additional forced durability barrier for its causal raw evidence.

Raw journals rotate hourly, are losslessly compressed after closing, and retain
SHA-256 hashes for both uncompressed and compressed representations.

Operational state uses SQLite WAL. Execution-critical durable state uses FULL
synchronous durability.

After any restart, no signal may be emitted until clock health, exact Coinbase
state, Coinbase continuity, the exact Kalshi ladder, and durable strategy state
are all reconciled. Future execution additionally requires account/open-order/
position reconciliation before writes are possible.

## Clock

The Linux host uses chrony. Both UTC wall time and a monotonic clock are recorded.

New signals are disabled when measured absolute UTC clock offset is unknown or
greater than 250 ms.

## Deployment

Production-shaped runtime target: Linux cloud VM + Docker Compose.

AWS us-east-1 is the first region benchmark target because Coinbase documents its
US Spot WebSocket infrastructure there. No Kalshi hosting region is assumed.

The final host region must be selected in a separate outcome-blind connectivity
benchmark before the prospective cohort is armed.

Initial persistent-volume target is 100 GB. The actual minimum-free-disk gate must
be frozen after measuring live bytes/hour.

Closed raw segments are backed up remotely, but remote-backup latency is not in
the live decision path.

## Dashboard

The dashboard is a separate read-only service, targeted initially at Streamlit
with approximately one-second refresh.

It has no trading credentials, imports no execution adapter, exposes no write
actions, and must not affect the runtime if it fails.

Access is private via VPN or SSH tunnel rather than a public unauthenticated port.

## Future execution boundary

The strategy runtime never directly submits an order.

A later strategy/risk layer may create a durable OrderIntent. A separate execution
worker is the only process allowed to hold write capability.

Execution mode is fixed at process startup. Z-C requires `disabled`.

The intended future micro-production probe quantity is `0.01` contracts, but this
is a future target only and is not authorized by Z-C.

Ambiguous exchange write responses must never be blindly retried. Reconciliation
by durable request/order identity must occur first.

Scaling after a successful micro-production experiment changes execution quantity
and risk/capacity checks, not Candidate E. Larger size still requires new depth,
slippage, fee, and exposure validation.

## Explicitly unresolved

Before arming the 168-hour runtime:
- final cloud region;
- empirical storage-rate/free-disk threshold;
- Coinbase gap-recovery implementation validation;
- long-running restart/recovery validation;
- dashboard/runtime validation.

Before demo or production:
- exact order API contract;
- duplicate/ambiguous-order reconciliation;
- demo qualification pass gate;
- production capital/loss limits;
- explicit RISK_POLICY authorization amendment.

## Authorization

Current authorization remains read-only.

Orders: 0.
Production writes: 0.
Demo: not authorized.
Real-money execution: not authorized.

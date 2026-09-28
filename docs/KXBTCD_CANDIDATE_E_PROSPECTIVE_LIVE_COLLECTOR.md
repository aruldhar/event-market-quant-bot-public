# Checkpoint 21N-Z-B — Candidate-E Prospective Live Collector

## Scope

Z-B implements the first production live-data path for the frozen prospective
Candidate-E strategy. It is an **implementation and smoke-test checkpoint**, not
the 168-hour evidence run and not an execution checkpoint.

Production trading remains disabled.

## Kalshi transport

Use Kalshi's authenticated production WebSocket:

`wss://external-api-ws.kalshi.com/trade-api/ws/v2`

Only the `orderbook_delta` channel is allowed.

The implementation subscribes to the **entire market ladder for one selected
KXBTCD event**, rather than only the current ±5 ATM window. This intentionally
trades a small amount of extra market-data traffic for stronger causal coverage:
when Coinbase moves the ATM strike, the newly relevant markets are already being
tracked and do not require a late subscription.

The first `orderbook_snapshot` is authoritative. Subsequent
`orderbook_delta` messages update YES or NO bid levels. YES asks are derived from
NO bids as `1 - no_bid`, matching the project's existing book convention.

A sequence discontinuity invalidates every book in the subscription. No signal
may be emitted while the cache is invalid. The collector requests fresh
authoritative snapshots using only the documented `get_snapshot`
`update_subscription` action. It becomes decision-eligible again only after every
subscribed market has a fresh snapshot in the current recovery generation.

## Coinbase transport

Z-B's bounded smoke harness uses the public Coinbase Exchange BTC-USD 60-second
candle endpoint once per newly completed UTC minute and requires the exact target
minute. There is no nearest-neighbor, carry-forward, interpolation, or source
substitution.

This preserves the Candidate-E model feature semantics. The final 168-hour run is
not armed by Z-B; before arming, the project may separately decide whether to keep
this bounded minute-candle transport or replace only the transport with a
prospective Coinbase WebSocket minute builder while preserving the identical
completed-minute close definition.

## Timing

Every raw Kalshi WebSocket frame is timestamped immediately on local receipt with
both UTC wall time and `time.monotonic_ns()` and is appended to the raw journal
before JSON transformation.

Derived decision rows record:

- Kalshi receive monotonic timestamp;
- Candidate-E model-ready monotonic timestamp;
- signal-emission monotonic timestamp;
- feed-receive → model-ready duration;
- model-ready → signal-emission duration.

These measure the live data/decision pipeline. They are not order latency.

## Smoke role

After Z-B is safely closed, a bounded 5–300 second smoke may be run. Smoke output
is explicitly labeled:

`transport_and_decision_smoke_only_not_168h_evidence`

It does not arm or consume the frozen 168-hour prospective cohort.

## Safety

The implementation has:

- public GET market discovery;
- public GET Coinbase candle retrieval;
- authenticated Kalshi WebSocket handshake;
- `subscribe` to `orderbook_delta`;
- `update_subscription` only with `get_snapshot`.

It has no order endpoint, no cancel path, no portfolio mutation, no paper broker,
no demo orders, no real-money orders, and no P&L scorer.

## Live validation addendum ? 2026-09-03 local / 2026-09-04 UTC

Post-closeout live validation discovered and repaired two narrow production-schema mismatches:

1. `/markets?status=open` returns open KXBTCD market rows whose lifecycle field is `status="active"`.
2. An empty snapshot side may be omitted entirely. Omission only is normalized to an empty side; explicit invalid values remain fail-closed.

The smoke authorization gate was also changed from "latest closeout message must equal Z-B" to "closed Z-B receipt must remain in Git ancestry," allowing later legitimate repair/documentation checkpoints without disabling read-only validation.

Canonical successful in-window smoke:
`candidate_e_smoke_20260904T020640Z`

Evidence:
- 188 markets
- 11,502 Kalshi WS messages
- 2,890 decision calls
- 2,703 evaluable Candidate-E states
- 0 sequence gaps
- 0 orders
- 0 production writes
- Candidate-E live signal arithmetic independently reconciled to approximately `1e-17`

This validates the live signal pipeline but does not establish profitability or execution eligibility.

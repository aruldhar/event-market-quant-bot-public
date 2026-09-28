# KXBTC15M Settlement Validation

Last official-source and live-response review: 2026-08-03 local Pacific time / 2026-08-04 UTC.

## Scope

This document separates confirmed facts, bounded observations, hypotheses, and unresolved questions for the KXBTC15M contract family. No auxiliary BTC feed may be treated as settlement authority merely because it is convenient or highly correlated.

## Official authorities

- **Contract-rule authority:** Kalshi's written KXBTC15M rules, exposed on the market surface and in the public single-market REST response.
- **Numerical index authority:** CF Benchmarks BRTI.
- **Documented delivery channels:** Kalshi's authenticated CF Benchmarks REST passthrough and authenticated `cfbenchmarks_value` WebSocket channel.

A delivery channel does not replace the underlying numerical authority.

## Live representative contract

Ticker:

```text
KXBTC15M-26AUG040000-00
```

Observed public fields:

```text
open_time:       2026-08-04T03:45:00Z
close_time:      2026-08-04T04:00:00Z
expiration_time: 2026-08-11T04:00:00Z
status:          active
result:          ""
settlement_ts:   absent
```

Raw archive:

```text
data/raw/kalshi_rest/2026/08/04/kalshi_public_rest_20260804T035942758187Z_1b2d83a4.jsonl
```

The raw response was preserved through the existing public REST logger before its rule fields were inspected.

## Confirmed settlement logic

The live `rules_primary` text states, in substance:

```text
later_average >= earlier_average  -> Yes
```

where:

- `earlier_average` is the simple average of the sixty seconds of CF Benchmarks BRTI before market open;
- `later_average` is the simple average of the sixty seconds of CF Benchmarks BRTI before market close.

This confirms:

1. The comparison uses two distinct 60-second BRTI windows.
2. The later window is compared with the earlier window.
3. The operator is **at least**, or `>=`.
4. An exact tie resolves **Yes**.
5. For the observed contract, the rule's comparison times match `open_time` and `close_time`.
6. The one-week-later `expiration_time` is not the 15-minute comparison boundary.

The live `rules_secondary` text further states that 60 RTI prices are collected during the final minute and that the official final value is their average rounded to the nearest two decimal places.

## Official WebSocket averaging semantics

Kalshi's official `cfbenchmarks_value` WebSocket documentation states that:

- the channel requires an authenticated WebSocket connection;
- BRTI can be selected through `index_ids`;
- updates are emitted roughly once per second;
- duplicate or out-of-order upstream source timestamps are ignored;
- each message carries the raw upstream frame;
- `last_60s_windowed_average_15min` appears only during the final minute before a quarter-hour close;
- the active final-minute window is `(quarter_close - 60 seconds, quarter_close]`;
- the start-boundary tick is excluded;
- the close tick is included;
- the count reaches 60 on the close tick.

This documentation materially narrows the expected final-minute tick window. The project has not connected to the channel and has not operationally validated its payloads.

## What is validated

The following components are now supported by official evidence and the representative raw response:

- Kalshi is the written-rule authority.
- CF Benchmarks BRTI is the numerical index.
- The opening and closing operands are 60-second simple averages.
- The later average is compared with the earlier average.
- The operator is `>=`.
- A tie resolves Yes.
- The observed comparison boundaries align with `open_time` and `close_time`.
- The final-minute quarter-hour tick window is documented as start-exclusive and close-inclusive.
- The official final value is described as rounded to two decimal places.

## What remains unresolved

Complete executable replication is still blocked by insufficient official evidence for:

1. Whether both operands are rounded before comparison or only the later official final value is rounded.
2. The exact order of averaging, rounding, and comparison inside the settlement engine.
3. Treatment of corrected, revised, or late BRTI values.
4. Treatment of missing observations within either 60-second window.
5. Provider interruption or outage behavior.
6. Any official fallback source or fallback calculation.
7. Whether `last_60s_windowed_average_15min` is the exact settlement-engine value or a documented convenience calculation with the same window.
8. Field-level operational semantics for `received_at`, the upstream `data.time`, and reconnect continuity.
9. Whether authenticated access to the WebSocket channel is available under an appropriate future project authorization without additional entitlement.

## Facts, assumptions, hypotheses, and unresolved questions

### Facts

- The project currently collects only public Kalshi REST data.
- The representative response contains official rule text.
- The project has no API key, private key, or CF Benchmarks entitlement configured.
- No authenticated WebSocket or CF Benchmarks collector exists.
- No orders were placed during validation.

### Accepted assumptions

None are accepted as settlement logic.

### Hypotheses

- The documented WebSocket final-minute average may allow exact or near-exact replication of the closing operand in a later authorized phase.
- A public BTC spot feed may be useful as a predictive feature, but it is not settlement authority.

These are hypotheses to test, not profitability claims.

### Unresolved questions

The rounding, correction, missing-data, outage, fallback, exact-engine-equivalence, timestamp, and future-access questions listed above remain blockers.

## Decision boundary

The project may:

- continue public raw archival;
- inspect public active and settled market metadata;
- test schema and rule consistency;
- document authenticated sources without using them.

The project must not yet:

- generate settlement labels from an auxiliary exchange feed;
- claim exact BRTI settlement replication;
- add API credentials or authenticated WebSocket collection in this checkpoint;
- advance to paper-strategy eligibility;
- claim market edge or profitability.

## Next evidence checkpoint

The next public, read-only milestone should inspect a reproducible sample of settled KXBTC15M responses and verify result, settlement timestamp, expiration value, rule-template consistency, and lifecycle semantics before external-feed design.

## Official evidence reviewed

- `https://docs.kalshi.com/api-reference/market/get-market`
- `https://docs.kalshi.com/cfbenchmarks/rest-passthrough`
- `https://docs.kalshi.com/websockets/cfbenchmarks-value`
- `https://docs.kalshi.com/getting_started/quick_start_websockets`
- `https://www.cfbenchmarks.com/data/indices/BRTI`
- representative public market response for `KXBTC15M-26AUG040000-00`

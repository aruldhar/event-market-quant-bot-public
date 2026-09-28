# KXBTC15M Settlement Edge Cases

Status: checkpoint 06 design candidate; official-source review completed 2026-08-08 local Pacific / 2026-08-09 UTC. No authenticated source has been connected and no settlement-label implementation is authorized.

## Purpose

This document separates the settlement behavior that is actually supported by official evidence from behavior that remains unresolved for KXBTC15M.

The objective is not to force every question to a numerical answer. The objective is to make uncertainty explicit enough that later modeling and data collection fail closed instead of silently inventing settlement semantics.

## Authority layers

KXBTC15M settlement has several distinct layers. They must not be collapsed into one source.

1. **Contract-rule authority — Kalshi KXBTC15M written rules.**
   These rules define the market-specific comparison, timing boundaries, operator, and outcome treatment.
2. **Numerical index authority — CF Benchmarks BRTI.**
   CF Benchmarks defines how the underlying real-time index itself is calculated and disseminated.
3. **Official delivery channels — Kalshi CF Benchmarks REST passthrough and `cfbenchmarks_value` WebSocket.**
   These transport CF Benchmarks data through Kalshi. They do not become the numerical authority merely because they deliver the values.
4. **Auxiliary predictive/reference data — any exchange spot feed, Pyth feed, or other non-authoritative price source.**
   These may later be useful features. They may not be used to manufacture settlement labels unless the contract rules explicitly make them authoritative.

## Confirmed contract-level behavior

The project has preserved official KXBTC15M rule text in raw public Kalshi REST responses and validated one narrow structural rule template across the accepted settled-market sample.

Confirmed for the observed KXBTC15M rule family:

- the earlier operand is a simple average of sixty seconds of CF Benchmarks BRTI before market open;
- the later operand is a simple average of sixty seconds of CF Benchmarks BRTI before market close;
- the later operand is compared with the earlier operand using `>=`;
- an exact tie therefore resolves Yes;
- the embedded rule boundaries match the market's `open_time` and `close_time` in the validated sample;
- the observed secondary rule describes an official final value obtained from 60 RTI prices during the final minute and rounded to the nearest two decimal places.

The accepted public settled-market sample does **not** expose separately named opening and closing BRTI-average operands. `expiration_value` and `settlement_value_dollars` remain preserved source fields without inferred operand semantics.

## Confirmed Kalshi delivery behavior

Kalshi's current official `cfbenchmarks_value` WebSocket documentation establishes the following transport behavior:

- the WebSocket connection requires authenticated Kalshi API-key signing;
- BRTI can be selected by `index_ids`;
- value events are emitted roughly once per second;
- duplicate or out-of-order upstream source timestamps are ignored by Kalshi's feed;
- each update contains a raw upstream CF Benchmarks frame in `msg.data`;
- `msg.received_at` and the upstream `data.time` are distinct timestamps;
- each message also contains a WebSocket `seq` field;
- `last_60s_windowed_average_15min` is present only during the final minute before a quarter-hour boundary;
- that final-minute accumulation window is `(quarter_close - 60 seconds, quarter_close]`;
- the start-boundary tick is excluded and the close tick is included;
- documented second-indexed counts reach 60 on the close tick.

Kalshi separately documents `avg_60s_data` as a per-tick trailing convenience average. If that trailing window has no prior ticks, its average falls back to the current tick value.

**That `avg_60s_data` fallback is not evidence of a KXBTC15M settlement fallback.** The final-minute accumulator is a different field with different documented semantics, and the project must not transfer fallback behavior from one field to the other without official evidence.

## Confirmed CF Benchmarks provider behavior

The current CME CF Cryptocurrency Real Time Indices Methodology Guide reviewed for this checkpoint is version 16.8 dated 29 June 2026.

For the CME CF Bitcoin Real Time Index (BRTI), the methodology currently documents:

- Effective Time: every 200 milliseconds;
- Retrieval Lag Threshold: 10 seconds;
- standard dissemination: approximately every second at the top of the second;
- maximum dissemination: approximately every 200 milliseconds when requested;
- dissemination precision: 0.01 U.S. dollars.

These statements describe the provider's index calculation/dissemination layer. They do not prove that Kalshi consumes every 200 ms calculation for KXBTC15M settlement. Kalshi's own relay documents roughly one-second value events and the KXBTC15M rule evidence describes 60 RTI observations.

### Delayed constituent data

If a constituent exchange order book's Retrieval Time is more than the applicable Retrieval Lag Threshold behind the Calculation Time, CF Benchmarks disregards that constituent exchange for that calculation.

For BRTI the current threshold is 10 seconds.

If all constituent exchange order books exceed the threshold for a calculation time, an index calculation failure occurs for that calculation time.

### Erroneous and potentially erroneous constituent data

CF Benchmarks documents automated exclusion rules for unusable constituent order books, including malformed books, books without both bid and ask sides, crossed books, and potentially erroneous data under its methodology.

If all relevant constituent books are excluded for a calculation time, an index calculation failure occurs.

### Provider calculation failure

When the real-time index cannot be calculated for a calculation time, CF Benchmarks states that the index value for that calculation time is not published.

This answers the **provider-level** question of what happens to a failed BRTI calculation. It does not answer the **Kalshi contract-level** question of how a KXBTC15M 60-observation average is settled if one or more expected observations are absent.

### Amendments and delayed publication

CF Benchmarks' current value API documentation states that published index values may, in exceptional circumstances, be delayed or amended after publication. The value schema includes a conditional `amendTime` field.

The generic CF Benchmarks value schema also contains `repeatOfPreviousValue`. Its documentation is not sufficient to establish when or whether that condition applies to BRTI inside a KXBTC15M settlement window, especially because the current BRTI methodology separately says a failed real-time calculation is not published for that Calculation Time.

Therefore the project must preserve the generic API field as evidence but must **not** infer a BRTI settlement substitution rule from it.

## Edge-case status matrix

| Edge case | Provider-level status | Kalshi/KXBTC15M status | Decision consequence |
|---|---|---|---|
| Two 60-second comparison windows | N/A | Confirmed from official rule text | Eligible as documented rule input |
| Comparison operator and tie | N/A | `later >= earlier`; tie => Yes | Eligible as documented rule input |
| Final-minute 60-price average | BRTI provides the numerical values | Confirmed by Kalshi crypto documentation and KXBTC15M evidence | Eligible as documented rule input |
| BRTI constituent data delayed | Confirmed provider exclusion rule; BRTI threshold currently 10 s | Exact settlement handling of resulting missing RTI tick unresolved | Block exact settlement replication |
| BRTI constituent data erroneous | Confirmed provider exclusion/failure rules | Exact settlement handling of resulting missing RTI tick unresolved | Block exact settlement replication |
| BRTI calculation failure | Failed value is not published for that Calculation Time | Behavior of a 60-observation KXBTC15M window with an absent value unresolved | Block exact settlement replication |
| Published BRTI value amended later | Provider API supports amendments | Whether Kalshi revises a window/settlement operand and at what cutoff unresolved | Block exact settlement replication |
| Late BRTI publication | Provider API allows exceptional delay | Inclusion/exclusion rule in KXBTC15M window unresolved | Block exact settlement replication |
| Fewer than 60 final-minute observations | Possible consequence of missing/delayed values | No KXBTC15M-specific fallback found in reviewed official sources | Block exact settlement replication |
| `avg_60s_data` empty-history fallback | Kalshi relay documents current-tick fallback for this convenience field | Not documented for settlement accumulator | Must not transfer fallback semantics |
| Quarter-hour accumulator boundaries | N/A | `(close-60s, close]`, start excluded, close included | Documented delivery behavior only |
| Duplicate upstream source timestamp | N/A | Kalshi relay ignores duplicate timestamp | Future collector must preserve raw evidence and account for dropped duplicate |
| Out-of-order upstream source timestamp | N/A | Kalshi relay ignores out-of-order timestamp | Future collector must preserve raw evidence and account for dropped item |
| WebSocket sequence gap | `seq` is present in Kalshi messages | No reviewed source establishes a replay/resume guarantee for this channel | Future collector must fail closed across unexplained gaps |
| WebSocket disconnect/reconnect | N/A | General Kalshi guidance recommends reconnect; exact BRTI continuity semantics unresolved | Future collector cannot assume continuity after reconnect |
| Opening operand rounding | N/A | Exact treatment unresolved | Block exact settlement replication |
| Closing operand rounding | Observed secondary rule describes final value rounded to two decimals | Whether the value compared by settlement engine is pre- or post-rounding remains unresolved | Block exact settlement replication |
| Order of average -> rounding -> comparison | N/A | Not fully established | Block exact settlement replication |
| Same rounding rule for both operands | N/A | Not established | Block exact settlement replication |
| Official fallback source | N/A | No KXBTC15M-specific fallback found in reviewed official sources | No substitute permitted |
| `last_60s_windowed_average_15min` equals settlement-engine operand exactly | N/A | Plausible but not officially established under edge conditions | Treat as hypothesis only |
| `expiration_value` equals one comparison operand | N/A | Not established by public settled-market fields | Do not infer |
| `settlement_value_dollars` equals one BRTI operand | N/A | Not established; field belongs to binary-market settlement surface | Do not infer |

## Access-path review

The reviewed official access paths do not provide a new public unauthenticated way to collect authoritative BRTI values:

### Kalshi `cfbenchmarks_value` WebSocket

- authenticated Kalshi WebSocket handshake required;
- current project authorization does not permit credentials;
- no collector is implemented.

### Kalshi CF Benchmarks REST passthrough

- authenticated Kalshi Trade API request required;
- account must have the appropriate entitlement;
- current project has neither authorized credentials nor confirmed entitlement;
- passthrough errors can map upstream authorization/server/timeout conditions to `503 service_unavailable`.

### Direct CF Benchmarks API / WebSocket

- requires a CF Benchmarks API key obtained through a license;
- current project has no such license or key;
- direct access is therefore a documented future option, not a current collection path.

### Auxiliary feeds

Kalshi also documents other price feeds such as a Pyth WebSocket channel, and public exchange spot feeds exist outside Kalshi. They are not KXBTC15M settlement authority under the reviewed rule evidence. They belong only in the auxiliary predictive/reference class unless a future contract rule explicitly says otherwise.

## What is still unresolved after this checkpoint review

The following remain genuine blockers rather than missing research effort that can safely be guessed away:

1. Exact opening-operand rounding treatment.
2. Exact closing-operand rounding treatment at the settlement-engine comparison step.
3. Exact average/round/compare operation order.
4. Whether both operands use identical rounding.
5. Kalshi treatment of an amended BRTI observation after initial receipt.
6. Kalshi treatment of a late observation whose source timestamp belongs inside a settlement window.
7. KXBTC15M behavior when one or more expected observations are absent.
8. KXBTC15M provider-outage behavior and any contract-specific fallback.
9. Exact equivalence between the documented WebSocket final-minute average and the settlement engine under amendments, missing observations, reconnects, or source interruptions.
10. Replay or continuity guarantees for `cfbenchmarks_value` after a sequence gap or reconnect.
11. Whether authenticated access to the Kalshi CF Benchmarks WebSocket is available to the user's account without an additional entitlement.

## Fail-closed interpretation

Until these unresolved items are either officially documented or bounded by a later explicitly accepted research assumption, the project must not:

- generate authoritative historical KXBTC15M settlement labels from an exchange spot feed;
- treat a Kalshi convenience average as proven settlement-engine state;
- fill missing BRTI ticks with the previous tick, next tick, interpolation, exchange spot, Pyth, or cached data;
- retroactively rewrite an archived source observation because an amendment later appears without preserving both versions and the amendment relationship;
- assume a reconnect has no missing data;
- claim exact settlement replication.

Public market-data collection may continue for engineering research. Settlement-dependent model or execution decisions remain blocked.

## What evidence would resolve the remaining questions

A future resolution should come from one or more of the following, in descending authority order:

1. explicit KXBTC15M contract-rule text covering the edge case;
2. explicit Kalshi documentation specific to crypto settlement or the `cfbenchmarks_value` settlement use;
3. an official Kalshi clarification that can be preserved as project evidence;
4. authenticated raw BRTI delivery plus settled-market observations, used only to test a documented rule rather than invent one;
5. a predeclared research assumption, clearly marked as non-authoritative, only if the project later chooses to study sensitivity rather than produce official settlement labels.

## Official sources reviewed

- Kalshi Crypto Markets: `https://help.kalshi.com/en/articles/13823838-crypto-markets`
- Kalshi CF Benchmarks Value Feed: `https://docs.kalshi.com/websockets/cfbenchmarks-value`
- Kalshi CF Benchmarks REST Passthrough: `https://docs.kalshi.com/cfbenchmarks/rest-passthrough`
- Kalshi Quick Start: WebSockets: `https://docs.kalshi.com/getting_started/quick_start_websockets`
- Kalshi Market Outcomes: `https://help.kalshi.com/en/articles/13823826-market-outcomes`
- CF Benchmarks CME CF Cryptocurrency Real Time Indices Methodology Guide, v16.8, 29 June 2026: `https://docs.cfbenchmarks.com/CME%20CF%20Real%20Time%20Indices%20Methodology.pdf`
- CF Benchmarks recent published index values API: `https://docs.cfbenchmarks.com/api/rest/values/`
- CF Benchmarks WebSocket value channel: `https://docs.cfbenchmarks.com/api/websocket/value/`
- CF Benchmarks REST API authentication: `https://docs.cfbenchmarks.com/api/`
- CF Benchmarks WebSocket API authentication: `https://docs.cfbenchmarks.com/api/websocket/intro/`
- Existing project evidence: `docs/SETTLEMENT_VALIDATION.md` and `docs/SETTLED_MARKET_EVIDENCE.md`

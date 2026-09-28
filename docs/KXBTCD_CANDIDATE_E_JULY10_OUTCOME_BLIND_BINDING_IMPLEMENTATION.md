# KXBTCD Candidate-E July 10 Outcome-Blind Binding Implementation

## Checkpoint

**21N-S-A — Outcome-Blind Real-Data Binder Implementation Freeze**

This checkpoint freezes the code that will bind the already-owned July 10, 2026 KXBTCD evidence to the frozen Candidate-E executable convergence/liquidation simulator. It intentionally stops before running the real strategy-signal and execution-path materialization.

The separation is deliberate: the implementation is committed before any July 10 signal/path diagnostics are exposed, so those diagnostics cannot influence the binding rules.

## Parent contracts

The binder inherits without modification:

- Candidate-E Champion-Final: `kxbtcd_btc_distance_offset_logistic.v1`
- Champion-Final fingerprint: `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- strategy predeclaration fingerprint: `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`
- fixed-point fee-accounting amendment fingerprint: `5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`
- 21N-R simulator implementation fingerprint: `6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf`
- 21N-R checkpoint commit: `9c58d63e9faab98b486fdcbc374605abd1115d82`
- 21N-R receipt commit: `b6ec6226374f90bae63784aee8cda28b81e7d67b`

The binder calls the frozen 21N-R structural-role selector, Candidate-E signal builder, event signal selector, and scenario simulator. It does not reimplement or tune those rules.

## Frozen local evidence contract

The following already-owned local inputs are pinned before the materialization run:

| Evidence | SHA-256 / count |
| --- | --- |
| July 10 BTC materialization | `022f6c6ce1b697bc67f7137f73e3f18cc0fe0198b347e5154a3063107299fb12` |
| paid Predexon order-book-delta shard | `43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509` |
| full-ladder replay `summary.json` | `b37ba7132baf086887e4b33e7c11e9de59decc5f0b387d7e6e5352a2570ebb48` |
| independent events | 4 |
| full-ladder tickers | 623 |
| paid deltas | 5,644,964 |
| free snapshots | 269,441 |
| adjacent replay pairs | 268,818 |
| exact pairs | 266,034 |
| unreconciled pairs | 2,784 |
| BTC decision anchors | 24 |
| structural role/anchor states to bind | 120 |

The observed file-level contract is also frozen: 623 paid tickers, 623 per-ticker replay artifacts, and 623 raw snapshot-backfill files must have exactly identical ticker sets.

Event ladder sizes remain:

- `KXBTCD-26JUL1013`: 78
- `KXBTCD-26JUL1014`: 188
- `KXBTCD-26JUL1015`: 188
- `KXBTCD-26JUL1016`: 169

## Binding rules

### 1. Full-ladder structural roles

The binder parses the numeric `-T...` threshold from the complete 623-ticker frozen July 10 ladder and delegates to the frozen 21N-R `select_structural_markets` function. Exactly five markets per event are selected: q10, q30, q50, q70, and q90.

This is a structural strike-quantile role. It is not a confidence score.

### 2. BTC decision state

For each of the 24 frozen anchor rows:

- `coinbase_current_price` is the Candidate-E BTC spot input;
- `decision_time_utc` is converted exactly to epoch milliseconds;
- `event_close_time_utc` is the monitoring end;
- the exact difference between close and decision time must equal the declared TTC anchor;
- all 24 BTC rows must remain source-eligible;
- no interpolation, nearest-minute replacement, carry-forward, or alternate BTC source substitution is allowed.

### 3. Verified book timeline

Only the 20 selected structural tickers are fully loaded into execution timelines. For each ticker:

1. the existing raw free snapshot-backfill JSONL is loaded through the established backfill loader;
2. the ticker's paid deltas are read from the pinned parquet shard in timestamp/sequence order;
3. the frozen 21N-R replay builder reconstructs the right-continuous millisecond timeline;
4. runtime verified-segment boundaries must exactly match the previously frozen per-ticker replay audit artifact.

A decision timestamp outside one verified segment is source-unavailable. The binder does not interpolate a book, jump a gap, use a nearby timestamp, or proxy another strike.

### 4. Signal materialization

Each event has six TTC anchors and five structural roles, producing exactly 120 structural role/anchor states before quote/depth eligibility.

At an eligible state the binder calls the frozen 21N-R `build_signal_candidates` function. Therefore the existing rules remain unchanged, including valid uncrossed two-sided YES book, one-contract decision-level depth, exact Candidate-E probability, fixed-point entry fee, and YES/NO post-fee edge.

Invalid or unavailable states are recorded as diagnostics rather than imputed.

### 5. Event selection and execution paths

For each event and each frozen threshold `0/1/2/3/5c`, the binder calls the frozen `select_event_signal`. For every selected signal it evaluates the frozen `0/500/1000 ms` scenarios with `simulate_scenario`.

This creates settlement-blind execution diagnostics such as:

- source availability across latency;
- full, partial, or missed entry IOC;
- fixed-point fees and cash changes for observed counterfactual fills;
- convergence-liquidation trigger status;
- full, partial, or missed exit IOC;
- remaining open quantity that would later require settlement;
- matched-hold open quantity.

The quantities named `settlement_fallback_quantity` and `matched_hold_settlement_quantity` are position quantities only. They do not contain a settlement label or settlement value.

## Execution-model assumptions retained from 21N-R

Two important assumptions remain explicit:

1. **Same-millisecond convention:** only the final reconstructable right-continuous state for a millisecond is exposed. Same-ms transients are not exploitable.
2. **Small-order non-impacting future-book assumption:** the hypothetical IOC consumes visible arrival depth for that IOC, but later historical books remain the observed exogenous path. This is a counterfactual modeling assumption, not an observed market-impact claim.

Aggregate price levels also do not reveal true queue ownership or resting-order partitioning. One synthetic fill per consumed price level remains the deterministic approximation frozen by the fee-accounting amendment.

## Outcome and P&L firewall

21N-S-A contains no settlement-label input and no realized-P&L function.

The materialization output is rejected if exact dangerous keys such as `outcome`, `winner`, `settlement_value`, `pnl`, `realized_pnl`, `profit`, or `loss` appear. Safety metadata must state:

- outcomes accessed: false;
- strategy P&L calculated: false;
- Candidate E refit: false;
- network requests: 0;
- Predexon purchases: 0;
- orders placed: 0;
- paper/demo/real-money execution: false.

## Determinism

The output is canonical JSON with no run timestamp. If an output file already exists, the materializer will overwrite it only when the regenerated bytes are identical. A non-identical existing artifact causes a fail-closed error.

## Interpretation boundary

The July 10 shard contains only four independent hourly events. Even after 21N-S-B runs, its signal and execution-path diagnostics are methodology/debug evidence only. They cannot validate profitability, select a threshold, justify strategy tuning, or advance the project toward production.

## Next checkpoint

After this implementation freeze is committed and remotely closed:

**21N-S-B — July 10 Outcome-Blind Strategy Input and Execution-Path Materialization Run**

21N-S-B may run the frozen binder on the real July 10 evidence. Outcomes must remain closed, realized P&L must remain unrun, and no strategy rule may be tuned from the resulting path diagnostics.

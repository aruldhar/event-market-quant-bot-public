# KXBTC15M Intramarket Reversion Research Design

Status: **discovery / public read-only collection**

This document records the working design for the KXBTC15M intramarket-reversion branch. It does not claim predictive edge or profitability and does not authorize authentication, paper execution, demo execution, or real-money trading.

## Research question

Across a KXBTC15M market's full active lifetime, when a contract side becomes sharply discounted, under what observable conditions does its executable price subsequently rebound enough to support a positive *simulated* liquidation after realistic spread, depth, fees, latency, partial fills, and missed fills?

The original five-minute cutoff is intentionally removed. Time remaining is an explanatory variable to measure, not a preselected trading window.

## Discovery hypothesis H1

> During some KXBTC15M market states, a sharply discounted side exhibits short-horizon executable-price reversion. The probability, magnitude, and speed of that reversion depend on time remaining, market path/state, underlying BTC state, spread, and available depth.

This is a hypothesis to falsify. A falling price alone is not an entry rule.

## Continuous collection architecture

The first automation reuses the repository's already validated components rather than introducing a second data path:

1. `scan_btc_markets.py` discovers the currently open KXBTC15M contract.
2. `record_orderbook.py` records that contract at the requested REST cadence through its documented close boundary plus a short diagnostic grace period.
3. `validate_run_manifest.py` validates the completed market capture.
4. The process repeats for a bounded number of markets.

`record_btc15m_continuous.py` is therefore an orchestration layer, not a new Kalshi API client. Every underlying scan and order-book run retains its existing raw archives, runtime events, run manifest, hashes, and order-book raw-to-derived lineage.

### Rollover rule

Do **not** use one blank order book as the sole rollover trigger.

A temporary empty or one-sided book before close can be economically meaningful and must be preserved rather than silently interpreted as a new contract. The controller uses the source-reported `close_time` as the primary boundary, records a small post-close grace interval, validates the run, and then discovers the next currently open market.

Post-close blank quotes remain useful evidence of the lifecycle transition, but they are a diagnostic rather than the only clock.

## Initial collection cadence

- KXBTC15M only.
- Public unauthenticated market-data endpoints only.
- Default order-book polling interval: 0.5 seconds.
- Full raw order-book response preserved before transformation.
- Existing best bid/ask CSV remains a lightweight derived view; full depth remains in raw data.
- Each market recording is independently manifested and validated.
- The orchestration is bounded by `--markets`; there is no unbounded daemon mode in this version.

The 0.5-second cadence is a discovery baseline, not a statement that production execution can react at that latency.

## Market-state idea

The user's qualitative states—"increasing", "decreasing", and "fluctuating"—should initially be derived **offline**, not embedded in the collector. That avoids forcing arbitrary state thresholds into the data-generation process.

A simple candidate representation is directional efficiency over a trailing window.

Let executable contract price observations be `p_0, ..., p_n`.

```text
net_move   = p_n - p_0
path_length = sum(abs(p_i - p_(i-1)))
```

When `path_length > 0`:

```text
signed_directional_efficiency = net_move / path_length
```

Properties:

- near `+1`: mostly one-way increase;
- near `-1`: mostly one-way decrease;
- near `0`: substantial back-and-forth relative to net displacement.

This does **not** yet freeze label thresholds. Development data must show whether useful state separation exists before a versioned classifier is defined.

Additional candidate state descriptors can remain simple:

- trailing high-low range;
- realized absolute movement;
- number of direction changes;
- spread distribution;
- time spent with two-sided executable liquidity;
- drawdown from recent local high;
- rebound from recent local low;
- time remaining.

## Previous-market state as a candidate feature

Because BTC is a continuous underlying process while KXBTC15M contracts reset every 15 minutes, the previous market's terminal path may contain information about the next market's opening regime. Examples include persistent momentum versus choppy conditions.

That is **not yet an accepted predictive fact**.

If tested later:

- only information available before or at the next market observation may be used;
- chronological market-level splits are required;
- previous-market summaries must be frozen before holdout evaluation;
- the previous contract's probability cannot be treated as directly comparable to the next contract because the settlement reference resets;
- an external BTC reference feed may later be required to distinguish event-contract repricing from actual underlying directional movement.

## What the first continuous sample is for

The initial multi-market run is engineering/discovery evidence. It should establish:

- clean automatic rollover;
- near-complete market coverage after the first partial market;
- stable 0.5-second polling behavior;
- valid manifests and raw lineage for every market;
- frequency of empty/one-sided books;
- whether large rebound episodes recur across independent 15-minute settlement periods.

Do not optimize entry prices, averaging sizes, stop thresholds, or profit targets against the first few collected markets.

## Later economic simulation requirements

Before H1 can become a paper-strategy candidate, simulated entries/exits must account for at least:

- executable ask on entry;
- depth-adjusted fills rather than top-of-book fantasy size;
- executable bid on liquidation;
- fees applicable to the specific series/market;
- latency;
- partial fills and missed fills;
- spread widening during fast moves;
- stale/gapped data shutdown;
- bounded position inventory;
- no martingale or loss-chasing sizing;
- model/estimation uncertainty.

## Immediate next validation

Install the implementation bundle, run the targeted unit tests, then run a small bounded live capture such as two markets. Validate that both market recorders complete and that the controller transitions to the next ticker automatically.

## Continuous unattended collection

The continuous orchestration layer supports `--continuous` to roll across
successive KXBTC15M markets until interrupted with Ctrl+C. On Windows it
requests that the operating system remain awake while the collector is active;
the display may still turn off. Explicit sleep/hibernate/shutdown, lid-close
behavior, power loss, and network loss are outside the process's control.

In continuous mode, market-discovery failures are retried indefinitely so a
transient connectivity interruption does not terminate the whole session.
No data is synthesized for an outage. A child recorder failure or manifest
validation failure remains terminal: the orchestration stops rather than
silently treating an incomplete market as complete.

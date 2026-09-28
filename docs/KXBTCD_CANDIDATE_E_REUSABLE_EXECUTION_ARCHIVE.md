# Checkpoint 21K-B1 — Reusable Candidate-E Historical Execution Archive Contract

## Purpose

Freeze the collection scope for a one-time, reusable historical execution archive **before the first 21K-B API request and before any strategy P&L is calculated**.

Archive ID: `kxbtcd_candidate_e_reusable_execution_archive.v1`

Archive predeclaration fingerprint:

`4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`

Allow-list fingerprint:

`85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`

## Facts already established

The archive universe contains:

- 4,070 OOS/OOF Candidate-E events
- 20,236 unique KXBTCD markets
- 118,862 prediction rows
- zero cross-stage event overlap
- zero cross-stage market overlap

The 4,676-event untouched historical reserve remains excluded.

## Collection design

For every allow-listed market, preserve the available **full tradable lifecycle** from `open_time` through `close_time`, rather than only Strategy-v1's six signal anchors.

The reusable archive includes:

1. market metadata;
2. one-minute YES bid / YES ask / price candlesticks;
3. reported one-minute volume and open interest;
4. all available public trades during the lifecycle, preserving block-trade flags;
5. dynamic historical-cutoff snapshots;
6. KXBTCD series metadata and full historical series-fee changes;
7. fee-change history for each allow-listed event.

This lets later separately versioned strategies reuse the same offline archive when their required inputs fall within this scope.

## Historical/live routing

Kalshi partitions markets/candlesticks and trades between live and historical tiers using moving cutoff timestamps. The collector must not hard-code a cutoff.

Market metadata must reconcile every allow-listed ticker to exactly one current tier. Candlestick routing follows that tier. If the tier moves during a long collection, the collector raw-preserves the failed attempt, refreshes routing state, and retries only on the correct tier.

Trade collection routes using the current `trades_created_ts` cutoff. A lifecycle that straddles the cutoff is collected from both tiers and deduplicated by `trade_id`.

## Fee implementation clarification

Strategy v1 already requires the exact applicable historical fee. Official Kalshi event metadata and the event-fee-change API document event-level fee overrides layered on the parent series fee schedule.

Therefore the archive collects both:

- parent KXBTCD series fee history;
- event-level fee-change history for the 4,070 allow-listed events.

When an event override is active it takes precedence over the parent series fee. A null override clears the event override.

This is an execution-cost implementation clarification, **not a change to Strategy v1's entry/exit, threshold, sizing, or model rules**.

## Raw-first rule

Every HTTP response, including errors used for routing recovery, must be preserved before semantic use. Raw records carry request identity, parameters, route, UTC and monotonic timing, status, byte count, and SHA-256.

## Interpretation boundary

This archive cannot prove historical queue position or full depth. One-minute candles and trades support coarse execution replay only.

No P&L scoring is authorized in 21K-B1. No model refit, candidate redesign, paper broker, demo order, or real-money order is authorized.

After archive materialization is complete, coverage/missingness must be validated before Strategy v1 is scored.

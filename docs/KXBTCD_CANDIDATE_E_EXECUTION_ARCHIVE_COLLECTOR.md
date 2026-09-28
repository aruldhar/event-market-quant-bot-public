# Checkpoint 21K-B2 — Raw-first Resumable Archive Collector

## Goal

Implement the read-only collector for the frozen
`kxbtcd_candidate_e_reusable_execution_archive.v1` contract without changing
Strategy v1 and without calculating strategy P&L.

Frozen archive fingerprint:

`4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`

Frozen allow-list fingerprint:

`85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`

## Design

### Raw data remains the source of truth

All Kalshi responses continue through the project's existing
`PublicCensusHttpClient`, which writes the original HTTP exchange to the
append-only raw JSONL archive before returning the parsed payload.

### SQLite is only a resume index

A local ignored SQLite file records a task only after the complete response
chain has passed structural/identity checks. This gives crash-safe transactional
resume semantics without replacing the immutable raw archive.

If collection stops, rerunning the same scope revalidates the frozen archive
and allow-list fingerprints and skips only tasks already committed as complete.

### Task boundaries

- one current cutoff snapshot per run, plus periodic refreshes;
- one KXBTCD series/series-fee bundle;
- one event/event-fee-history bundle per selected event;
- deterministic batches for live/historical market metadata reconciliation;
- one full-lifecycle 1-minute candle task per market;
- one complete paginated trade task per market.

A trade task is not marked complete until its cursor chain ends normally.
Repeated cursors fail closed. If a market lifecycle straddles the current trade
cutoff, both historical and live trade tiers are queried and deduplicated by
`trade_id`.

### Dynamic market routing

Market metadata is reconciled against the live and historical tiers. For a
previously cached market on resume, `settlement_ts` is compared with the
fresh cutoff so a market that migrated from live to historical is routed to
the current candle tier rather than trusting a stale cached route label.

### Smoke first

`--max-markets N` creates an explicitly non-full deterministic smoke scope. It
uses the same frozen allow-list, raw-first HTTP path, validation, resume logic,
and output schemas, but cannot be interpreted as archive completion.

The first live run should use a very small smoke cap. The full 20,236-market
run is not the first network test.

## Outputs

When a scope completes, the collector materializes:

- archive allow-list CSV;
- market metadata CSV;
- 1-minute candle CSV;
- public trades CSV;
- event metadata CSV;
- event fee-change CSV;
- KXBTCD series metadata CSV;
- KXBTCD series fee-change CSV;
- per-market coverage CSV.

Missing candle periods are counted explicitly and never imputed.

## Safety

This implementation exposes only public GET routes used by the frozen archive.
Paths containing portfolio, orders, order groups, communications, or transfers
are explicitly rejected by the collector wrapper.

No model refit, Strategy-v1 mutation, reserve access, P&L calculation, paper
broker, demo execution, or real-money execution is performed.


## Resume-lineage amendment discovered by smoke testing

The first five-market smoke run intentionally resumed work from an earlier
failed run. It exposed a receipt-level issue: derived rows correctly retained
their original `raw_session_id` and `raw_request_id`, but the completed run
manifest initially inventoried only the newest run's raw JSONL file.

The collector now maintains a transactional raw-session index inside the
resume database. Legacy v1 resume databases are migrated in place to v2 by
digest-validating cached task payloads and backfilling all locally generated
raw session references.

Before a successful manifest is finalized:

1. every contributing/resume raw session is enumerated;
2. every matching raw JSONL file is discovered, including multiple files if a
   session spans UTC midnight;
3. a missing contributing raw file fails closed;
4. all inherited plus current source sessions are included in the manifest;
5. all contributing raw files are passed through the existing manifest
   integrity inspection.

This changes lineage accounting only. It does not alter archive scope,
strategy rules, market/candle/trade interpretation, or authorization.

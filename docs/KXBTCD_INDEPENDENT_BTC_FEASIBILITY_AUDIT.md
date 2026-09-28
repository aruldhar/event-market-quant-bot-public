# KXBTCD Independent-BTC Feasibility Audit

**Checkpoint:** 19B
**Date:** 2026-08-15
**Status:** IMPLEMENTATION FREEZE — BOUNDED OUTCOME-BLIND PILOT ONLY
**Parent protocol:** `kxbtcd_successor_research_protocol.v1`
**Parent protocol fingerprint:** `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
**Audit design fingerprint:** `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`

## Purpose

Checkpoint 19A established that the next KXBTCD successor eligible for advancement must add at least one contemporaneous BTC-state signal independent of Kalshi's own market probability. Checkpoint 19B does **not** choose that feature or fit Candidate E.

This checkpoint freezes and tests the smallest raw-first collection path needed to answer a narrower engineering question:

> Can public Coinbase and Kraken BTC observations be attached to open KXBTCD states with auditable first-seen timing, raw lineage, and five-minute causal-history coverage without opening outcomes?

A PASS means only that the instrumentation is technically usable for a longer outcome-blind evidence collection. It does not establish predictive value, select a model, or establish profitability.

## Frozen bounded-pilot design

The first pilot is exactly:

- duration: `420` monotonic seconds;
- Coinbase/Kraken sampling target: every `2` seconds;
- open-KXBTCD sampling target: every `10` seconds;
- external request order: alternate Coinbase-first and Kraken-first by cycle;
- KXBTCD request order: request KXBTCD only after both current-cycle external attempts;
- five-minute history coverage horizon: `300` seconds;
- source failure guard: abort after more than `5` consecutive failures for one required source path;
- missed cycles are not burst-replayed.

The 420-second duration is an engineering minimum chosen before outcome access so the pilot can contain a full five-minute first-seen history plus post-warmup KXBTCD states. It is not an E1, E2, or E3 sample-size choice and is not enough to establish representative calendar coverage.

Changing these frozen pilot parameters requires a new audit-design fingerprint. The command-line collector intentionally exposes no cadence/duration override.

## Source objects

### Coinbase

Engineering endpoint:

- owner: Coinbase;
- API family: Coinbase Exchange public REST;
- instrument: `BTC-USD`;
- request: `GET https://api.exchange.coinbase.com/products/BTC-USD/book?level=1`;
- diagnostic object: best bid / best ask midpoint;
- source timestamp: response `time`;
- provisional source ID: `coinbase.exchange.public_rest.product_book.btc_usd.provisional_19b`.

Coinbase's official Exchange API documents the product-book endpoint, `level=1` best bid/ask, `sequence`, and `time`, and states that level 1/2 are appropriate for polling. The raw response remains authoritative for this pilot; the derived midpoint is only a feasibility diagnostic.

### Kraken

Engineering endpoint:

- owner: Kraken;
- API family: Kraken Spot public REST;
- instrument: `BTC/USD`;
- request: `GET https://api.kraken.com/0/public/PreTrade?symbol=BTC/USD`;
- diagnostic object: best bid / best ask midpoint;
- source timestamp: later of the best-bid and best-ask `publication_ts` values;
- provisional source ID: `kraken.spot.public_rest.pretrade.btc_usd.provisional_19b`.

Kraken's official Pre-Trade Data documentation describes aggregated order-book price levels and a `publication_ts` for each level. The raw response remains authoritative for this pilot.

### Kalshi KXBTCD

Engineering endpoint:

- owner: Kalshi;
- request: public `GET /markets`;
- filters: `series_ticker=KXBTCD`, `status=open`, `mve_filter=exclude`, `limit=1000`;
- derived state fields: event ticker, market ticker, close time, strike, yes bid/ask midpoint, spread;
- any non-empty pagination cursor fails closed because a partial KXBTCD ladder is not accepted.

The Kalshi response may contain fields that are downstream or outcome-related in other lifecycle states. The 19B materializer uses an explicit allow-list and never copies `result`, settlement values, labels, predictions, scores, or execution fields into the feasibility artifact.

## Timing and causality

The existing `docs/TIME_ALIGNMENT_POLICY.md` remains controlling.

For an external observation to be attached to a KXBTCD state:

```text
external.local_receive_monotonic_ns
    <= kalshi_snapshot.local_receive_monotonic_ns
```

The collector enforces this structurally by requesting KXBTCD only after the current external attempts. The materializer checks the monotonic inequality again.

Source timestamps are preserved separately for source semantics and diagnostics. Each `*_age_seconds` field is computed from the same-machine local monotonic difference between the external observation's first-seen receipt and the later KXBTCD receipt. It is therefore a local first-seen age diagnostic, not a frozen staleness threshold. Because absolute cross-clock comparison remains uncertain, an apparently future source timestamp is not clamped; the external observation is marked unavailable for that row and the original payload remains in raw storage.

No sub-second lead/lag feature or claim is authorized.

## Five-minute lookback coverage

The pilot records only a structural boolean:

```text
five_minute_lookback_available_<source>
```

It is true when the process had already received at least one observation from that source at least 300 monotonic seconds before the KXBTCD state.

This does **not** define a future five-minute-return feature. Checkpoint 19B does not freeze a nearest-neighbor tolerance, interpolation rule, return formula, or sampling alignment for Candidate E.

## Descriptive outputs

The collector writes:

1. `feasibility_rows.csv` — protocol-valid KXBTCD/source rows;
2. `structural_exclusions.csv` — KXBTCD market states excluded before protocol-row creation;
3. `summary.csv` — descriptive availability/timing coverage only;
4. raw JSONL archives for Coinbase, Kraken, and Kalshi;
5. the normal run manifest and runtime-event log.

The summary may describe:

- request success rates;
- row-level source availability;
- both-source availability;
- five-minute history coverage;
- local first-seen age distributions;
- cross-source midpoint disagreement in basis points;
- external local-receive skew;
- KXBTCD event/market/TTC coverage.

It may not score outcomes, fit a candidate, choose a threshold, or select a model.

## What remains deliberately unfrozen

Checkpoint 19B does **not** freeze or select:

- the E1 production source ID or source combination;
- a source staleness threshold;
- a cross-source disagreement threshold;
- a Coinbase/Kraken consensus-price formula;
- Candidate E's feature set or formula;
- a five-minute return formula;
- regularization or tuning grids;
- E1/E2/E3 event counts;
- E1/E2/E3 calendar coverage;
- an advancement gate;
- an E3 terminal cohort.

The bounded 420-second pilot is too short to justify those decisions. If the pilot validates the instrumentation, the next research step is a separately frozen longer outcome-blind availability collection before any Candidate-E fitting.

## Failure behavior

The audit fails closed on conditions including:

- raw persistence failure;
- malformed source response;
- invalid BBO;
- local monotonic time reversal;
- external observation locally received after the KXBTCD state;
- partial/paginated KXBTCD ladder;
- repeated required-source failures beyond the frozen guard;
- zero protocol-valid KXBTCD feasibility rows.

A source timestamp that appears later than the KXBTCD local wall-clock `as_of_utc` is retained raw but treated as unavailable in the derived row; it is not silently corrected.

## Safety boundary

- outcome access: prohibited;
- Candidate-E fitting: prohibited;
- Candidate-E formula freeze: prohibited in this checkpoint;
- Checkpoint-17 terminal use: prohibited permanently;
- paper execution: prohibited;
- demo execution: prohibited;
- real-money execution: prohibited;
- order creation/cancellation/transfers: prohibited.

## Official API documentation reviewed

- Coinbase Exchange — Get product book: `https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-book`
- Kraken Spot REST — Pre-Trade Data: `https://docs.kraken.com/api/docs/rest-api/get-pre-trade`
- Kalshi — Get Markets: `https://docs.kalshi.com/api-reference/market/get-markets`

<!-- CHECKPOINT19B_PILOT_RESULT_20260816 -->
## Bounded pilot result

The first exact frozen 420-second audit run is recorded in `docs/KXBTCD_INDEPENDENT_BTC_FEASIBILITY_PILOT_RESULT.md`.

Result: **PASS for engineering feasibility only**.

The pilot demonstrated complete bounded-window availability and structurally valid causal alignment, but its seven-minute / three-event coverage is insufficient to freeze permanent source-quality thresholds, candidate formulas, or future evidence cohort sizes. A longer outcome-blind availability audit is required before E1.

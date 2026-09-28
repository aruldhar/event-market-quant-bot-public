# KXBTCD Pre-Outcome Historical Collector

Status: **Checkpoint 12 materialization-v3 accepted — public/read-only, outcome-blind, no model fit**

## Purpose

`collect_kxbtcd_preoutcome_dataset.py` materializes the first real Candidate-B feature dataset without opening KXBTCD outcomes.

The collector uses the existing raw-first public Kalshi HTTP client. Every HTTP response is persisted before transformation. Source Market objects may contain settlement/result fields because they are part of the upstream object, but this collector does not read or emit those fields into event, split, state, quote, or dataset rows.

## Why materialization v3 exists

Two live, outcome-blind attempts exposed scaling assumptions in v1.

First, a full-Series historical Market crawl remained paginated after 500 pages of 1,000 markets. The preserved 500,000 rows only covered roughly 2026-01-06 through 2026-06-14, and an offline audit found 245 page-order violations. Historical Market cursor order therefore cannot be treated as a strict chronological rule-boundary scan.

Second, the replacement exact-event witness approach correctly bounded the Event universe but found 11,093 Events after the older-regime lower bound, exceeding its 6,000-event witness guard. Raising that guard would simply preserve the wrong unit of work.

Neither run opened outcomes, fit a model, or placed an order.

## Conservative modern-regime lower bound

Checkpoint 10's preserved, outcome-blind rule-regime report contains this KXBTCD sample-observed transition bracket:

```text
last sampled trimmed-60s event: 2024-12-20T01:00:00Z
first sampled simple-60s event:  2025-03-22T17:00:00Z
```

The second timestamp is **not** asserted to be the exact production rule-change instant. Materialization v3 deliberately starts there and discards any potentially usable modern history between the unknown true transition and that first sample-proven modern event.

The collector loads the preserved Checkpoint-10 regime report, requires that exact transition shape and first-modern timestamp, records the report path and SHA-256 in the run manifest, and fails closed if the evidence changes under the same materialization fingerprint.

## Event `strike_date` evidence and sampling-frame use

An offline audit of the raw Event responses already preserved by the failed collector established:

```text
KXBTCD Events at/after 2025-03-22T17:00:00Z: 9,737
missing strike_date: 0
duplicate strike_date timestamps: 0
Checkpoint-10 KXBTCD samples joined to Event census: 25/25
strike_date exactly equal to independently validated market close_time: 25/25
maximum absolute difference: 0 seconds
```

Materialization v3 therefore uses Event `strike_date` as the **outcome-blind sampling-frame chronology** in this post-proof interval.

This does not promote `strike_date` into an unconditional all-history settlement authority. Legacy Events before this interval were directly observed with null `strike_date`, and the v3 collector still fails closed if a post-proof Event returns a missing, duplicate, non-UTC, or pre-boundary timestamp.

No date is reconstructed from ticker/title text.

## Provisional event identities before selection

The unchanged split contract requires an event close time, target regime ID, primitive ID, and lineage before weekly selection.

For each post-proof Event, v3 therefore constructs a **provisional** target-regime primitive from:

```text
CF Benchmarks Bitcoin Real-Time Index (BRTI)
60-second window
simple mean
no trimming
above-threshold payoff relation
Event strike_date as measurement end
```

These provisional fields exist only to support deterministic quarantine, week partitioning, embargo, and SHA-256 event selection. The project explicitly records:

```text
unsampled_event_semantics_claimed_proven = false
```

A provisional row is not sufficient to produce a model state.

## Full semantic gate for every selected Event

After the frozen chronological split and weekly event selection, the collector fetches the **complete market ladder** for every selected Event.

For every returned strike it requires:

- exact selected `event_ticker`;
- KXBTCD `greater` / above-threshold payoff shape;
- recognized simple 60-second untrimmed BRTI rule semantics;
- parsed measurement end exactly equal to the selected Event `strike_date` / frozen split close time;
- one shared settlement primitive across the complete Event ladder;
- the fully validated primitive exactly equal to the provisional primitive used by the sampling frame;
- no continuation cursor after the per-Event 1,000-market completeness guard.

If any selected Event fails any one of those checks, the **entire materialization fails closed**. The collector does not silently replace that Event with a different hash-ranked Event because doing so after observing a semantic failure would change the predeclared sampling rule.

A successful run therefore proves the settlement semantics of every Event that can contribute Candidate-B states, without claiming that all unselected hourly Events were individually rule-validated.

## Frozen event, strike, and time sampling

The materialization still uses:

```text
maximum selected Events per eligible UTC week = 4
Event selection = SHA-256(event_ticker) ascending
structural strikes = q10, q30, q50, q70, q90
TTC anchors = 55m, 50m, 45m, 40m, 35m, 30m
```

Event selection uses no outcomes, prices, spread, volume, liquidity, quote availability, or model score.

Each selected Event's complete ladder is validated before structural strike selection. Each selected structural market then receives one 1-minute candle request spanning the frozen anchor range.

At each anchor the selector requires a real, uncrossed YES bid/ask observation at or before the target and no more than 60 seconds stale. Future candles and longer forward-fill are prohibited.

Historical markets use `/historical/markets/{ticker}/candlesticks`. Markets newer than the current historical cutoff use the normal KXBTCD series candlestick route with `include_latest_before_start=false`.

## Output

The run writes auditable CSV artifacts for:

- conservative post-proof settled Event census;
- provisional modern sampling-frame events;
- frozen chronological split rows;
- weekly selected Events;
- fully validated structural markets;
- quote-anchor availability audit;
- historical-reconstructed synchronized states;
- Candidate-B-ready pre-outcome rows;
- fail-closed exclusions.

The run summary records at least:

```text
conservative_modern_start_utc
conservative_modern_sampling_frame_count
fully_validated_selected_event_count
unsampled_event_semantics_claimed_proven = false
checkpoint10_regime_report_sha256
outcomes_materialized = false
model_fit_performed = false
authentication_used = false
orders_placed = 0
```

## What a successful run means

A PASS means the frozen sampling frame was built outcome-blindly, all selected Events passed complete settlement-rule validation, the requested historical quote states were materialized under the frozen timing rules, and the resulting pre-outcome dataset has a deterministic fingerprint.

A PASS does **not** mean Candidate B is predictive, calibrated, profitable, or executable. No labels or model coefficients exist in this stage.

## Accepted materialization-v3 run

Run: collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d

- selected events: 296
- structural markets: 1,480
- attempted states: 8,880
- available states: 6,378 (71.82%)
- dataset rows: 6,378
- dataset events: 295
- locked-test outcome labels opened: 0
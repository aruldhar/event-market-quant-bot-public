# Sports Historical Collector

## Status

Checkpoint-08 implementation component. Read-only and outcome-blind.

## Purpose

`collect_sports_historical.py` creates the first raw-linked Kalshi Sports historical dataset needed for the predeclared calibration experiment. It deliberately stops before threshold selection and outcome analysis.

## Inputs

CLI controls:

- `--max-sports-events`: bounded number of Sports events with at least one baseline-candidate settled market;
- `--max-event-pages`: fail-closed Event pagination guard;
- `--max-market-pages-per-tier`: fail-closed per-event market pagination guard;
- `--anchor-lookback-hours`: real-candle request window ending at each anchor, allowed 1–48 hours.

Fixed research anchors come from the predeclared experiment:

```text
7d, 3d, 1d before close_time
```

## Network path

One run:

1. archives `/historical/cutoff`;
2. pages `/events?status=settled` without nested markets;
3. treats blank/missing event categories as unclassifiable discovery records, preserves them only in raw storage, and filters source-native `category == Sports`;
4. queries `/historical/markets?event_ticker=...`;
5. queries live `/markets?event_ticker=...&status=settled`;
6. unions the two tiers and rejects duplicates or cutoff-routing contradictions;
7. retains binary, finalized, non-MVE markets without consulting `result`;
8. requests one real 1-minute candlestick window for each market × 7d/3d/1d anchor;
9. writes raw-linked events, markets, anchors, and candles CSVs;
10. completes the standard run manifest and runtime event log.

For live candlestick requests, `include_latest_before_start=false` is explicit.

## Outputs

Under:

```text
data/derived/sports_historical/YYYY/MM/DD/
```

one run writes:

```text
<run_id>_events.csv
<run_id>_markets.csv
<run_id>_anchors.csv
<run_id>_candles.csv
```

No outcome CSV is written before the staleness threshold is frozen.

The raw HTTP archive, runtime event log, and collection manifest use the project's existing infrastructure.

## Failure modes

The collector fails closed on, among other things:

- inaccessible or malformed cutoff data;
- malformed accepted Sports identity fields such as missing `event_ticker` or `series_ticker`;
- exhausted pagination with another cursor remaining;
- market/event identity mismatch;
- a market returned from the wrong live/historical tier for the captured cutoff;
- duplicate market tickers across tiers;
- non-object or malformed candle payloads;
- duplicate candle timestamps inside one anchor request;
- candles outside the requested window;
- raw persistence failure;
- derived write failure;
- manifest/runtime-event integrity failure.

Missing candles or missing bid/ask pairs are **not** silently repaired. A zero-candle response creates an anchor row with zero counts so the later pilot can measure missingness.

## Tests

Deterministic tests cover:

- three-anchor construction;
- zero-candle anchor preservation;
- outcome-blind invariance when raw `result` changes;
- historical/live cutoff routing;
- explicit synthetic-candle disablement on live requests;
- crossed quote preservation;
- duplicate-tier failure;
- relational schema checks;
- deterministic CSV headers;
- offline raw-to-derived manifest reconciliation;
- rejection of tampered derived candle values;
- rejection if a pre-staleness manifest claims outcomes were materialized.

## Validation command

After a completed collector run:

```powershell
.\.venv\Scripts\python.exe validate_sports_historical_manifest.py <manifest-path>
```

A PASS proves the normalized pre-staleness tables reconcile to successful raw exchanges and preserve the declared blinding/routing contract. It does not validate a staleness threshold or calibration result.
## Cross-tier routing anomalies

Checkpoint 08 observed a real public API inconsistency during the first 3-event smoke test: `GET /markets?status=settled&event_ticker=...` returned `KXNFLRETIRE-RWILSON3-2829` even though its `settlement_ts` was before the captured `market_settled_ts` cutoff. Kalshi's published historical-data contract says such a market belongs to the historical tier.

The collector therefore treats list-endpoint tier membership as an observation, not as routing authority. For every market:

1. classify the canonical tier from the captured `market_settled_ts` and the market's `settlement_ts`;
2. preserve any off-tier list response unchanged in raw storage;
3. if a canonical-tier copy was also returned, derive only from that canonical copy;
4. if only the off-tier copy was returned, issue one raw-first canonical single-market request (`/historical/markets/{ticker}` or `/markets/{ticker}` as required);
5. require the recovered ticker, event identity, settlement timestamp, and cutoff classification to agree;
6. fail closed on conflicts or if canonical evidence cannot be obtained.

The manifest and terminal summary count cross-tier observations, affected market tickers, and canonical recovery fetches. An off-tier observation is never silently relabeled as canonical data.

## Unclassifiable event metadata

A later 100-event pilot encountered a settled Event object with a blank `category`. The broad `/events` page validator therefore distinguishes envelope integrity from Sports eligibility. Every Event item must still be an object, but a blank/missing category is not allowed to abort the entire Sports scan. Such a record is raw-archived, counted as `unclassifiable_event_count`, skipped from the derived Sports dataset, and never treated as Sports by inference.

Once an Event explicitly declares `category == Sports`, its required identity fields remain fail-closed: `event_ticker` and `series_ticker` must be non-empty text before any market or candle collection occurs.

## Accepted 100-event collection evidence

Final outcome-blind collection run:

`collect_sports_historical_20260809T060907842728Z_94ad3820`

Collector output:

```text
Sports events: 100
Markets: 1200
Anchor observations: 3600
Real 1m candle rows: 288210
Anchors with a bid/ask pair in the 24h engineering window: 2646
Anchors without a bid/ask pair: 954
Event pages scanned: 9
Cross-tier list observations: 84
Markets observed off canonical tier: 84
Canonical single-market recovery fetches: 0
Unclassifiable settled events skipped: 1
Market cutoff: 2026-06-09T00:00:00Z
Authentication used: no
Outcomes materialized: no
Staleness threshold selected: no
Calibration analysis run: no
Orders placed: 0
```

Independent manifest validation passed:

```text
Event rows: 100
Market rows: 1200
Anchor rows: 3600
Candle rows: 288210
Raw records indexed: 4718
Outcomes materialized: no
```

This run is accepted for data-quality analysis only. It does not itself satisfy or bypass the staleness gate.

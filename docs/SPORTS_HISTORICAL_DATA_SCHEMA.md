# Sports Historical Data Schema

## Purpose

Checkpoint 08 needs a normalized Kalshi Sports historical dataset without weakening the project's raw-first rule. The original HTTP exchange remains the source of truth. Every normalized row carries exact raw request lineage, and cross-table foreign keys preserve event → market → anchor/candle relationships without copying source fields whose immediate raw provenance would be ambiguous.

This schema supports the predeclared 7-day, 3-day, and 1-day calibration anchors. It does **not** choose a staleness threshold, evaluate outcomes, or claim a trading edge.

## Version

Dataset family:

```text
sports_historical_dataset.v1
```

Tables:

```text
sports_historical_event.v1
sports_historical_market.v1
sports_historical_anchor.v1
sports_historical_candle.v1
sports_historical_trade.v1
sports_historical_outcome.v1
```

The field lists are declared in `src/sports_historical_schema.py` and validated by tests.

## Why the event and anchor tables exist

### Event table

Sports classification and `series_ticker` come from Kalshi Event metadata. They are therefore stored in an event row whose lineage points directly to the `/events` response that supplied them.

Market and candle rows reference that identity through `event_ticker`/`ticker` relationships rather than pretending a candlestick response itself supplied the Sports category.

### Anchor table

A market can have **zero** real one-minute candles in the bounded lookback window before an anchor. If the dataset stored only candle rows, that missing observation would disappear completely.

`sports_historical_anchor.v1` therefore emits exactly one row for every market × anchor request, even when the candlestick array is empty. It records counts, the latest real candle timestamp, the latest candle with a complete YES bid/ask pair, and the resulting quote age when available.

This is descriptive quality evidence. It is not yet an accepted staleness rule.

## Outcome blinding

Raw historical market responses can contain final `result`. Raw-first preservation means that field remains in the immutable raw HTTP body.

Before the staleness rule is frozen, the collector materializes only:

```text
events
markets
anchors
candles
```

It does **not** create the outcome table and does not collect trades for the simple baseline. The later staleness pilot may load only those four tables.

After the staleness decision is recorded in `docs/DECISIONS.md`, a separate offline step may materialize `sports_historical_outcome.v1` from the already archived market responses. No re-collection is required merely to reveal outcomes.

## Common lineage fields

Every table begins with:

| Field | Meaning |
|---|---|
| `run_id` | Collection-run manifest identifier. |
| `raw_source` | Raw adapter identity, currently `kalshi_public_rest`. |
| `raw_session_id` | Raw recorder session. |
| `raw_request_id` | Exact raw HTTP request ID. |
| `route_tier` | `metadata`, `historical`, or `live`. |

The portable raw key is:

```text
(raw_source, raw_session_id, raw_request_id)
```

A normalized row may be emitted only after the corresponding HTTP exchange has been persisted.

## Event table — `sports_historical_event.v1`

Fields after lineage:

```text
event_ticker
series_ticker
category
mutually_exclusive
strike_date
```

The baseline requires source-native `category == Sports`. Category is never inferred from ticker text or titles.

Primary key:

```text
event_ticker
```

## Market table — `sports_historical_market.v1`

Fields after lineage:

```text
ticker
event_ticker
market_type
status
open_time
close_time
settlement_ts
mve_collection_ticker
is_provisional
```

The pre-staleness collector applies only outcome-free baseline filters:

- `market_type == binary`;
- terminal REST object status `finalized`;
- no `mve_collection_ticker`.

It deliberately does **not** inspect `result` while building this dataset.

Foreign key:

```text
market.event_ticker -> event.event_ticker
```

## Anchor table — `sports_historical_anchor.v1`

One row exists for every accepted market at each predeclared anchor:

```text
7d
3d
1d
```

Fields after lineage:

```text
ticker
anchor_name
anchor_ts
window_start_ts
window_end_ts
candle_count
quote_pair_count
latest_real_candle_ts
latest_quote_pair_ts
latest_quote_age_seconds
```

`latest_quote_age_seconds` is blank if no complete bid/ask pair exists in the request window. No value is imputed.

The request window is an engineering bound and is recorded in the run manifest. It must not be relabeled as the accepted staleness threshold.

Primary key:

```text
(ticker, anchor_name)
```

## Candle table — `sports_historical_candle.v1`

Fields after lineage:

```text
ticker
anchor_name
anchor_ts
source_field_family
end_period_ts
period_interval_minutes
yes_bid_close
yes_ask_close
price_close
volume
open_interest
quote_pair_present
crossed_close
```

Historical and live API surfaces currently expose different field families. The normalized row records:

```text
historical_plain
live_dollars
```

so that normalization remains auditable.

Missing bid/ask/price/volume/open-interest values remain blank. Crossed quotes are flagged, not repaired.

The live request must explicitly use:

```text
include_latest_before_start=false
```

so a synthetic continuity candle cannot satisfy an anchor.

Foreign key:

```text
(ticker, anchor_name) -> anchor.(ticker, anchor_name)
```

## Trade table — `sports_historical_trade.v1`

The trade schema remains defined because the public historical-trade path was validated, but the first calibration baseline does not need trade prints to construct the bid/ask midpoint proxy. To keep the initial collector simple and reduce unnecessary requests, trade collection is disabled before the staleness pilot.

Fields after lineage:

```text
ticker
trade_id
created_time
count_fp
yes_price_dollars
no_price_dollars
taker_side
```

A later accepted diagnostic can add trade collection without changing the outcome-blinding rule.

## Outcome table — `sports_historical_outcome.v1`

Fields after lineage:

```text
ticker
event_ticker
result
```

This table is explicitly outcome-sensitive and is **not materialized before the staleness rule is frozen**.

The later parser must fail closed on anything other than the accepted terminal YES/NO representation. It may not infer a label from prices, titles, or settlement values.

## Cutoff routing

Each run captures `/historical/cutoff` first.

Market and candlestick routing uses `market_settled_ts`:

```text
settlement_ts < market_settled_ts  -> historical tier
settlement_ts >= market_settled_ts -> live tier
```

The candle's own timestamp does not determine which API tier owns it.

Event metadata stays on the normal Event surface. The collector enumerates settled events without nested markets, then queries both historical and live settled-market lists for each accepted Sports event so the moving cutoff does not silently truncate the event's market set.

## Request-window rule

For each accepted market and each anchor, the collector requests real one-minute candles from:

```text
anchor_ts - anchor_lookback_hours
through
anchor_ts
```

The current CLI allows `anchor_lookback_hours` from 1 through 48. This is a collection bound, not a staleness decision. If the outcome-blind pilot shows material right-censoring at the bound, the correct response is to expand/recollect the window before freezing a threshold—not to impute a quote.

## Reconciliation requirements

Before a run can be used by the staleness pilot:

1. all four pre-staleness tables pass their exact field schemas;
2. every row has nonblank raw source/session/request lineage;
3. every lineage key resolves to a successful raw HTTP exchange in the run;
4. Event rows match their raw `/events` objects;
5. Market rows match their raw historical/live market-list objects;
6. settlement timestamps agree with the run's captured cutoff and route tier;
7. each accepted market has exactly 7d, 3d, and 1d anchor rows;
8. every anchor request's raw parameters match its recorded window;
9. live anchor requests explicitly disable synthetic continuity candles;
10. every candle row can be rebuilt from the referenced raw candlestick response;
11. zero-candle windows remain represented by anchor rows;
12. no pre-staleness derived table contains `result`.

`validate_sports_historical_manifest.py` performs the offline raw-to-derived reconciliation.

## Current limitations

This schema and collector do not yet establish:

- an acceptable quote-age threshold;
- enough coverage for the >=1,000 unique-event calibration gate;
- calibration or miscalibration;
- economic executability;
- profitability.

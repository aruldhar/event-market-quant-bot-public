# KXBTC15M development live-data collection specification

## Purpose

Collect the public Kalshi BTC chart history for the same 96 frozen development
markets already used by the KXBTC15M diagnostics. This is an input-provenance
gate, not a strategy-selection run.

## Frozen boundary

- Input allowlist: exact market index/ticker pairs in the frozen market-dynamics
  anchors CSV.
- Expected markets: 96.
- Last eligible development ticker: `KXBTC15M-26AUG121430-30`.
- First holdout ticker: `KXBTC15M-26AUG121445-45`.
- The collector refuses any ticker at or beyond the holdout boundary.

## Public requests

For each eligible market, archive before parsing:

1. `GET /markets/{ticker}`
2. `GET /live_data/events/{event_ticker}?range=1h`

Authentication and order execution are prohibited.

## Hard validation gate

- Market ticker and event ticker are consistent and unique.
- The displayed target is parseable from `yes_sub_title`.
- Live data is historical BTC crypto data for the same event.
- `maturity_ts_ms` equals the market close time.
- Timeseries timestamps are strictly increasing on a continuous one-second grid.
- The final timeseries timestamp equals maturity.
- A point exists exactly one second before market open.
- Every raw response and the derived CSV lineage are retained in the run manifest.

Target/pre-open equality and final chart/expiration equality are reported across
all 96 markets. They are empirical semantic audits, not assumed hard invariants.

## Causality

The derived timeseries includes only the displayed target, chart observations,
timestamps, and raw lineage. The published expiration value is labeled
`audit_only` and may never enter a trading feature. A later H3 delta analysis
must join each order-book decision only to chart observations at or before that
decision timestamp.

## Outputs

- `kxbtc15m_development_live_data_summary.csv`: one row per market.
- `kxbtc15m_development_live_data_timeseries.csv`: one row per chart observation.
- `KXBTC15M_DEVELOPMENT_LIVE_DATA.md`: collection-gate summary.
- Raw JSONL, runtime event log, and collection manifest under the existing data
  roots.

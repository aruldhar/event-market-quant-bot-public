# KXBTC15M development economics inputs

## Purpose

Collect the minimum label and fee evidence required before implementing a
depth-aware pooled-position simulator. This is not an ML experiment.

## Frozen scope

- The ticker allowlist comes only from the already-generated market-dynamics
  anchors CSV.
- Exactly 96 unique eligible development markets are permitted.
- Market indices must remain within the frozen first 100 markets.
- `KXBTC15M-26AUG121445-45` and every later ticker are refused.
- Outcomes must be official finalized `yes`/`no` market results.

## Public requests

- 96 `GET /markets/{ticker}` calls for development outcomes.
- One `GET /series/KXBTC15M` call for the current public series snapshot.
- One `GET /series/fee_changes` call with `show_historical=true`.

All responses are written raw-first through the repository's existing public
HTTP recorder and correlated to derived CSV rows. No authentication or account
endpoint is used, and no order can be placed.

## Interpretation gate

The collector preserves full fee objects rather than guessing a formula from
partial fields. After collection, inspect the returned series snapshot and fee
change history to identify the fee configuration effective during the August
11–12, 2026 market window. Only then should the bounded depth-aware simulator
be implemented.

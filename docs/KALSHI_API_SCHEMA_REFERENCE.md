# Kalshi Public API — Schema Reference and Gotchas

Last updated: 2026-09-28. Base: `https://api.elections.kalshi.com/trade-api/v2/`

Every item below was verified by dumping actual response keys, not read from documentation.
Five of these were guessed wrong first and each wrong guess produced a false result that
survived until something else contradicted it. When in doubt, dump `sorted(response.keys())`
and one full record before writing any analysis.

## Field semantics that are easy to get wrong

### `fee_type` decides whether makers pay anything — not `fee_multiplier`

```
quadratic                        = 14,235 series (98.9%)   taker pays, MAKER PAYS ZERO
quadratic_with_maker_fees        =    160
quadratic_with_combo_maker_fees  =      3
fee_multiplier:  1 = 14,365      0.5 = 19 (all MLB)        0 = 14 (incl. KXBTCY)
```

Published schedule, effective 2026-07-07:

- taker fee = `0.07 x C x P x (1 - P) x M_taker`
- maker fee = `0.0175 x C x P x (1 - P) x M_maker` — one quarter the coefficient, and
  `M_maker` defaults to **0**

Both are rounded **up to the whole cent per order**, which is why small orders are penalised:
at N=1 and P=0.5 the fee is 2c per contract against 1.75c at N=100.

Consequence: **"the fee killed it" is a statement about taker strategies only.** All weather
series are `quadratic`, so resting orders there cost nothing to have filled. `KXMLBGAME` is the
awkward case — `fee_multiplier` 0.5 *and* `quadratic_with_maker_fees`, so the half-fee sport is
one of the 160 that does charge makers.

Fee as a fraction of capital at risk is `0.07 x (1 - P)`, which is linear and 19x cheaper at
95c than at 5c. The fee itself peaks at P = 0.5.

### `strike_type` is the authoritative structure field, not which strike fields are populated

Values seen: `custom` (18,074), `greater` (12,804), `greater_or_equal` (3,882), `between`
(2,771), `None` (497), `less` (429), `less_or_equal` (27).

**For `greater` and `less` markets, `floor_strike == cap_strike`** — the same value appears in
both. Inferring "this is a bucket because both fields are set" classified nested CPI thresholds
as mutually exclusive and manufactured an 85c phantom arbitrage. Only `between` is a real
bucket.

A complete exhaustive ladder is the `between` buckets **plus** a `less` tail **plus** a
`greater` tail. Verify rather than assume: `cap_less == floor_first_bucket`,
`floor_greater == cap_last_bucket`, and every internal gap no wider than its bucket. Filtering
out empty-book buckets and then pricing the remainder as exhaustive manufactured an 82c phantom
arbitrage on KXHIGHLAX.

### `mutually_exclusive` means AT MOST one YES, not exactly one

On the event object. Therefore:

- **Sell-all and sell-pair need only exclusivity — sound.** Arbitrage iff
  `sum(bid) - fees > 100`.
- **Buy-all needs exhaustiveness, which the flag does not give.** A low `sum(ask)` is the
  market correctly pricing "none of these": KXSTATE51 shows 8 legs at `sum_ask = 15` because
  there will probably be no 51st state.

### Price and size fields are suffixed

`yes_bid_dollars`, `yes_ask_dollars`, `no_bid_dollars`, `no_ask_dollars` are **strings in
dollars**. Plain `yes_bid` / `yes_ask` return `None`. Likewise `volume_fp`,
`open_interest_fp`, `liquidity_dollars` — plain `volume` / `open_interest` / `liquidity`
return `None` on every market, which silently empties a liquidity filter.

`liquidity_dollars` is `0.0000` everywhere and is useless; use `open_interest_fp`.

**Top-of-book depth is available**: `yes_bid_size_fp` and `yes_ask_size_fp`. And
`no_ask == 100 - yes_bid` exactly, so the size available on a buy-NO leg is that market's
`yes_bid_size_fp`. Always rank candidate trades by `edge x size` in dollars, not by cents per
contract.

An empty book reads as **bid 0 / ask 98**, which passes a naive "has a two-sided quote" test.
Require `bid > 0 and ask < 100 and size > 0`.

## Endpoint behaviour

### `/series?limit=1000` ignores the limit
Returns all ~14,398 series in one call, each with `category`, `fee_type`, `fee_multiplier`.
Site navigation labels differ from API category names ("Climate and Weather", not
"Climate"/"Weather").

### `/markets?status=open` blind-paged is unusable
There are more than 500,000 open markets, the cursor never exhausts, and the ordering is
dominated by sports player props. **Enumerate `/series` first, then fetch markets per series**
(~3,400 series at 0.22s is about 13 minutes).

### `market_type=perpetual` as a filter is ignored
It returns unrelated markets, the same way `limit` is ignored on `/series`.

### `/markets/trades?ticker=X&limit=1000` RETURNS NEWEST-FIRST
Proved directly: selecting element 0 gives exactly the same result as selecting the
chronologically last trade. Only ~60.9% of adjacent pairs ascend in time, so the list is not
cleanly sorted — but position 0 is the newest.

Measured bias by entry-selection rule, same markets, band 65-85c, one bet per game:

| rule | result |
|---|---|
| earliest qualifying (honest) | **-3.01c** |
| random pick from the list | +2.39c |
| `trades[0]` / latest (look-ahead) | **+5.88c** |

**Always store `created_time` and sort ascending before selecting an entry.** Never treat
`trades[0]` as "the first trade". Any dataset fetched without `created_time` is unusable for
entry-rule work.

### Candlesticks
`/series/{s}/markets/{t}/candlesticks?start_ts=&end_ts=&period_interval=60`. One call returns
**every** bar in the window, so widening the window gives extra horizons for free.

Fields: `end_period_ts`, `open_interest_fp`, `volume_fp`, and `price` / `yes_bid` / `yes_ask`
each as OHLC with `close_dollars` etc.

- Markets living about an hour (KXBTCD hourly) return **one** bar at `period_interval=60`; use
  `period_interval=1`.
- Pre-2026-07-24 markets need the `/historical/` path, and **historical candlesticks use a
  different field schema** — parsing `c['yes_bid']['close_dollars']` silently yields nothing.
  Trade-derived bid/ask works instead: `taker_side='yes'` means the ask was at that price.

### Perpetual futures are a separate universe
`KXBTCPERP`, `KXETHPERP`, `KXSOLPERP`, `KXXRPPERP`, `KXDOGEPERP` all resolve at
`/series/{ticker}` with `fee_type: margin_market_maker_program_fees` and `fee_multiplier: 0`,
but they are **absent from `/series?limit=1000`** and **every markets/events endpoint returns
empty**. As of 2026-09-28 perps market data is not reachable on `trade-api/v2`.

## Operational notes

- `/var/lib/kalshi-research` is root-owned: a plain `cat > file` redirect **fails silently**
  while a subsequent `docker run` proceeds against a nonexistent file. Use `sudo tee`.
- A container that writes output needs the mount writable — not `:ro`.
- Validate a written script with `python3 -m py_compile` before a long run; a line count is not
  proof the paste survived.
- Kalshi runs weekly maintenance 03:00-05:00 ET Thursday, which blocks KXBTCD generation
  discovery roughly 06:00-09:30 UTC.
- IEM (Iowa Environmental Mesonet) rate-limits hard with HTTP 429 on sequential calls; batch
  stations into one request via repeated `&station=` and sleep 8-12s. Put the sleep **before**
  any `continue`, or failed fetches skip the delay and cascade into rate limiting.

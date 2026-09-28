# Kalshi Structural Arbitrage Screen — Result

Last updated: 2026-09-28. Evidence dates 2026-09-26 to 2026-09-27.

Two families of riskless structural arbitrage were screened exhaustively. Both are closed.
Scripts: `scripts/kalshi_research/corr.py` and `mxarb.py`.

## Family 1 — strike ladders

`corr.py`, live snapshot, 3,432 series (every category except Sports, Entertainment, Mentions,
Elections and Politics), **38,484 open markets**.

Three relations tested, all fee-aware, all using only Kalshi's own executable prices:

- **Nested monotonicity (2 legs).** Where an event holds several "above strike K" markets they
  are nested, not exclusive: `P(>K1) >= P(>K2)` whenever `K1 < K2`. Buy YES on the lower strike
  and NO on the higher and the minimum payoff is 100 with upside of 200 in the middle region,
  so `ask(lower) + no_ask(higher) < 100` after fees is locked. Two legs carries the smallest
  possible multi-leg fee penalty.
- **Exclusive pair (2 legs).** Two mutually exclusive buckets whose bids sum above 100.
- **Complete ladder.** Buy every leg of a verified exhaustive partition.

```
pairs_nested = 173,976    pairs_excl = 3,474    ladders priced = 97
partition_ok = 106 of 115 checked
TOTAL VIOLATIONS = 1   (+3.22c on 4 contracts = $0.13)
```

The single hit — `USCLIMATE`, `less`-type strikes — is more likely a fifth semantic misread
than a real dislocation. Either way it is not a business.

## Family 2 — multi-outcome events

`mxarb.py`. `/events?status=open&with_nested_markets=true&limit=200` exhausts in **72 pages /
14,245 events** and returns markets inline, far cheaper than per-series market calls.
**5,021 mutually-exclusive events with 2+ markets** (Sports 3469, Elections 999, Entertainment
223, Climate 102, Economics 95).

```
sellall_tested = 4,425    pairs = 53,068    ->    ZERO violations
```

`mutually_exclusive` means **at most one** YES, not exactly one. Therefore sell-all and
sell-pair need only exclusivity and are sound; **buy-all needs exhaustiveness, which the flag
does not give.** All 78 apparent hits were buy-side and every one is explained by
non-exhaustiveness — `KXSTATE51` shows 8 legs at `sum_ask = 15` because there will probably be
no 51st state; `KXNBERRECESSQ` at 26 because the recession may start after the last listed
quarter. An exhaustive partition cannot have `sum_ask` far below 100; a low `sum_ask` *is* the
market pricing "none of these".

## The number that matters: gross violations are routine, the fee eats them by ~1c

Across fully-quoted mutually-exclusive partitions, the sum of bids runs **median 92, p90 99,
max 105.0**, with a whole-partition ask-bid spread of median 15c. Top near misses: 105.0 on 11
legs, 104.0 on 11, 103.0 on several.

Worked example, `KXNATBOOKAWARDS-POETRY26`, 11 legs, `sum_bid = 105`, so 5c gross. Selling a
40c favourite costs `7 x 0.6 x 0.4 = 1.68c`; ten longshots near 6.5c cost `7 x 0.935 x 0.065 =
0.43c` each. **Fee load ~6.0c against ~5.0c gross — it misses by about a cent.**

Pairs are structurally *worse* than the full ladder here: a 2-leg violation needs the top two
outcomes to sum above ~103, which only happens when the rest of the field is worthless.

## Why the multi-leg penalty makes this structural

For a position split into legs, `sum(p_i (1 - p_i)) - P(1 - P) = P^2 - sum(p_i^2) >= 0`.
Splitting is **always** more expensive, and the penalty reaches 17x at P = 0.95. So the
structures with the most ways to be mispriced are also the most expensive to exploit. Ladder
dutch books are not merely absent; they are close to impossible by construction.

## Execution caveat for any future hit

**Kalshi has no atomic multi-leg order.** Leg one fills, then leg two may have moved, leaving a
naked directional position. A 4c edge where the second leg can slip 3c is not a 4c edge. Only
worth pursuing when the edge absorbs a slip, or when one leg is a resting order you are content
to leave unfilled.

A single snapshot also cannot distinguish a structural violation from a crossed stale quote.
That needs persistence sampling across repeated snapshots, and any candidate must be ranked by
`edge x top-of-book size` in dollars — a 4c edge on 3 contracts is not a business.

## Four wrong schema guesses that produced phantom arbitrage

Recorded in full in `KALSHI_API_SCHEMA_REFERENCE.md`, summarised here because each one produced
a confident false positive before being caught:

1. Pairing different MLB **players** as nested strikes because they shared an event and a
   `floor_strike` of 1.
2. Treating `floor_strike == cap_strike` threshold markets as buckets, which classified nested
   CPI thresholds as mutually exclusive — an 85c phantom.
3. Filtering out empty-book buckets and pricing the remainder as exhaustive — an 82c phantom
   on KXHIGHLAX.
4. Reading `volume` / `open_interest` / `liquidity` instead of the `_fp` and `_dollars` fields,
   which returned `None` on all 11,850 markets and silently emptied the liquidity filter.

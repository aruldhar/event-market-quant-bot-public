# KXBTC15M H3 sealed-holdout evaluation specification

## Purpose

This is the one confirmatory test of the frozen H3 candidate on the untouched
KXBTC15M markets 101 through 126. The evaluator creates a durable pre-outcome
freeze receipt before it extracts or interprets any holdout archive or requests
any finalized result. The audit ZIP is byte-hashed as a frozen input before the
receipt is committed. The 26 markets become permanently opened after this command runs and
must never be reused for model or policy selection.

## Exact sample

- Partition: chronological markets 101–126 from the 126-market audit.
- First ticker: `KXBTC15M-26AUG121445-45`.
- Last ticker: `KXBTC15M-26AUG122100-00`.
- Required market count: 26.
- Required eligible count: 26 under the already-frozen primary raw-depth
  quality gate.
- Finalized labels come from one unauthenticated public GET per exact ticker.

Any missing, duplicate, shifted, ineligible, non-finalized, or non-binary
market fails closed. No replacement market is allowed.

## Frozen policy

- Observe every causally received archived HTTP order-book response.
- Search only while `240 < seconds_remaining <= 300`.
- Trigger on the first favored midpoint satisfying `0.90 <= midpoint < 0.98`.
- Execute after one second at full archived depth without rechecking the entry
  state.
- Spend no more than $100 including the frozen conservative fee model.
- Monitor all later causal responses for a protected cash exit worth 50% of
  maximum settlement profit after fees and one-second execution delay.
- If no protected target fills, begin the frozen full cash fallback ten seconds
  before close; settle only if archived depth cannot liquidate.
- At most one cycle; no compounding, early entry, re-entry, runner, external BTC
  data, authentication, or order placement.

The evaluator regenerates every H3 row with the accepted native implementation
and requires market-by-market agreement with the independent frequency
implementation on status, trigger, fill, decision time, execution time, exit
reason, and P&L.

## Metrics and preregistered decision gate

The primary estimand is mean P&L per eligible holdout market, with no-trades
counted as $0. Its 95% interval uses 2,000 market bootstrap draws with seed
20260813 and ordered draws 49 and 1949, matching development reporting.

Sealed-holdout support requires all four conditions:

1. At least 10 of 26 markets fill.
2. Mean P&L per eligible market is strictly above $0.
3. The bootstrap 95% lower bound is strictly above $0.
4. There are zero full-capital losses, where a full loss is at least 90% of
   entry cash outflow.

If every gate passes, the result is `SUPPORTED`. If mean P&L is positive and
there are no full losses but another gate fails, it is `INCONCLUSIVE`.
Otherwise it is `NOT_SUPPORTED`.

The 10-fill information floor and conservative loss gate were frozen before
opening outcomes. Development results are displayed only as context and are
not a threshold the holdout must match.

## Evidence and one-shot control

The freeze receipt records the canonical design fingerprint, exact input
hashes, and hashes of all implementation files. Raw public responses, runtime
events, derived CSVs, and a completed/failed run manifest are preserved. A
matching completed manifest or existing result output blocks another run.

A passed holdout is evidence of generalization, not a profitability guarantee
and not authorization for paper, demo, or live trading. A failed or
inconclusive result cannot be repaired by trying variants on the opened 26
markets; any new strategy requires a new prospective sample.

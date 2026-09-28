# KXBTC15M H3 Research Closeout

Status: **closed; confirmatory holdout failed; no H3 strategy graduated**.

Date: 2026-08-13 America/Chicago / 2026-08-14 UTC closeout preparation.

## Repository continuity

This local research branch began after the last published GitHub checkpoint:

```text
repository: aruldhar/event-market-quant-bot
published main: fa36906a860393a9f96351808309b75508417480
checkpoint commit recorded by the receipt: ab5f300b97b5385e5d2eaeafae901eef5bdf31ec
checkpoint: 10 - BTC-Specific Historical Research Design
canonical regression in that receipt: 311 passed, 22 subtests passed
```

The Checkpoint-10 endpoint selected modern-regime KXBTCD for the first BTC
structural baseline, found no untouched-holdout improvement from the v1
monotonicity repair, and proposed Checkpoint 11 — KXBTCD Baseline Expansion and
Reference Feed Reassessment.

The KXBTC15M work summarized here was a subsequent local, public/read-only
secondary branch. This document connects that branch back to the published
Checkpoint-10 endpoint without rewriting the earlier evidence.

## Research question

The branch asked whether high-probability KXBTC15M contracts could support a
simple executable strategy after native observation frequency, fees, displayed
depth, one-second latency, missed fills, and protected cash exits were modeled.

The final frozen H3 rule was:

- first causal native favored midpoint from 90% to below 98%;
- decision during four to five minutes remaining;
- one-second delayed, unprotected, full-depth entry;
- maximum $100 cash deployment including conservative fees;
- protected full-position exit at 50% of maximum settlement profit;
- ten-second preclose cash fallback;
- settlement only after preclose liquidity failure;
- at most one position unless a diagnostic explicitly stated otherwise.

## Data and independence boundary

```text
original development markets: 96
sealed chronological holdout markets: 26
all opened markets after the one-shot test: 122
development fills under frozen H3: 57
holdout fills under frozen H3: 14
combined fills: 71
```

Each 15-minute market is the evaluation unit. Native snapshots within a market
are repeated states, not independent observations. All 122 markets are now
opened development evidence. The 26-market holdout is permanently consumed and
must never be reused as untouched evidence for H3, a stop overlay, a model, or a
tuned variant.

## Development result

On the original 96 markets, frozen H3 filled 57 markets and reported:

```text
mean P&L per eligible market: $2.32
mean P&L per fill: $3.90
profitable fills: 100%
protected target fills: 100%
full-capital losses: 0
worst filled-trade P&L: $1.10
```

This result was adaptive development evidence. The timing, band, target, and
execution mechanics had been selected after multiple diagnostics and were not
an unbiased expected-return estimate.

## One-shot sealed holdout

Experiment:

`kxbtc15m_h3_native_4_5m_protected50_holdout.v1`

Design fingerprint:

`4b3edf6f39be338f4fd6149cdea3de4ce54a7410aa1a105a187c6619d82d7aff`

Observed on the 26-market holdout:

```text
filled markets: 14
total P&L: -$46.55
mean P&L per eligible market: -$1.79
95% bootstrap interval: -$10.16 to $2.83
mean P&L per fill: -$3.32
profitable fills: 92.9%
target fills: 92.9%
full-capital losses: 1
worst P&L: -$99.83
decision: NOT_SUPPORTED
```

The losing trade was `KXBTC15M-26AUG121945-45`. It entered 104 YES contracts
at an average price of $0.957, never produced a protected target signal, could
not liquidate at the preclose fallback, settled on the losing side, and lost
$99.828.

H3 failed the preregistered positive-mean, positive-lower-bound, and zero-full-
loss gates. The development result therefore did not generalize.

## Main adaptive diagnostics

### Timing and entry selection

- The four-to-five-minute row remained the strongest development timing row.
- Continuing to search through the entire last five minutes increased fills
  from 57 to 94 but reduced mean P&L per market from $2.32 to $0.95 and created
  three full losses.
- Added entries after four minutes had mean P&L `-$3.5416`, worst `-$99.87`,
  and three full losses.
- The 90%-to-below-98% combined band reproduced the baseline. Splitting to
  90%-95% retained most of the result, while 95%-98% reduced coverage and mean
  P&L. The 80%-90% alternative introduced full-loss risk.
- Immediate or persisted early entries in the five-to-7.5-minute window failed
  every preregistered combined-policy gate and each produced one full loss.

### Cash exits and execution mechanics

- Protected 50%-of-maximum profit was the strongest tested native exit target:
  `$2.32` mean P&L per market, 100% target fills in development, and zero full
  losses.
- Protected execution improved mean P&L by about `$0.11` per market versus
  unprotected 50% execution by rejecting delayed below-target sales.
- A principal-recovery runner slightly reduced combined P&L and worsened the
  lower tail.
- Strict bounded re-entry produced only one second entry and about `$0.01`
  incremental mean P&L per market. The opportunity was too sparse to justify
  additional policy complexity.

### Stop-loss and timeout research

- Every one of the 57 original development winners first showed negative
  executable full-exit P&L before reaching its target.
- Median pre-target minimum executable P&L was `-$3.62`; the worst was
  `-$83.00`. Fixed stops therefore stopped many eventual winners.
- Fixed, persistence, velocity, acceleration, age-gated, and liquidity-gated
  stop families saved the one opened loser but sacrificed more winner recovery
  than they saved in combined opened evidence. No robust candidate passed.
- A full no-target exit at 90 seconds remaining reduced the known loss to
  `-$51.73` but reduced combined 122-market P&L from `$176.00` to `$167.18`.

### Partial 90-second frontier

At the first causal native response at or below 90 seconds remaining, partial
sales of positions that had not reached the protected target produced:

| Fraction sold | Combined P&L | Difference vs H3 | Paired mean 95% interval | Worst |
|---:|---:|---:|---:|---:|
| 25% | $178.71 | +$2.71 | -$0.15 to $0.28 | -$87.81 |
| 50% | $176.68 | +$0.67 | -$0.39 to $0.52 | -$75.78 |
| 75% | $172.08 | -$3.93 | -$0.65 to $0.77 | -$63.76 |
| 100% | $167.18 | -$8.82 | -$0.91 to $1.01 | -$51.73 |

The 25% and 50% rows were positive only after combining the original all-winner
development evidence with the single known opened loser. All four policies
reduced P&L in the original 96 markets and in both earlier-64 and later-32
development diagnostics. Every combined paired interval crossed zero.

Therefore the 90-second/25% row is retained only as an adaptive insurance
hypothesis. It is not selected as H3 v2 and does not justify repairing the
failed holdout conclusion.

## Final disposition

1. Frozen H3 is **not supported** by its sealed holdout.
2. No stop, runner, re-entry, early-entry, velocity, acceleration, or partial
   timeout overlay graduates.
3. Further H3 threshold search stops. The apparent edge is too thin relative
   to one binary full-capital loss and the degrees of adaptive selection.
4. The analyzers, tests, specifications, and generated reports remain audit and
   learning artifacts.
5. All 122 KXBTC15M markets are development-only evidence from this point.
6. KXBTC15M remains a qualified secondary benchmark, not the primary next
   strategy target.

## Return to the published project path

The next milestone remains rooted in the published Checkpoint-10 endpoint:

```text
11 - KXBTCD Baseline Expansion and Reference Feed Reassessment
```

Its updated emphasis is model readiness rather than another heuristic search:

- retain Kalshi as the current read-only research venue;
- retain modern-regime KXBTCD as the primary BTC family;
- define a causal target for the conditional KXBTCD settlement-price
  distribution and coherent per-strike probabilities;
- compare market-implied probability, regularized linear/ordinal baselines,
  and bounded tree-based models before considering greater complexity;
- group all strikes and observations from one settlement cluster in the same
  chronological partition;
- define a new development/validation/holdout firewall before labels or model
  selection;
- define the information hypothesis before selecting Coinbase, Kraken, BRTI,
  or another external source;
- keep manual feature-weight tuning and reuse of any opened holdout prohibited;
- model executable prices, fees, depth, latency, missed fills, and uncertainty
  before any paper-strategy eligibility decision.

This chooses the next scientific target. It does not establish that KXBTCD,
Kalshi, or any model is profitable.

## Safety

All work remained public and read-only. No authentication, account access,
API/private key, external order, cancellation, paper/demo execution, production
execution, or real-money authorization was used.

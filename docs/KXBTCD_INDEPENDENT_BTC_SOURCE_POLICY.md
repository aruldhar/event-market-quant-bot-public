# KXBTCD Independent-BTC Source Policy and Evidence Gate Freeze

**Checkpoint:** 19D-B
**Status:** FROZEN — OUTCOME-BLIND SOURCE POLICY
**Policy fingerprint:** `6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18`
**Parent Checkpoint-19 protocol:** `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
**Parent 19C audit:** `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`
**Parent 19D-A audit:** `023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`

## Purpose

Checkpoint 19D-B converts the outcome-blind engineering evidence from 19C and
19D-A into a fixed source-quality contract before Candidate E is specified or
any E1 outcomes are used.

This checkpoint freezes data-source identity, deterministic source roles,
quality gates, causal lookback behavior, and minimum source/calendar evidence
requirements. It does not freeze Candidate E's feature formula, model family,
regularization, scoring gate, or final E3 terminal rule.

## Source roles

### Live primary

`coinbase.exchange.public_rest.product_book.btc_usd.v1`

Use the Coinbase Exchange BTC-USD level-1 best bid and ask. The source state
price is the arithmetic midpoint:

`S_primary = (best_bid + best_ask) / 2`

### Live verifier

`kraken.spot.public_rest.pretrade.btc_usd.v1`

Use Kraken BTC/USD PreTrade best bid and best ask as an independent verifier.
The verifier midpoint is not averaged into the feature.

### Historical primary

`coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1`

Use the exact last fully completed one-minute candle and its close. Coinbase
documents the close as the last trade in the bucket.

### Historical verifier

`kraken.spot.public_rest.posttrade.btc_usd.v1`

Use the latest trade in the exact required minute whose `publication_ts` is not
later than the KXBTCD decision timestamp.

## Why primary + verifier instead of consensus

19D-A showed 100% exact-minute Coinbase reconstruction and one genuine
zero-trade Kraken minute. More importantly, preserved 19C Kraken BBO data showed
that a successful request can contain an old bid or ask level. Therefore
blindly averaging the two venues can inject stale verifier state into the
feature.

Coinbase is the deterministic primary. Kraken remains mandatory for state
eligibility because disagreement and independent venue confirmation are useful
quality checks. No learned weighting, best-source selection, or fallback is
allowed.

## Frozen live quality gates

A live state is eligible only if all of the following hold:

| Gate | Maximum |
|---|---:|
| Coinbase local first-seen age | 5.0 s |
| Kraken local first-seen age | 5.0 s |
| Coinbase source-event age | 10.0 s |
| Kraken conservative BBO publication age | 60.0 s |
| Coinbase/Kraken receive skew | 1.0 s |
| Coinbase/Kraken midpoint disagreement | 5.0 bp |
| Absolute local wall-clock offset bound | 1.0 s |

Kraken BBO freshness is the age of the **older** of its best bid and best ask.

These are source-quality gates, not model hyperparameters. They were selected
without KXBTCD outcomes.

## Threshold rationale

- Both 19D-A local-first-seen p99 values were below 4.6 s, so 5 s removes the
  observed long local-age tails without tuning against labels.
- Coinbase source-event age p99 was about 5.68 s; 10 s is a simple rounded
  guardrail well below the ~42.9 s maximum tail.
- Kraken conservative BBO age p95 was about 49.2 s but p99 was about 354 s;
  60 s keeps ordinary slower level updates while rejecting the clearly stale
  tail. Kraken is verifier-only.
- 19C receive skew p95 was 234 ms; 1 s allows ordinary sequential REST timing
  but rejects the isolated 9.687 s tail.
- Historical current-price disagreement p99 was about 4.47 bp; 5 bp is a round
  pre-outcome boundary below the observed ~6.04 bp maximum.

## Fail-closed behavior

Any missing source, malformed BBO, missing required timestamp, age violation,
clock violation, receive-skew violation, or disagreement violation makes the
state unavailable.

Do not:

- substitute another exchange;
- use Coinbase alone when Kraken fails;
- use Kraken alone when Coinbase fails;
- average sources after one fails a quality gate;
- carry a stale source forward;
- interpolate from future observations;
- relax a threshold after outcome access.

## Causal five-minute lookback

If a later Candidate-E menu uses a five-minute BTC return, the source
observation must already have been received at or before the exact `T-300s`
target. The maximum allowed live target gap is 5 s. Future observations are
prohibited.

For historical reconstruction, the exact completed-minute bucket five minutes
earlier is required. Historical gap tolerance is zero and no missing minute may
be imputed.

This freezes only the source-alignment rule. It does not require Candidate E to
use a five-minute-return feature.

## Historical/live interpretation boundary

The historical completed-minute primitives are reproducible reconstruction
sources, not historical BBO archives. Coinbase candles and Kraken PostTrade are
not claimed to equal live BBO snapshots.

Historical reconstruction may audit or replay a frozen candidate, but it may
not rescue a missing prospectively required live state in E1/E2/E3. A later
Candidate-E predeclaration must state exactly which frozen source surface it
uses and may not mix incompatible semantics silently.

## Evidence-tier minimums

### E1 — successor design

- starts strictly after the 19D-B source-policy freeze;
- at least 168 source-eligible KXBTCD events;
- at least 7 distinct UTC dates;
- chronological span at least 168 hours;
- all 24 UTC hour-of-day bins represented;
- at least 90% of all predeclared scheduled states source-eligible;
- each counted event retains at least two-thirds of its scheduled states.

### E2 — final fit

Same numerical minimums as E1, but E2 starts only after the successor
specification is frozen from E1.

### E3 — untouched prospective test

- starts only after the final E2 model is frozen;
- at least 336 source-eligible events;
- at least 14 distinct UTC dates;
- chronological span at least 336 hours;
- all 24 UTC hour-of-day bins represented;
- at least 90% scheduled-state source eligibility;
- each counted event retains at least two-thirds of its scheduled states.

If a tier does not meet these source/calendar gates, extend it prospectively
without opening outcomes. Do not relax the gates to finish sooner.

## Facts, assumptions, hypotheses, unresolved questions

### Facts

- 19C had 5,758 external cycles, 288 KXBTCD snapshots, 27 events, and no raw or
  runtime errors.
- 19D-A Coinbase exact-minute coverage was 100%.
- 19D-A Kraken exact-minute current and lookback coverage were each 287/288.
- The two row-level Kraken exclusions were one genuine zero-trade minute.
- 19D-A current cross-source disagreement p99 was about 4.47 bp.
- Kraken live BBO publication freshness had a much heavier tail than local
  request freshness.
- No KXBTCD outcomes were used to choose this policy.

### Assumptions

- One complete UTC week is the smallest reasonable calendar unit for E1/E2
  because KXBTCD events are approximately hourly and Candidate C/D exposed
  temporal instability.
- Two UTC weeks are a more defensible minimum for the one-time E3 claim.
- The selected quality thresholds are operationally feasible outside the
  single 19C day; this must be monitored prospectively.

### Hypotheses

- The frozen gates will retain at least 90% of scheduled states over future
  weeks.
- Coinbase-primary plus Kraken-verifier will provide a stable independent BTC
  state suitable for testing Candidate E.

### Unresolved

- Candidate E's exact feature menu (`d_BTC`, `r_5m`, or a tiny ablation set).
- Model form and any regularization grid.
- Exact KXBTCD TTC schedule for E1.
- E1 chronological scoring layout and Candidate-E advancement gate.
- Final E3 temporal-stability rule.

Those belong to the next Checkpoint-19 substep and must be frozen before E1
outcomes are used.

## Safety

19D-B remains read-only. Candidate-E fitting, outcome access for model design,
Checkpoint-17 terminal reuse, paper/demo/live execution, orders, cancellations,
transfers, and sub-second lead/lag inference remain prohibited.

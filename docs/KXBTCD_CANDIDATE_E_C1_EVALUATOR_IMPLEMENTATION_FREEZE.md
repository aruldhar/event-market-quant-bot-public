# KXBTCD Candidate-E C1 Evaluator Implementation Freeze

Checkpoint: **21C**

## Purpose

Freeze the exact network-capable implementation that may later open the already
frozen C1 outcome allow-list. Checkpoint 21C itself is outcome-blind: it performs
zero C1 outcome requests and zero model fitting.

## Frozen parents

- Checkpoint-21A protocol fingerprint:
  `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- Champion-R0 fingerprint:
  `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- Champion-R0 `beta_distance`:
  `0.014447239079794087`
- C1 validation fingerprint:
  `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- C1 cohort fingerprint:
  `7f53764ca50d4a5e00a4d12d0cebda566a1333a6951b2686b2c9d06631c1ca36`
- C1 pre-outcome row fingerprint:
  `6d02d8b484813760a87a7daea05ecf994e18ae875e7e066e9b097ac830e01af8`

## Exact C1 identity

- 500 eligible events
- five chronological blocks B0-B4
- exactly 100 events per block
- 14,887 pre-outcome rows
- 2,491 unique outcome markets
- 506 strict-tail candidate identities inspected during pre-outcome materialization
- strict-tail range consumed: `[3200, 3706)`
- strict never-materialized tail remaining: 5,725
- protected floor: 4,500

## One-time exposure contract

Before any HTTP client is constructed, the future C1 runner must:

1. fetch `origin` and require clean synchronized `main`;
2. validate the safely closed Checkpoint-21C implementation receipt;
3. validate the frozen implementation byte hashes;
4. validate Champion-R0 and the exact C1 validation freeze;
5. validate the local C1 cohort/row artifacts against their frozen fingerprints;
6. reconstruct the exact 2,491-market C1 allow-list;
7. hard-deny every H1/H2/H3 event and market identity;
8. write an immutable C1 exposure-attempt receipt marking the full C1 cohort
   permanently exposed.

Only after those checks may the read-only historical outcome client be created.

A fresh second C1 attempt is prohibited. An interrupted attempt may resume only
from its recognized failed/running manifest and validated append-only outcome
journal. Already journaled outcomes are not re-requested.

## Outcome source

The future evaluation uses public read-only Kalshi historical market retrieval:

`/historical/markets/{market_ticker}`

Each requested identity must be in the exact frozen C1 allow-list. The returned
market identity must match the request, status must be `finalized`, and result
must be `yes` or `no`. Raw response persistence occurs before semantic use via
the existing public raw-first client.

## Frozen scoring

The future evaluator applies Champion-R0 without fitting:

`logit(p) = logit_clip_0.001(q_market) + 0.014447239079794087 * d_BTC`

Raw Kalshi midpoint remains the benchmark. Metrics use equal total weight per
event and equal weight per scored row within an event.

C1 PASS requires every predeclared Checkpoint-21A condition:

- pooled event-equal raw-minus-champion log-loss delta `> 0`;
- pooled event-equal raw-minus-champion Brier delta `>= 0`;
- champion log-loss win in at least 4 of 5 chronological blocks;
- newest B4 log-loss win;
- median event-level raw-minus-champion log-loss delta `> 0`;
- finite, converged, positive frozen `beta_distance`;
- all five structural roles and all six TTC targets retained in every block;
- source, timing, lineage, firewall, and finite-metric checks PASS.

Primary ties fail.

## Prohibited behavior

Checkpoint 21C and the later C1 evaluator prohibit:

- fitting or refitting on C1;
- candidate selection on C1;
- feature changes on C1;
- hyperparameter search on C1;
- C2/C3 materialization or outcome access;
- strategy research based on C1 before the frozen result exists;
- paper, demo, or real-money execution;
- order placement, cancellation, transfers, or mock-broker behavior.

## Interpretation

Checkpoint 21C freezes software behavior only. It is not a C1 result and does
not establish predictive improvement, executable edge, or profitability.

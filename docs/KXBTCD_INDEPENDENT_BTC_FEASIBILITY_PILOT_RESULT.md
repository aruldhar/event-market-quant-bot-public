# KXBTCD Independent-BTC Feasibility Pilot Result

**Checkpoint:** 19B
**Status:** ENGINEERING FEASIBILITY PASS — THRESHOLDS AND CANDIDATE E REMAIN UNFROZEN
**Run:** `collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960`
**Protocol fingerprint:** `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
**Audit design fingerprint:** `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`

## Scope

This result records the frozen 420-second Checkpoint-19B outcome-blind engineering pilot. It is source-availability and timing evidence only. It is not model evidence and does not authorize Candidate-E fitting, outcome access, paper execution, demo execution, order placement, transfers, or real-money execution.

## Manifest integrity

The completed collection manifest is:

`data/manifests/2026/08/16/collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960.json`

The manifest recorded:

- schema `collection_run_manifest.v2`;
- completed status;
- 3 raw files;
- 462 raw API records;
- 0 raw error records;
- 3 derived CSV files;
- 13,390 total derived rows;
- 1 runtime event file;
- 464 runtime events;
- 0 runtime error events.

The raw request count decomposes exactly as:

- Coinbase: 210;
- Kraken: 210;
- Kalshi: 42.

The derived row count decomposes exactly as:

- feasibility rows: 13,356;
- structural exclusions: 0;
- summary rows: 34.

## Outcome-blind feasibility results

- External cycles: 210.
- KXBTCD snapshots: 42.
- Unique KXBTCD events: 3.
- Unique KXBTCD markets: 318.
- Every snapshot contained exactly 318 KXBTCD market rows.
- Coinbase request success rate: 1.0.
- Kraken request success rate: 1.0.
- Kalshi request success rate: 1.0.
- Both-source row availability rate: 1.0.
- Structurally usable row rate: 1.0.
- Structural exclusion count: 0.

Snapshot-level same-machine first-seen age diagnostics:

- Coinbase: p50 0.1875 s; p95 0.297 s; max 1.282 s.
- Kraken: p50 0.133 s; p95 0.63395 s; max 0.75 s.

Snapshot-level Coinbase/Kraken BBO-mid disagreement:

- p50 0.719803365910057 bp;
- p95 1.0871449989790267 bp;
- max 1.0896050134210689 bp.

External receive skew:

- p50 140 ms;
- p95 187.55 ms;
- max 765 ms.

Five-minute causal lookback:

- Coinbase: 11 / 42 KXBTCD snapshots;
- Kraken: 11 / 42 KXBTCD snapshots.

The 11/42 rate is consistent with the pilot's mandatory five-minute warm-up and is not interpreted as a feed failure.

## Coverage limitation

The pilot lasted about seven minutes and observed only three KXBTCD events. Time-to-close coverage was uneven:

- 0 to 30 minutes: 7,896 rows;
- 30 to 60 minutes: 0 rows;
- 1 to 4 hours: 0 rows;
- 4 to 24 hours: 3,360 rows;
- greater than 24 hours: 2,100 rows.

Therefore this pilot establishes that the collection/alignment path functions under one bounded window. It does **not** establish an acceptable permanent staleness cutoff, cross-source disagreement cutoff, consensus-price rule, E1/E2/E3 cohort size, Candidate-E formula, predictive improvement, or profitability.

## Decision

**Checkpoint-19B bounded pilot: PASS for engineering feasibility only.**

Do not freeze source-quality thresholds from this seven-minute pilot. Before E1, collect a longer outcome-blind availability window that covers materially broader calendar and KXBTCD time-to-close regimes. Use that evidence only for source availability/timing/coverage and for predeclaring future source-quality and evidence-cohort requirements.

Candidate E remains unfrozen. Candidate-E fitting remains prohibited. Outcome access remains prohibited. Checkpoint-17 terminal evidence remains prohibited. Execution remains prohibited.

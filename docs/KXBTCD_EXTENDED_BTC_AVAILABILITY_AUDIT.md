# KXBTCD Extended Independent-BTC Availability Audit

**Checkpoint:** 19C
**Status:** COMPLETED — EXTENDED ENGINEERING FEASIBILITY PASS
**Parent protocol fingerprint:** `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
**Parent 19B audit fingerprint:** `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`
**19C audit design fingerprint:** `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`

## Research question

Checkpoint 19B proved that Coinbase and Kraken BBO observations can be attached to live KXBTCD states with raw lineage and local first-seen timing. It did not provide enough calendar or TTC coverage to select permanent source-quality rules.

Checkpoint 19C asks only whether, across one continuous full-day window, the two independent BTC sources remain available and mutually consistent, whether a five-minute causal history can be reconstructed reliably, and which KXBTCD TTC/calendar regimes are observed.

## Frozen collection design

- Duration: `86400` monotonic seconds.
- Coinbase/Kraken target cadence: every `15` seconds.
- Open KXBTCD target cadence: every `300` seconds.
- Alternate Coinbase-first and Kraken-first.
- Request KXBTCD only after the current external attempts.
- Never burst-replay missed cycles.
- No duration or cadence command-line override.

The 24-hour window gives one complete UTC daypart cycle. Fifteen-second external sampling gives up to twenty observations in a five-minute history window. Five-minute KXBTCD snapshots reduce redundant full-ladder volume while remaining dense relative to hourly contract lifecycles.

## Failure semantics

A raw-preserved HTTP or transport failure is availability evidence and does not by itself invalidate the whole 24-hour audit.

Parser/schema ambiguity, partial KXBTCD pagination, local monotonic reversal, raw-persistence ambiguity, run-manifest failure, and runtime-event persistence failure remain fail-closed.

## Outputs

The run writes full protocol-valid feasibility rows, structural exclusions, one row per external cycle, one row per successful KXBTCD snapshot, UTC-hour coverage, a descriptive summary, raw archives, runtime events, and the standard run manifest.

The one-row-per-cycle file prevents source availability and cross-source disagreement from being statistically multiplied by the number of KXBTCD strikes in a ladder.

## Five-minute history diagnostic

19C records both the structural five-minute-history boolean and the gap from the exact five-minute target to the most recent already-received same-source observation. This is an outcome-blind timing diagnostic only; it does not freeze a future five-minute-return formula or alignment tolerance.

## Deliberately not frozen

19C does not select E1 source IDs, a staleness threshold, a disagreement threshold, a consensus-price rule, Candidate E, a five-minute return tolerance, E1/E2/E3 event/calendar requirements, or an advancement gate.

Those decisions may be made only after the complete 19C outcome-blind audit is inspected.

## Safety

Candidate-E fitting, outcome access, Checkpoint-17 use, sub-second lead/lag, paper/demo/live execution, order creation/cancellation, transfers, and real-money trading remain prohibited.

Passing 19C establishes extended data feasibility only; it cannot establish predictive edge or profitability.

<!-- CHECKPOINT19C_RESULT_CLOSEOUT_20260817 -->
## Completed 19C result — accepted 2026-08-17

Canonical run: `collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`.

Manifest integrity validation: **PASS**.

```text
raw records = 11,804
raw errors = 0
derived CSVs = 6
derived rows = 96,405
runtime events = 11,806
runtime errors = 0
worktree dirty at start = false
```

Outcome-blind audit result:

```text
external cycles = 5,758
KXBTCD snapshots = 288
feasibility rows = 90,288
unique events = 27
unique markets = 4,722
both-source external-cycle availability = 1.0
structurally usable row rate = 1.0
structural exclusions = 0
five-minute lookback row rate per source = 0.996477937267411
```

Cross-source disagreement (external-cycle level): p50 `0.7268472244022195` bp, p95 `2.7526752145628617` bp, max `5.347777694885947` bp.

External receive skew: p50 `156` ms, p95 `234` ms, max `9687` ms. The maximum was an isolated tail near 09:05 UTC rather than a source-request outage.

The audit also demonstrated why source quality must not be compressed into a single success flag: local-first-seen age, exchange/source-event publication freshness, request availability, causal lookback alignment, and cross-source disagreement are distinct observables.

### Final interpretation

Checkpoint 19C **passes extended engineering feasibility**. Coinbase and Kraken remain provisional independent-BTC source families suitable for the next outcome-blind source-quality/materialization freeze.

This result is not predictive evidence. It does not freeze Candidate E, a source-staleness threshold, cross-source disagreement threshold, consensus-price formula, five-minute-return tolerance, E1/E2/E3 cohort sizes, an advancement gate, or any execution policy.

Candidate-E fitting performed: false. Outcomes accessed: false. Checkpoint-17 terminal used: false. Execution performed: false. Orders placed: 0.

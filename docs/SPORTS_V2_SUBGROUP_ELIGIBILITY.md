# Sports V2 Outcome-Blind Subgroup Eligibility

## Status

**Predeclared before any Sports V2 outcome materialization.** Public/read-only analysis only.

## Purpose

The Sports V2 heterogeneity profile demonstrated that the broad `Sports` category contains different sports/leagues and different contract structures. Large aggregate event count therefore cannot, by itself, justify treating MLB, NFL, NBA, tennis, golf, coach-status markets, next-team markets, debut markets, and other products as one homogeneous predictive population.

This layer converts the already-outcome-blind heterogeneity profile into a deterministic sport × product-family cross-classification and freezes which subgroups have enough **pilot support** to deserve predeclared robustness checks in a later calibration experiment.

It does **not** inspect market outcomes and it does **not** authorize any calibration, predictive, profitability, paper-trading, or execution conclusion.

## Source

Input must be an independently rebuildable `sports_v2_heterogeneity_profile.v1` report sourced from a validated `collect_sports_v2_scalability` run.

No API calls are made. No raw market result fields are read. If an outcome key appears anywhere in the supplied profile object, subgroup eligibility fails closed.

## Cross-classification

Each event is assigned the already-frozen outcome-blind taxonomy labels:

- `sport_group`
- `product_family`

The new report emits:

1. sport-group eligibility;
2. product-family eligibility;
3. observed sport × product-family cell eligibility;
4. a full event-count matrix including zero cells.

The matrix is descriptive composition evidence. A cell with many events is not an edge.

## Frozen pilot-support gates

These gates determine whether a subgroup is an `eligible_robustness_stratum` for a future predeclared calibration analysis.

A subgroup must have:

- at least **10 independent events**;
- event-level any-valid-quote coverage >= **80%**;
- event coverage >= **50%** in each of:
  - 5–7 days before close;
  - 3–5 days before close;
  - 1–3 days before close;
- at least **50%** of events represented in all three time regions.

These thresholds are frozen before any Sports V2 outcomes are opened.

### Sport-group identity/diversity rule

A named sport robustness stratum must additionally:

- have a high-confidence sport identity;
- contain at least **2 distinct source series**;
- not have one source series exceed **75%** of the subgroup's events.

A dominant-series share above **50%** is a warning even when the subgroup remains eligible.

`Other/Unclassified` and `Ambiguous` sport groups are always descriptive-only.

### Product-family identity/diversity rule

A named product-family robustness stratum must additionally:

- have a high-confidence product-family identity;
- contain high-confidence events from at least **2 sports**;
- not have one high-confidence sport exceed **80%** of classified events in that product family.

A dominant-sport share above **60%** is a warning.

`other_or_unclassified_product_family` and `ambiguous_product_family` are always descriptive-only.

This prevents a product-family conclusion from silently being only an MLB or only an NFL conclusion.

### Sport × product-family cell rule

A named cross-cell must additionally:

- have high-confidence sport and product labels;
- contain at least **2 distinct source series**;
- not have one source series exceed **75%** of the cell's events.

A dominant-series share above **50%** is a warning.

## Interpretation

`eligible_robustness_stratum` means only:

> The 100-event outcome-blind pilot contains enough independent and sufficiently covered data for this subgroup to be carried forward as a **predeclared robustness stratum** in a future larger Sports V2 calibration study.

It does **not** mean:

- the subgroup is calibrated or miscalibrated;
- the subgroup is predictable;
- the subgroup has positive expected value;
- the subgroup should be traded;
- the subgroup can support a standalone result with the current pilot sample.

Every emitted row therefore keeps `standalone_calibration_claim_authorized=false`.

## Final-sample boundary

The existing Sports Calibration V2 requirement remains controlling: any later standalone time-band × probability-bin claim requires at least **100 unique events in that cell**, alongside the broader final-sample and holdout requirements.

A pilot-supported subgroup that does not reach final-sample requirements must be reported as sample-limited rather than merged post hoc with unrelated groups.

## Why this addresses Sports heterogeneity

The framework separates three possible effects before outcomes are known:

1. a platform-wide Sports calibration pattern;
2. a sport/league-specific pattern;
3. a contract-structure/product-family pattern.

The sport × product matrix also exposes confounding. For example, if a particular sport is mostly one product type, a later difference cannot automatically be attributed to the sport itself.

No new subgroup may be invented after outcome inspection merely because it improves a result.

## Accepted 100-event pilot eligibility result

Source run: `collect_sports_v2_scalability_20260809T074813046311Z_68eb260c`.

Outcome-blind accepted result:

- eligible sport robustness strata: MLB, NFL, NBA;
- eligible product-family robustness stratum: `coach_or_manager_status`;
- eligible sport x product-family strata: none;
- outcomes materialized: no;
- calibration analysis run: no;
- general Sports conclusion authorized: no.

This result is preserved as subgroup-support evidence only. Checkpoint 09 closes without opening Sports V2 outcomes.

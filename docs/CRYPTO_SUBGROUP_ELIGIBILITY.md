# Crypto Outcome-Blind Subgroup Eligibility

## Purpose

This Checkpoint-09 layer asks which Crypto subgroups have enough independent,
reconstructable historical market-state support to deserve **predeclared later
robustness testing**. It does not inspect final outcomes, estimate calibration,
train a model, estimate profitability, or authorize trading.

The layer consumes `crypto_heterogeneity_profile.v1` and applies the same
numerical support thresholds frozen for Sports V2. This avoids giving Crypto an
easier standard after its composition was observed. Only the names of the
identity dimensions change from sport/product to asset-or-driver/template.

## What "usable historical quote" means here

A usable quote is a real source-returned one-minute historical candle inside the
predeclared T-7d through T-1d region whose YES bid and YES ask can be reconstructed
and pass the collector's integrity rules, including an uncrossed bid/ask pair.

"Usable" means usable for **historical market-state reconstruction only**. It
does not mean executable, liquid, profitable, fresh enough for a forced anchor,
or fillable at the displayed ask. Execution research later must separately
model spread, fees, depth, latency, partial fills, missed fills, and uncertainty.

## Frozen support gates

A named robustness stratum requires all of the following before outcome access:

- at least 10 independent events;
- event quote coverage >= 80%;
- early, middle, and late time-region event coverage each >= 50%;
- at least 50% of events represented in all three time regions;
- at least two distinct source series where series diversity is applicable;
- no blocked identity classification;
- no dominant-series share above 75%.

A template-family claim additionally requires at least two high-confidence
asset/driver groups. This mirrors the Sports policy's requirement that a general
product-family claim span multiple sports. A template that is concentrated in
one driver group can still qualify as a **specific asset/driver x template**
cell if that cell independently meets all event, coverage, and series-diversity
gates.

Series shares above 50% create a warning and shares above 75% block the stratum.
For general template-family claims, a high-confidence asset group above 60%
creates a concentration warning and above 80% blocks the template claim.

## Interpretation

`eligible_robustness_stratum` means only that the subgroup has sufficient
pre-outcome data support to be named in a later predeclared robustness plan.
It does **not** mean the subgroup is predictive, miscalibrated, or profitable.

`descriptive_only` means the subgroup remains visible in the audit output but
cannot support a standalone later conclusion under this pilot policy.

Broad `Crypto` conclusions remain unauthorized by this layer.

## Accepted 25-event subgroup eligibility result

Source run: `collect_historical_feasibility_20260809T072159989703Z_6ae075ee`.

Outcome-blind accepted result:

- eligible asset/driver robustness stratum: `ProjectOrTokenSpecific`;
- eligible general contract-template robustness strata: none;
- eligible specific asset/driver x template stratum: `ProjectOrTokenSpecific | fdv_family`;
- eligible FDV cell: 12 events, 100% event quote coverage, 91.667% all-three-band event coverage;
- outcomes materialized: no;
- calibration/model analysis run: no;
- subgroup edge conclusion authorized: no;
- general Crypto conclusion authorized: no.

Checkpoint 09 preserves this FDV cell as a qualified secondary research branch but does not open outcomes or scale it immediately.

# Sports V2 Outcome-Blind Heterogeneity Profile

## Status

**Predeclared before any Sports V2 outcome materialization.** Public/read-only analysis only.

## Why this step exists

The 100-event Sports V2 scalability pilot establishes that the exact-time historical quote path works at useful scale. It does **not** establish that all Kalshi Sports markets belong to one homogeneous predictive population.

Sports contains materially different sports, leagues, and contract structures. MLB debut markets, NFL next-team markets, NBA personnel markets, combat-sports scheduling markets, and championship futures may have different participants, information flows, horizon behavior, and calibration properties. A large aggregate event count is therefore evidence of sample availability, not evidence that one pooled Sports model is scientifically appropriate.

Checkpoint 09 must characterize this heterogeneity **before outcomes are opened**.

## Source data

The profiler accepts only an independently valid `collect_sports_v2_scalability` manifest and its existing outcome-blind derived tables:

- events;
- markets;
- one-minute exact-time observations.

The profiler does not call Kalshi or any external source. It does not inspect raw nested market payloads for descriptive enrichment because those raw objects may contain result fields. This keeps the profiling boundary outcome-blind.

## Frozen taxonomy v1

Classification uses only source `series_ticker` text already present in the derived event table.

### Sport / league groups

A group is assigned only when a high-confidence token is present:

- MLB
- NBA
- NFL
- NHL
- College Basketball (`NCAAB`, `CBB`, `MARCHMADNESS`)
- College Football (`NCAAF`, `CFB`)
- Soccer (`SOCCER`, `FIFA`, `EPL`, `UCL`, `MLS`, `WORLDCUP`)
- Combat Sports (`UFC`, `MMA`, `BOXING`/`BOX`)
- Golf
- Tennis (`TENNIS`, `ATP`, `WTA`)
- Motorsports (`NASCAR`, `FORMULA1`, `F1`)

If no rule matches, retain `Other/Unclassified`. If multiple sport rules match, retain `Ambiguous`. Do not manually relabel events after seeing outcomes.

### Product-family tags

Separate source-ticker rules identify only obvious structural families:

- debut / first appearance;
- team destination / roster;
- coach / manager status;
- retirement;
- championship / title future;
- record / milestone;
- appearance / scheduling.

Anything else remains `other_or_unclassified_product_family`. This taxonomy is intentionally conservative. A source series is not assumed to be an economic product family merely because it has a distinct ticker.

## Metrics

For each sport group, product family, and sport × product cross-group report:

- unique events;
- unique source series;
- sampled markets;
- events with at least one valid quote;
- event quote coverage;
- valid one-minute observation count (descriptive only);
- median valid observations per event;
- event coverage in 5–7d, 3–5d, and 1–3d regions;
- all-three-band event coverage;
- largest-event observation share;
- top-decile event observation share.

No subgroup is declared profitable, predictive, calibrated, or superior from these metrics.

## Decision boundary

This profile is a **composition diagnostic**, not a strategy test.

After seeing the outcome-blind subgroup composition, Checkpoint 09 may predeclare which subgroup robustness tests are required for Sports V2. Those rules must be frozen **before** final YES/NO outcomes are materialized.

Until that happens:

- no broad "Sports calibration effect" conclusion is authorized;
- no sport-specific calibration claim is authorized;
- no product-family calibration claim is authorized;
- no subgroup may be selected because of outcome behavior;
- no calibration, profitability, paper-trading, authentication, or execution work is permitted by this profile.

## Downstream subgroup eligibility

The composition profile itself does not select subgroups. Its observed sport × product-family counts must next be passed through the frozen outcome-blind policy in `docs/SPORTS_V2_SUBGROUP_ELIGIBILITY.md`.

That policy determines which groups have enough pilot support to become predeclared robustness strata. It does not authorize outcome access, calibration conclusions, or strategy selection.

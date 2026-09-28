# Checkpoint 09 — Crypto Outcome-Blind Heterogeneity Profile

## Purpose

This diagnostic exists because a category label such as **Crypto** does not prove that all contracts share one predictive process. Before comparing Sports and Crypto as strategy branches, the project must measure Crypto heterogeneity using the same outcome-blind discipline applied to Sports.

This profile does **not** select a strategy, inspect final outcomes, estimate calibration, train a model, or estimate profitability.

## Source data

Use the independently validated Checkpoint-09 cross-category historical-feasibility run. Filter only rows whose source category is `Crypto`. Preserve the source manifest hash and require deterministic report reconstruction.

## Frozen diagnostic dimensions

### Asset / driver identity

High-confidence labels are assigned only from explicit source-series prefixes:

- `Bitcoin` — `KXBTC...`, except explicit cross-asset `KXBTCETH...`
- `Ethereum` — `KXETH...`
- `BNB` — `KXBNB...`
- `ZEC` — `KXZEC...`
- `CrossAssetBTCETH` — `KXBTCETH...`
- `ProjectOrTokenSpecific` — `KXFDV...`
- `Other/Unclassified` — everything else

The labels are structural descriptors, not claims that members are economically interchangeable.

### Contract-template family

Source-ticker patterns are grouped conservatively as:

- `fdv_family` — `KXFDV...`
- `min_or_max_family` — ticker contains `MINY` or `MAXY`
- `launch_or_deployment_family` — ticker contains `TOKENLAUNCH`, `MAINNET`, or `DEPLOY`
- `relative_or_ath_family` — ticker contains `VS` or `ATH`
- `other_or_unclassified_template_family` — no frozen match
- `ambiguous_template_family` — more than one frozen template matches

No external semantic interpretation is used to force ambiguous rows into a group.

## Metrics

For asset groups, template families, and observed asset × template cells, report:

- independent event count;
- unique source-series count;
- sampled market count;
- event quote coverage;
- early/middle/late time-to-close coverage;
- all-three-band event coverage;
- valid quote observations;
- median valid observations per event;
- maximum single-event observation share;
- top-decile observation share.

## Interpretation rule

The report is descriptive only. It may show that Crypto is more or less homogeneous than the broad category name suggests, but it cannot authorize a general Crypto edge, Sports-vs-Crypto strategy winner, calibration conclusion, model, profitability claim, or execution change.

Any later branch decision must consider both statistical sample support and process coherence; raw observation count alone is not evidence of independent information.

## Accepted 25-event profile result

Source run: `collect_historical_feasibility_20260809T072159989703Z_6ae075ee`.

Outcome-blind accepted result:

- events: 25;
- high-confidence asset/driver classification: 21/25 (84%);
- high-confidence template classification: 23/25 (92%);
- largest driver group: `ProjectOrTokenSpecific`, 13 events;
- largest template family: `fdv_family`, 12 events;
- broad Crypto conclusion authorized: no;
- outcomes materialized: no.

The result shows that Crypto is more cleanly classifiable than the 100-event Sports pilot but is not synonymous with Bitcoin and is not one homogeneous process.

# Research History

A chronological account of the whole project, from the first read-only scanner (August 2, 2026) to the closed edge search (September 28, 2026). Each phase links to the documents that hold its full evidence. Every result below was produced under a rule frozen before the outcomes were opened, unless it is explicitly labelled exploratory.

**Bottom line.** The project built a forecasting model that beat Kalshi's own prices on four separate out-of-sample cohorts, and then showed that the improvement could not be turned into money after spread, fees and liquidity. A broad search of eleven other directions reached the same conclusion: the inefficiencies are real but sized at or below the cost of trading them.

## Timeline at a glance

| Dates (2026) | Phase | Outcome |
| --- | --- | --- |
| Aug 2 - 9 | 1. Read-only data foundation | Raw-first archive, lineage, manifests, source registry, settlement evidence |
| Aug 9 | 2. Opportunity census and venue/strategy selection | Cross-category feasibility; Sports and Crypto pass quote gates, Weather and Commodities fail |
| Aug 9 | 3. KXBTCD monotone baseline | Tiny development gain; no gain on the untouched holdout |
| Aug 9 | 4. Sports calibration design | Closed on data-quality gates before outcomes were opened |
| Aug 11 - 14 | 5. KXBTC15M intramarket program | Development +$2.32/market became -$1.79/market on the sealed holdout |
| Aug 14 | 6. KXBTCD vs. BTC perpetuals preselection | KXBTCD chosen as the primary modeling head |
| Aug 14 - 16 | 7. Candidates B, C and D | B failed validation; C passed development but failed its locked test; D failed development |
| Aug 16 - 17 | 8. Independent BTC reference data | Coinbase/Kraken source audit and frozen source policy |
| Aug 17 - 18 | 9. Candidate E | Passed H1, H2, H3 and three fresh cohorts (C1-C3); log loss 69-80% lower than the market's |
| Aug 18 - Sep 3 | 10. Turning Candidate E into a strategy | Every entry policy failed or was inconclusive after costs |
| Sep 3 - 21 | 11. Production-shaped live system on AWS | Read-only live collector, restart durability, soak runs, 33-lane shadow simulation |
| Sep 24 - 28 | 12. Kalshi edge search | Eleven directions closed; one preregistered forward test left open |

## Phase 1 - Read-only data foundation (Aug 2 - 9)

The first rule was that nothing would be trusted that could not be audited. Before any modeling, the project built:

- **Raw-first archiving.** Every REST response is written to append-only JSON Lines before transformation, with UTC and monotonic timing, byte counts and SHA-256 digests. Collectors fail closed if the raw write fails.
- **Raw-to-derived lineage.** Every derived row carries `run_id`, `raw_session_id` and `raw_request_id`, and an offline validator reconciles both directions.
- **Run manifests.** Atomic per-run manifests record Git identity, artifact hashes, counts and completion state, and can be validated offline.
- **Structured runtime observability.** One event stream per run with stable event names and severities.
- **A machine-readable source registry** with authority, authentication, timestamp and source-quality boundaries, validated before any source can feed a model.
- **Settlement evidence.** A small settled-market sample established what Kalshi actually exposes after settlement. It caught the first semantic trap: the `status=settled` query filter returns objects whose status is `finalized`.

Documents: [PLATFORM_QUICKSTART.md](PLATFORM_QUICKSTART.md), [ARCHITECTURE.md](ARCHITECTURE.md), [RAW_DATA_SCHEMA.md](RAW_DATA_SCHEMA.md), [RUN_MANIFEST_SCHEMA.md](RUN_MANIFEST_SCHEMA.md), [RUNTIME_OBSERVABILITY_SCHEMA.md](RUNTIME_OBSERVABILITY_SCHEMA.md), [SOURCE_REGISTRY_SCHEMA.md](SOURCE_REGISTRY_SCHEMA.md), [SETTLED_MARKET_EVIDENCE.md](SETTLED_MARKET_EVIDENCE.md), [SETTLEMENT_VALIDATION.md](SETTLEMENT_VALIDATION.md), [SETTLEMENT_EDGE_CASES.md](SETTLEMENT_EDGE_CASES.md), [KALSHI_HISTORICAL_ENDPOINT_VALIDATION.md](KALSHI_HISTORICAL_ENDPOINT_VALIDATION.md), [TIME_ALIGNMENT_POLICY.md](TIME_ALIGNMENT_POLICY.md), [SOURCE_QUALITY_POLICY.md](SOURCE_QUALITY_POLICY.md).

## Phase 2 - Opportunity census and venue selection (Aug 9)

Rather than assume Bitcoin was the right place to look, the project first asked where the strongest evidence of an executable edge might be, across venues and market categories. A cross-category historical feasibility pilot collected 100 events, 161 markets and 46,972 one-minute quote observations without opening any outcomes.

| Category | Event quote coverage | Status |
| --- | --- | --- |
| Sports | 96% | pass (concentration warning) |
| Crypto | 96% | pass (concentration warning) |
| Climate and Weather | 32% | failed the quote gate |
| Commodities | 4% | failed the quote gate |

A key methodological point from this phase: raw one-minute rows are not independent samples. In both passing categories the largest single event supplied about 39% of observations, so observation counts could not be used as sample size.

Documents: [VENUE_STRATEGY_SELECTION.md](VENUE_STRATEGY_SELECTION.md), [OPPORTUNITY_CENSUS_SCHEMA.md](OPPORTUNITY_CENSUS_SCHEMA.md), [HISTORICAL_FEASIBILITY_EXPERIMENT.md](HISTORICAL_FEASIBILITY_EXPERIMENT.md), [HISTORICAL_FEASIBILITY_RESULT.md](HISTORICAL_FEASIBILITY_RESULT.md), [CRYPTO_HETEROGENEITY_PROFILE.md](CRYPTO_HETEROGENEITY_PROFILE.md), [CRYPTO_SUBGROUP_ELIGIBILITY.md](CRYPTO_SUBGROUP_ELIGIBILITY.md).

## Phase 3 - KXBTCD monotone baseline (Aug 9)

KXBTCD markets ask whether BTC will be above a strike at a set time, so a ladder of strikes should be monotone. The first model projected raw midpoints onto a non-increasing curve (isotonic regression) and asked whether that improved calibration.

- Development: log loss 0.12295 -> 0.12261, a favourable but tiny gain.
- Untouched holdout: every ladder was already monotone, so the projection changed nothing (delta exactly 0).

The small development improvement did not replicate. Documents: [CHECKPOINT_10_RESULT.md](CHECKPOINT_10_RESULT.md), [KXBTCD_BASELINE_EXPERIMENT.md](KXBTCD_BASELINE_EXPERIMENT.md), [BTC_RESEARCH_UNIT_INVENTORY.md](BTC_RESEARCH_UNIT_INVENTORY.md), [BTC_FAMILY_QUOTE_FEASIBILITY.md](BTC_FAMILY_QUOTE_FEASIBILITY.md).

## Phase 4 - Sports calibration design (Aug 9)

A preregistered calibration experiment on Kalshi sports markets was designed with a 70/30 chronological development/holdout split and event-clustered uncertainty. Its outcome-blind freshness gate could not produce an acceptable quote-age rule, and a redesigned V2 passed scalability but not subgroup eligibility. The phase closed **without opening any sports outcomes**: blocked data was not converted into a positive or negative result. Sports returned later in the edge search (Phase 12).

Documents: [SPORTS_CALIBRATION_EXPERIMENT.md](SPORTS_CALIBRATION_EXPERIMENT.md), [SPORTS_CALIBRATION_EXPERIMENT_V2.md](SPORTS_CALIBRATION_EXPERIMENT_V2.md), [SPORTS_STALENESS_PILOT.md](SPORTS_STALENESS_PILOT.md), [SPORTS_V2_SCALABILITY_PILOT.md](SPORTS_V2_SCALABILITY_PILOT.md), [SPORTS_V2_SUBGROUP_ELIGIBILITY.md](SPORTS_V2_SUBGROUP_ELIGIBILITY.md).

## Phase 5 - KXBTC15M intramarket program (Aug 11 - 14)

Kalshi's 15-minute Bitcoin markets were studied at the intramarket level: reversion, lead-lag against BTC, entry states, and about twenty preregistered exit and stop-rule variants (time windows, probability bands, velocity stops, target protection, partial exits, latency stress). A continuous recorder captured the order books.

The final frozen rule (H3) looked excellent in development and failed its one-shot sealed holdout:

| | Development (96 markets) | Sealed holdout (26 markets) |
| --- | --- | --- |
| Mean P&L per eligible market | +$2.32 | -$1.79 |
| Profitable fills | 100% | 92.9% |
| Full-capital losses | 0 | 1 (-$99.83) |

The single loss came from a 96c entry that could not be liquidated before close. High win rates with a rare total loss is the classic profile of selling tail risk. Threshold search stopped here. Documents: [KXBTC15M_INTRAMARKET_REVERSION.md](KXBTC15M_INTRAMARKET_REVERSION.md), [KXBTC15M_H1_PREREGISTRATION.md](KXBTC15M_H1_PREREGISTRATION.md), [KXBTC15M_H3_RESEARCH_CLOSEOUT.md](KXBTC15M_H3_RESEARCH_CLOSEOUT.md) and the `KXBTC15M_*_SPEC.md` files.

## Phase 6 - KXBTCD vs. BTC perpetuals preselection (Aug 14)

A read-only gate compared KXBTCD event contracts with Kalshi's BTC perpetual futures. KXBTCD won as the primary validation head: at least 4,000 saved settled events over 172 day blocks and 25 week blocks, a simpler binary settlement target, and no funding, margin or liquidation mechanics. Documents: [KXBTCD_VS_BTC_PERPETUALS_PRESELECTION_GATE.md](KXBTCD_VS_BTC_PERPETUALS_PRESELECTION_GATE.md), [BTC_STATE_FEATURE_CONTRACT.md](BTC_STATE_FEATURE_CONTRACT.md), [REFERENCE_FEED_SELECTION.md](REFERENCE_FEED_SELECTION.md).

## Phase 7 - Candidates B, C and D (Aug 14 - 16)

A frozen KXBTCD dataset was built first: 295 events, 55-to-30-minute time-to-close anchors, a 60-second staleness limit, and a chronological split of 175 train / 56 validation / 64 locked-test events. Locked-test labels stayed sealed until a candidate earned them.

| Candidate | Idea | Result |
| --- | --- | --- |
| B - market-context logistic | Adjust the market price with context features | **Failed validation**: log loss 0.1456 vs. raw 0.1423. Locked test stayed sealed. |
| C - market x spread interaction | Let the adjustment depend on the bid-ask spread | **Passed development** (OOF log loss 0.1465 -> 0.0768, 4/4 blocks) then **failed its one-time locked test** (0.0522 raw vs. 0.0685 model) |
| D - market-logit recalibration | Shift and rescale the market's own logit | **Failed development**: won only 3 of 5 blocks and lost the newest |

Candidate C is the most instructive result in the project. A large, block-consistent development gain reversed on 64 untouched events. The generalization review that followed was restricted to development data, so the exposed test could never be used to design the successor. Documents: [KXBTCD_PREOUTCOME_DATASET_AND_CANDIDATE_B.md](KXBTCD_PREOUTCOME_DATASET_AND_CANDIDATE_B.md), [KXBTCD_CANDIDATE_B_TRAIN_VALIDATION_EVALUATION.md](KXBTCD_CANDIDATE_B_TRAIN_VALIDATION_EVALUATION.md), [KXBTCD_CANDIDATE_B_FAILURE_ANALYSIS_AND_CANDIDATE_C_PREDECLARATION.md](KXBTCD_CANDIDATE_B_FAILURE_ANALYSIS_AND_CANDIDATE_C_PREDECLARATION.md), [KXBTCD_CANDIDATE_C_TERMINAL_LOCKED_TEST_EVALUATION.md](KXBTCD_CANDIDATE_C_TERMINAL_LOCKED_TEST_EVALUATION.md), [KXBTCD_CANDIDATE_C_GENERALIZATION_FAILURE_REVIEW.md](KXBTCD_CANDIDATE_C_GENERALIZATION_FAILURE_REVIEW.md), [KXBTCD_CANDIDATE_D_DEVELOPMENT_EVALUATION.md](KXBTCD_CANDIDATE_D_DEVELOPMENT_EVALUATION.md).

## Phase 8 - Independent BTC reference data (Aug 16 - 17)

Candidates B-D only rearranged information already in Kalshi's quote. The successor protocol asked a different question: does information from outside Kalshi help? That required a trustworthy independent BTC price.

- A 24-hour outcome-blind availability audit captured 11,804 raw records and 96,405 derived rows with zero errors.
- Historical reconstruction achieved 100% Coinbase coverage and 99.3% two-source coverage; Coinbase and Kraken disagreed by a median 0.72 basis points.
- A source-quality trap surfaced: Kraken's receive time can look fresh while one side of its book is minutes old. Coinbase became the primary source.

Documents: [KXBTCD_SUCCESSOR_RESEARCH_PROTOCOL.md](KXBTCD_SUCCESSOR_RESEARCH_PROTOCOL.md), [KXBTCD_INDEPENDENT_BTC_FEASIBILITY_AUDIT.md](KXBTCD_INDEPENDENT_BTC_FEASIBILITY_AUDIT.md), [KXBTCD_EXTENDED_BTC_AVAILABILITY_AUDIT.md](KXBTCD_EXTENDED_BTC_AVAILABILITY_AUDIT.md), [KXBTCD_INDEPENDENT_BTC_HISTORICAL_MATERIALIZATION_AUDIT.md](KXBTCD_INDEPENDENT_BTC_HISTORICAL_MATERIALIZATION_AUDIT.md), [KXBTCD_INDEPENDENT_BTC_SOURCE_POLICY.md](KXBTCD_INDEPENDENT_BTC_SOURCE_POLICY.md), [KXBTCD_CANDIDATE_E_COINBASE_PRIMARY_SOURCE_AMENDMENT.md](KXBTCD_CANDIDATE_E_COINBASE_PRIMARY_SOURCE_AMENDMENT.md).

## Phase 9 - Candidate E (Aug 17 - 18)

Candidate E keeps Kalshi's price as the anchor and adds one independent term, the log distance between Coinbase spot and the strike:

```
logit(p) = logit(q_market) + beta * d_BTC,     d_BTC = 10,000 * ln(S_t / K)
```

One free parameter, fitted once per stage, never tuned on a test cohort. A richer distance-plus-momentum variant was also predeclared and rejected in H1 in favour of the simpler model.

| Stage | Events | Market log loss | Candidate E | Blocks won |
| --- | --- | --- | --- | --- |
| H3 locked test | 750 | 0.1379 | 0.0389 | 5/5 |
| C1 fresh cohort | 500 | 0.1708 | 0.0532 | 5/5 |
| C2 fresh cohort | 500 | 0.1676 | 0.0506 | 5/5 |
| C3 fresh cohort | 500 | 0.1210 | 0.0237 | 5/5 |

Each cohort was materialized outcome-blind and frozen before labels were opened, and each was used exactly once. The final champion was fitted on 4,500 events / 123,520 rows (beta = 0.0149), with 4,676 events left untouched in reserve.

**Interpretation.** Kalshi's KXBTCD quotes lag the spot price, and a single spot-distance term corrects most of that lag. This is strong, replicated predictive evidence. It is not yet evidence of profit.

Documents: [KXBTCD_CANDIDATE_E_PREDECLARATION.md](KXBTCD_CANDIDATE_E_PREDECLARATION.md), [KXBTCD_CANDIDATE_E_H1_HISTORICAL_DEVELOPMENT_EVALUATION.md](KXBTCD_CANDIDATE_E_H1_HISTORICAL_DEVELOPMENT_EVALUATION.md), [KXBTCD_CANDIDATE_E_H2_HISTORICAL_VALIDATION.md](KXBTCD_CANDIDATE_E_H2_HISTORICAL_VALIDATION.md), [KXBTCD_CANDIDATE_E_H3_HISTORICAL_LOCKED_TEST.md](KXBTCD_CANDIDATE_E_H3_HISTORICAL_LOCKED_TEST.md), [KXBTCD_POST_H3_CHAMPION_LIFECYCLE_AND_PROSPECTIVE_VALIDATION.md](KXBTCD_POST_H3_CHAMPION_LIFECYCLE_AND_PROSPECTIVE_VALIDATION.md), the `KXBTCD_CANDIDATE_E_C1/C2/C3_*` files and [KXBTCD_CANDIDATE_E_FINAL_HISTORICAL_FIT.md](KXBTCD_CANDIDATE_E_FINAL_HISTORICAL_FIT.md).

## Phase 10 - Turning Candidate E into a strategy (Aug 18 - Sep 3)

A better probability only pays if you can trade at the moment it disagrees with the market. This phase tested that with real historical quotes, exact fees and conservative fill assumptions.

| Attempt | What it tried | Result |
| --- | --- | --- |
| Execution archive | Reusable historical candles and trades for replay | 100-market pilot PASS; full archive audited |
| Entry Model v1 | A second model to predict which Candidate-E signals are real | **Rejected**: no better than Candidate E alone (1/5 blocks) |
| Strategy v1 - quoted entry and hold | Buy when model edge exceeds a threshold after fees | **FAIL**: best policy made +$2.64 over 159 entries in 2,570 events, lost money in the newest block and on H3 |
| Strategy v2 - reliability shrinkage | Blend model and market with a global weight | **FAIL** at every weight tested |
| Conditional-alpha | Learn when to trust the model from market state | **FAIL**: worse than Candidate E alone on log loss (0.0399 vs. 0.0374); an entry-score follow-up found no incremental signal |
| Order-book replay (Predexon) | 5.6M order-book delta rows across four July 10 events | Replay engine accepted as a sandbox |
| Continuous convergence and re-entry | Trade repeatedly through the hour | **Not evaluable**: the frozen strikes had no two-sided liquidity; liquidity sits within a few strikes of spot |
| Spot-relative V2 | Trade the strikes near spot where liquidity lives | July 10 official result: 27 exact / 33 censored paths, all 15 policies **inconclusive** |

The picture is consistent: the model's edge is largest exactly where the book is thinnest, and where there is liquidity the edge after spread and fees is roughly zero. Documents: `KXBTCD_CANDIDATE_E_STRATEGY_*`, `*_ENTRY_MODEL_V1_*`, `*_QUOTED_ENTRY_HOLD_V1_*`, `*_RELIABILITY_SHRINKAGE_*`, `*_CONDITIONAL_ALPHA_*`, `KXBTCD_PREDEXON_*`, `*_CONTINUOUS_*`, `*_SPOT_*`, `*_V2_*` and `*_JULY10_*`.

## Phase 11 - Production-shaped live system on AWS (Sep 3 - 21)

To test prospectively rather than historically, the project built a read-only live system and treated its reliability as a research requirement in its own right.

- **Live collector.** Authenticated read-only Kalshi order-book WebSocket plus Coinbase trades and candles, with raw archiving, sequence-gap detection and fail-closed readiness.
- **Restart durability.** A SQLite durable-state core, identity and raw-reference reconciliation, a restart gate state machine, a credential-boundary check, and bounded live reconnect and whole-process restart tests, each validated in stages.
- **AWS deployment.** Docker on an Amazon Linux EC2 host; host clock evidence from chrony published through a read-only file bridge and gated before any runtime starts; hourly raw segments archived off-site to S3.
- **Soak testing.** One-hour shakedowns completed with zero Kalshi sequence gaps and zero orders, signals or production writes. One 24-hour launch was rejected before measurement because Coinbase briefly returned an empty candle at a minute boundary; the fix was a typed, recoverable condition rather than accepting stale data.
- **Live shadow.** A shadow runner simulated 33 strategy lanes (edge thresholds, spot-relative strike sets, duration caps and trailing-lock exits) on the live feed, settled against official outcomes, with Grafana dashboards for health, decisions and P&L. Every order in this phase was simulated; none was sent.

Documents: [KXBTCD_CANDIDATE_E_PRODUCTION_RUNTIME_ARCHITECTURE.md](KXBTCD_CANDIDATE_E_PRODUCTION_RUNTIME_ARCHITECTURE.md), `KXBTCD_CANDIDATE_E_RESTART_DURABLE_STATE_*`, `KXBTCD_CANDIDATE_E_B5_*`, [KXBTCD_CANDIDATE_E_AWS_LINUX_HOST_VALIDATION.md](KXBTCD_CANDIDATE_E_AWS_LINUX_HOST_VALIDATION.md), [SOAK_OBSERVABILITY_IMPLEMENTATION.md](SOAK_OBSERVABILITY_IMPLEMENTATION.md), [CANDIDATE_E_LIVE_SHADOW_RESEARCH_PLAN.md](CANDIDATE_E_LIVE_SHADOW_RESEARCH_PLAN.md), [RISK_POLICY.md](RISK_POLICY.md), [V2_MICRO_PROBE_RUNBOOK.md](V2_MICRO_PROBE_RUNBOOK.md), and the `deploy/` folder.

## Phase 12 - Kalshi edge search (Sep 24 - 28)

With Bitcoin exhausted, a fast, lightweight search tested whether any other part of Kalshi had a tradeable inefficiency. Eleven directions were closed: BTC 15-minute markets, zero- and half-fee series, the Kalshi-Polymarket basis, weather settlement, weather forecasting, strike-ladder arbitrage (177,450 relations over 38,484 markets: one $0.13 violation), multi-outcome arbitrage (about 57,500 tests over 5,021 events: zero), weather market making (2.33M real trades), the sports favourite/longshot bias, sports in-game repricing, and a sports game-state model.

Along the way the project retracted one of its own findings: a +1.00 degF weather "edge" at t = +10.6 was an error in its own settlement proxy, caught by testing against the buckets Kalshi actually settled. One maker hypothesis survives, preregistered with a frozen evaluator for evaluation after 2026-11-01.

Documents: [KALSHI_EDGE_SEARCH_CLOSEOUT.md](KALSHI_EDGE_SEARCH_CLOSEOUT.md) and the files it links; scripts in [`scripts/kalshi_research/`](../scripts/kalshi_research/).

## What carried across the whole project

1. **Freeze first, then look.** Every model, split, evaluator and gate was fingerprinted before outcomes were opened. Exposed data was never reused as a test.
2. **Development wins are hypotheses.** Monotone baseline, KXBTC15M H3 and Candidate C all looked good in development and failed out of sample.
3. **Prediction is not profit.** Candidate E replicated four times as a forecaster and still could not clear spread, fees and liquidity.
4. **Weighted or normalized statistics fake edges.** Six documented cases; only a simulated decision at an executable price counts.
5. **Validate every proxy against the venue's own outcomes.** Five API field semantics and one settlement proxy were wrong on the first guess.
6. **Reliability is part of the research.** Fail-closed gates, raw lineage and restart tests are what made the negative results trustworthy.

For the canonical, checkpoint-by-checkpoint record, see [PROJECT_STATE.md](PROJECT_STATE.md), [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) and [DECISIONS.md](DECISIONS.md). [LEARNING_GUIDE.md](LEARNING_GUIDE.md) explains the statistics and market mechanics used throughout.

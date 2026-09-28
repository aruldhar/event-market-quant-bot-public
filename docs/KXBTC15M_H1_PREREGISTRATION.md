# KXBTC15M Intramarket Reversion — Development Preregistration

Status: frozen before development-set price/rebound analysis

## Scope and evidence boundary

This experiment uses the 126 consecutive KXBTC15M top-of-book recordings collected prospectively from 2026-08-11 through 2026-08-13. The artifact audit was outcome-blind.

- Development sequence: markets 1–100, ending `KXBTC15M-26AUG121430-30`.
- Untouched holdout: markets 101–126, beginning `KXBTC15M-26AUG121445-45` and ending `KXBTC15M-26AUG122100-00`.
- Primary quality gate: completed manifest; matching CSV hash, row count, run ID, and ticker; zero request/raw/runtime errors; zero orders; first valid quote within 45 seconds of open; final valid quote within five seconds of close; maximum pre-close observation gap no greater than five seconds.
- Eligible development markets fixed by the audit: 96.
- Eligible holdout markets fixed by the audit: 26. Holdout prices and strategy outcomes must not be inspected during development.
- Sensitivity quality gate: maximum pre-close observation gap no greater than two seconds. This leaves 94 development and 25 holdout markets.

These files contain top-of-book prices, not order-book depth. Results describe quote-level executable entry/exit prices for an infinitesimal order before fees. They do not establish fills for material size or net profitability.

## Price and timing definitions

- Contract side: YES or NO, analyzed symmetrically.
- Entry ask: the displayed best ask for the selected side.
- Exit bid: the displayed best bid for that same side at a later observation.
- Time remaining: source-defined market close time minus observation time.
- Two-sided quote: both bid and ask exist for the side.
- Entry spread: ask minus bid.
- A target is reached only when a later displayed bid is at or above the target. Later asks do not count as executable exits.

## Episode definition

A primary episode is a fresh downward entry into the 10–15 cent ask band for one side:

1. The side's ask is in `[0.10, 0.15]`.
2. The side has a bid and the entry spread is no greater than 0.03.
3. At least 60 seconds remain before close.
4. The ask was above 0.15 for at least five continuous seconds immediately before entry, allowing ordinary sub-two-second sampling gaps.
5. After an episode begins, another episode for that side cannot begin until its ask has again remained above 0.15 for at least ten continuous seconds.

This prevents hundreds of half-second snapshots in one excursion from being treated as independent opportunities. Multiple genuinely separate excursions in one market remain allowed, but all uncertainty estimates resample whole markets rather than individual episodes.

## Primary hypothesis H1

H1-R20-60: after a primary 10–15 cent entry episode, the same side reaches an executable bid of at least 0.20 within 60 seconds.

Reported quantities:

- episode count and distinct market count;
- success proportion;
- median and 90th-percentile time to target among successes;
- market-clustered bootstrap 95% confidence interval using 5,000 resamples and seed 20260813;
- fraction of eligible development markets containing at least one episode and at least one success.

The hypothesis is considered development-supported only if the lower bound of the market-clustered 95% confidence interval exceeds 0.50. This is an intentionally demanding repeatability criterion, not a claim of profitability.

## Predeclared secondary analyses

### H1 target ladder

For the same episodes, report executable-bid attainment of:

- 0.20 within 10, 30, 60, and 120 seconds;
- 0.30 within 60 and 120 seconds;
- 0.40 and 0.50 within 120 seconds and before close.

These estimates describe magnitude and speed. Only H1-R20-60 is the primary decision statistic.

### H2 — Time remaining

Classify entry episodes using fixed buckets:

- early: more than 10 and no more than 15 minutes remaining;
- middle: more than 5 and no more than 10 minutes;
- late: more than 2 and no more than 5 minutes;
- terminal: no more than 2 minutes.

H1-R20-60 success is compared across early, middle, and late buckets. Terminal behavior is descriptive because fixed horizons are censored by close. The predeclared directional hypothesis is that rebound success and bid availability weaken as close approaches.

### H3 — Current-side directional state

Using only the 60 seconds before entry, sample the side midpoint on a five-second grid. Require at least 80% grid coverage. Define signed directional efficiency:

`E = (midpoint_end - midpoint_start) / sum(abs(midpoint_change))`.

- falling: `E <= -0.35`;
- fluctuating: `-0.35 < E < 0.35`;
- rising: `E >= 0.35`.

The predeclared hypothesis is that falling episodes have lower H1-R20-60 success than fluctuating or rising episodes. No post-entry observation may contribute to this state label.

### H4 — Previous-market state

Compute whole-market YES directional efficiency from five-second midpoint samples. Compute the next market's first-five-minute YES directional efficiency the same way. Report:

- Spearman correlation between previous whole-market efficiency and next early-market efficiency;
- a falling/fluctuating/rising transition table using the same ±0.35 thresholds;
- next-market H1 episode and success rates stratified by previous-market state.

This hypothesis remains exploratory on the development set. It may enter the holdout only if a single direction and rule are selected before holdout inspection.

### H5 — YES/NO symmetry

Report H1-R20-60 success separately for YES and NO and their market-clustered difference. This checks whether an apparent effect is side-specific.

### H6 — Top-of-book liquidity

Report H1-R20-60 by entry spread bucket (`<=0.01`, `>0.01–0.02`, `>0.02–0.03`) and report side-bid availability by time-remaining bucket. The directional hypothesis is that wider spreads and lower bid availability correspond to weaker executable rebounds.

## Deferred questions

The following are not valid confirmatory tests with the uploaded top-of-book bundle:

- averaging-down or pooled-position profitability;
- tradeable dollar capacity;
- partial fills and missed fills;
- fee-adjusted net P&L;
- latency-sensitive order execution;
- whether Kalshi cash-out values would match a simulated liquidation.

They require raw depth plus an official fee model and explicit execution assumptions.

## Multiple testing and promotion rule

- H1-R20-60 is the only primary statistic.
- H1 target ladder and H2–H6 are secondary/exploratory diagnostics.
- Development findings do not authorize tuning on the holdout.
- Before holdout inspection, choose at most one primary H1 rule and at most two additional directional rules, including all thresholds and failure handling.
- Holdout decisions are evaluated at the market level. No new threshold may be invented after holdout results are seen.

## Missing quotes and failures

- Missing asks cannot create entries.
- Missing later bids cannot count as target attainment.
- Episodes are evaluated until their fixed horizon or market close, whichever occurs first.
- A market excluded by the quality gate is not reintroduced because its price path looks favorable.
- Results are repeated using the two-second maximum-gap sensitivity set.

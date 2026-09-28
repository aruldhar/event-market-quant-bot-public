# Checkpoint 19H-B — Candidate-E Coinbase-Primary Source Amendment

## Purpose

Checkpoint 19H-B amends only the historical/live BTC source *eligibility* policy for Candidate E before any new Candidate-E outcome is opened.

The Candidate-E model family, formulas, raw Kalshi benchmark, six TTC anchors, five structural strike roles, H1/H2/H3 sizes, chronological gates, untouched queue, reserve floor, and execution prohibition remain unchanged.

Frozen source-amendment fingerprint:

`b08da00a8f66817d9e3b600ccf091c8a4fc1ee92a0bed1c821d23bc321d9faba`

Parent 19G materialization contract:

`cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145`

## Outcome-blind evidence that triggered the amendment

The first 600 untouched queue identities were canonically materialized under the original 19G Coinbase+Kraken verification rule. No Candidate-E outcome was opened and no Candidate-E fit was performed.

Observed event eligibility:

- original Coinbase + Kraken + 5 bp veto: 303/600 = 50.50%
- both sources required but 5 bp disagreement veto removed: 459/600 = 76.50%
- Coinbase-only required: 459/600 = 76.50%

Events rescued solely by removing the blocking verifier rule: 156.

Anchor-level exclusion counts:

- current Coinbase/Kraken disagreement above 5 bp: 570
- 5-minute-lookback disagreement above 5 bp: 570
- missing Kraken current: 3
- missing Kraken lookback: 3

The evidence therefore shows that Kraken *availability* was not the material coverage bottleneck. The 5 bp cross-venue disagreement veto was.

## Accepted source architecture

### Candidate-E required source

Coinbase is the sole required independent BTC-state source.

Historical state:

- current state = exact close of the last fully completed UTC Coinbase one-minute candle at scheduled decision time T;
- 5-minute state = exact Coinbase completed-minute close 300 seconds before the current bucket;
- no future interpolation;
- no nearest-neighbor substitution;
- no carry-forward;
- no source substitution.

### Kraken role

Kraken is optional diagnostic evidence only.

Kraken:

- is not a Candidate-E model feature;
- is not required to build a Candidate-E historical row;
- is not required for anchor/event eligibility;
- cannot veto an otherwise valid Coinbase/Kalshi state because of cross-venue disagreement;
- may later run asynchronously as monitoring outside the lightweight Candidate-E live decision path.

The canonical Coinbase-primary historical materializer makes zero Kraken requests.

## Event eligibility

The existing 4-of-6 rule remains frozen.

An anchor counts when:

1. exact Coinbase current minute exists and is valid;
2. exact Coinbase 5-minute lookback exists and is valid; and
3. at least one q10/q30/q50/q70/q90 KXBTCD structural market has a valid real two-sided YES quote within the frozen 60-second staleness cap.

An event is eligible with at least four eligible anchors among 55m, 50m, 45m, 40m, 35m, and 30m before close.

## Sample-size decision

H1/H2/H3 remain 1,500 / 750 / 750.

The effective 600-event Coinbase-primary counterfactual eligibility rate was 76.5%. The minimum average rate needed to obtain 3,000 eligible events inside the 4,431-event materialization cap is approximately 67.70%.

Because the outcome-blind counterfactual rate is above that requirement, this amendment does not reduce the predeclared sample sizes.

The 5,000-event untouched reserve floor remains unchanged.

## Superseded 19G chunks

The six original 19G canonical chunks covering queue indices 0–599 remain preserved as source-feasibility evidence but may not enter the Coinbase-primary final freeze.

The Coinbase-primary canonical path uses a separate derived root and restarts at queue index 0. Re-materializing the same first 600 identities does not consume 600 additional unique reserve events; final reserve accounting is based on unique frozen queue indices under the effective canonical prefix.

## Basis points

A basis point (bp) is one hundredth of one percent:

`1 bp = 0.01% = 0.0001` in decimal-return form.

Therefore:

- 5 bp = 0.05%
- 10 bp = 0.10%
- 100 bp = 1.00%

At a BTC price of $100,000, a 5 bp price difference is approximately $50.

## Safety

- read-only historical collection only;
- no new Candidate-E outcomes;
- no Candidate-E fitting;
- no paper/demo/live execution;
- no orders, cancellations, transfers, or real-money trading.

<!-- CHECKPOINT19HC_FINAL_HISTORICAL_FREEZE_20260817 -->
## Checkpoint 19H-C ? final Candidate-E historical pre-outcome freeze

Checkpoint 19H historical materialization is complete under the frozen
Coinbase-primary source amendment.

Final freeze:
- canonical raw queue events materialized: 3200
- H1 train events: 1500
- H2 validation events: 750
- H3 locked-test events: 750
- ineligible events before the 3,000th eligible event: 147
- actual untouched tail remaining: 6231
- cohort-map fingerprint: `09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa`
- row-universe fingerprint: `e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5`
- exclusion fingerprint: `dd2877579bb800fc1d15ee3c05754947658dfdb552858d67f39b260e32aaf9c4`
- required BTC source: Coinbase
- Kraken required: False
- Candidate-E outcomes accessed: False
- Candidate-E fit performed: False
- execution authorized: False

Frozen stage boundaries:

- H1: 1500 events / 36314 rows; `2025-03-22T17:00:00Z` `KXBTCD-25MAR2213` through `2025-07-07T14:00:00Z` `KXBTCD-25JUL0710`; queue indices 0 through 1641.
- H2: 750 events / 22354 rows; `2025-07-07T15:00:00Z` `KXBTCD-25JUL0711` through `2025-08-25T04:00:00Z` `KXBTCD-25AUG2500`; queue indices 1642 through 2396.
- H3: 750 events / 22409 rows; `2025-08-25T13:00:00Z` `KXBTCD-25AUG2509` through `2025-10-12T22:00:00Z` `KXBTCD-25OCT1218`; queue indices 2397 through 3146.

Interpretation:
- Checkpoint 19H is a data/cohort freeze, not a predictive result.
- H1 labels may be opened only in the next explicitly authorized development checkpoint.
- H2 labels remain sealed until H1 selects exactly one Candidate-E specification.
- H3 labels remain sealed until H2 passes and the final H1+H2 parameters are frozen.
- The 6,231-event untouched tail remains protected for future evidence.

# Checkpoint 09 — Historical Feasibility Result

## Status

**Accepted outcome-blind data-feasibility and branch-design evidence, pending final checkpoint closeout.**

No final YES/NO outcomes were materialized by the feasibility collector or validators. No calibration, predictive model, execution simulation, or profitability analysis was run.

## Accepted cross-category pilot

Run ID:

```text
collect_historical_feasibility_20260809T072159989703Z_6ae075ee
```

Collection result:

```text
100 events
161 sampled markets
966 candlestick request chunks
46,972 real one-minute candle observations
46,972 valid uncrossed quote observations
34 event pages scanned
8 cross-tier list observations
8 markets observed off canonical tier
0 canonical recovery fetches
1 unclassifiable event skipped
market cutoff = 2026-06-10T00:00:00Z
authentication used = no
outcomes materialized = no
strategy/model analysis = no
orders placed = 0
```

Independent validation:

```text
Historical feasibility manifest validation: PASS
Event rows: 100
Market rows: 161
Window rows: 966
Observation rows: 46,972
Valid quote observation rows: 46,972
Raw records indexed: 1,473
Outcomes materialized: no
```

## Transport and sample-gate corrections

The initial implementation attempted one six-day one-minute candle request. A preserved source HTTP 400 reported:

```text
requested time range with candlesticks: 8640.000000, max candlesticks: 5000
```

The final collector keeps the scientific T-7d through T-1d region unchanged but fetches it through deterministic non-overlapping <=24-hour request chunks. Each chunk is raw-preserved and lineage-validated separately.

A separate smoke-test defect initially allowed `--events-per-category 2` to act as the qualification sample target. The final design freezes the research gate at **25 events/category**; smaller smoke collections always report `insufficient_event_sample`.

## Predeclared quote-feasibility results

| Category | Events | Markets | Event quote coverage | Early 5–7d | Middle 3–5d | Late 1–3d | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| Sports | 25 | 44 | 96% | 84% | 88% | 84% | pass with concentration warning |
| Crypto | 25 | 42 | 96% | 88% | 84% | 96% | pass with concentration warning |
| Climate and Weather | 25 | 50 | 32% | 16% | 28% | 32% | gate failed |
| Commodities | 25 | 25 | 4% | 0% | 0% | 4% | gate failed |

The Weather and Commodities result means only that the public Kalshi historical one-minute quote path, under this frozen observation contract, is not sufficiently complete for the next historical experiment. It is not evidence that those domains are efficiently priced or unprofitable.

## Concentration result

Raw one-minute candle rows are not independent samples.

Sports:

```text
valid observations = 8,788
median valid observations/event = 70
p90 = 913
largest event share = 39.372%
top 10% of events share = 68.229%
all-three-band event coverage = 72%
```

Crypto:

```text
valid observations = 30,911
median valid observations/event = 424
p90 = 2,379
largest event share = 38.339%
top 10% of events share = 67.821%
all-three-band event coverage = 84%
```

Therefore raw observation count must not be treated as statistical sample size or used to choose a branch.

## Sports V2 follow-up evidence

The exact-time Sports path was separately scaled to 100 events in:

`collect_sports_v2_scalability_20260809T074813046311Z_68eb260c`

Independent validation passed with 100 events, 169 markets, 52,331 valid quote observations, 1,532 raw records, 97% event quote coverage, and 79%/87%/90% early/middle/late event coverage.

Outcome-blind heterogeneity profiling found only 66% high-confidence sport classification and 59% high-confidence product-family classification. Under frozen subgroup support gates:

- MLB, NFL, and NBA qualified as sport robustness strata;
- `coach_or_manager_status` qualified as a product-family robustness stratum;
- no sport x product-family cell qualified.

Conclusion: Sports is technically feasible at scale, but broad Sports must not be treated as one homogeneous predictive population.

## Crypto follow-up evidence

The 25-event Crypto sample had 84% high-confidence asset/driver classification and 92% high-confidence contract-template classification.

The sample was not simply Bitcoin. It included project/token FDV markets, BTC/ETH/BNB/ZEC structures, launch/deployment questions, relative/ATH structures, and others.

Applying the same numerical subgroup support gates used for Sports produced:

- eligible asset/driver: `ProjectOrTokenSpecific`;
- eligible general template family: none;
- eligible specific cell: `ProjectOrTokenSpecific | fdv_family`.

The eligible FDV cell had 12 events, 100% event quote coverage, and 91.667% all-three-band coverage. It remains a qualified research subgroup only; 12 events do not establish an edge.

## Final branch reassessment

Checkpoint 09 explicitly **does not** conclude that Sports is the winner because it has more nominal events.

The project accepts that source `event` count is not a universal cross-domain measure of independent information. Different strategies require different dependence/evaluation clusters. For BTC in particular, multiple strikes or contracts tied to one settlement period may be useful observations but are strongly correlated and must not be counted as separate independent trials.

Final disposition:

- Sports V2: qualified secondary branch; calibration V2 remains unrun and outcomes hidden.
- Project/token FDV: qualified secondary Crypto subgroup; outcomes hidden.
- Climate and Weather: blocked only under the current historical quote path.
- Commodities: strongly blocked only under the current historical quote path.
- No category/subgroup is established as predictive, miscalibrated, profitable, or globally superior.

Checkpoint 09 stops further broad category ranking because additional ranking dimensions were producing diminishing decision value without outcome evidence.

The next milestone is **BTC-Specific Historical Research Design**. BTC is chosen as the next design target because it offers a coherent common underlying process and a clean opportunity to define correlated settlement/time clusters. This is not a profitability claim and does not select an external feed.

Checkpoint 10 must define the BTC market family, settlement/expiry clustering, simple hypothesis, historical support, and chronological evaluation rules before selecting predictive/reference feeds or building a model.

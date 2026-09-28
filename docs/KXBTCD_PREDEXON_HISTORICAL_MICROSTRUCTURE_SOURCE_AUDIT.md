# KXBTCD Predexon Historical Microstructure Source Audit

## Status

Checkpoint 21N-O source qualification: **PASS FOR EXPLORATORY / DEVELOPMENT HISTORICAL REPLAY**, subject to the fail-closed segment mask defined in `docs/KXBTCD_PREDEXON_SEGMENT_SAFE_REPLAY_DESIGN.md`.

This is a source-quality result, not a strategy-profitability result and not execution authorization.

## Question

Can Predexon historical Kalshi KXBTCD order-book deltas, when anchored by trusted full-book snapshots, support deterministic short-horizon historical microstructure replay for future Candidate-E entry/realizability research?

## Evidence scope

The already-purchased Predexon shard is:

- date: 2026-07-10 UTC;
- raw paid rows: 5,644,964;
- compressed Parquet bytes: 35,648,337;
- SHA-256: `43E9C5D99FB4001B866AE3E60021C8C10123DC1FB6248DF96084446FACE68509`;
- KXBTCD contracts: 623;
- independent KXBTCD hourly events: 4.

Event inventory:

| Event | Contracts | Paid rows |
| --- | ---: | ---: |
| `KXBTCD-26JUL1013` | 78 | 811,944 |
| `KXBTCD-26JUL1014` | 188 | 1,806,617 |
| `KXBTCD-26JUL1015` | 188 | 1,538,596 |
| `KXBTCD-26JUL1016` | 169 | 1,487,807 |

The statistical unit for future strategy evidence is the **hourly event**, not the strike contract. The 623 contracts therefore remain only four independent event windows.

## Free snapshot feasibility

A free Predexon order-book census over all 623 already-owned contract streams returned at least one snapshot for **623 / 623** contracts with zero HTTP/errors in that census.

This establishes seed availability, not continuous replay validity.

The earlier free archive audit on target `KXBTCD-26JUL1016-T63899.99` showed bursty snapshot coverage and large gaps, so free snapshots alone are not accepted as a continuous short-horizon replay source. They are used as trusted full-book anchors around the paid delta tape.

## Canonical YES-side delta mapping

Replay uses exact fixed-point arithmetic:

- snapshot `yes_bids` -> YES bid book;
- snapshot `yes_asks` -> YES ask book;
- paid `side=yes`, price `p`, delta -> YES bid level at `p`;
- paid `side=no`, NO-bid price `p`, delta -> equivalent YES ask at `1-p`.

Paid `price_dollars` and `delta_fp` remain exact `Decimal` values. A paid delta that would create negative resting quantity fails closed.

Snapshot quantity comparison permits `1e-9` contracts only to absorb JSON binary-float serialization noise in the free snapshot representation.

## Original 684-snapshot target audit

For `KXBTCD-26JUL1016-T63899.99`:

- snapshots: 684;
- adjacent pairs: 683;
- exact pairs: 682;
- unreconciled pairs: 1;
- displayed sequence-decrease pairs: 1;
- sequence-decrease pair was unreconciled after actual replay;
- excluded gap: 23.362 seconds;
- verified-time fraction across that narrow snapshot span: 67.6771%;
- segment count: 2;
- status: `PASS_SEGMENT_SAFE_REPLAY`.

The important point is causal: the interval is excluded because **book reconstruction failed**, not merely because its displayed sequence decreased.

## Frozen 20-contract stratified reconciliation audit

A deterministic five-contract-per-event sample was frozen before replay-quality inspection, covering minimum / approximately 25th percentile / median / approximately 75th percentile / maximum strikes for each of the four events.

Aggregate result:

- contracts: 20 / 20 completed;
- adjacent snapshot pairs: 8,273;
- exact reconstructed pairs: 8,210;
- failed pairs / hard boundaries: 63;
- exact pair rate: **99.2385%**;
- verified-time rate across sampled snapshot spans: **88.4224%**.

By event:

| Event | Sampled contracts | Exact pair rate | Verified-time rate | Failed pairs | Largest excluded gap | Longest continuous verified segment |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `KXBTCD-26JUL1013` | 5 | 99.379% | 74.607% | 32 | 33.255 min | 47.821 min |
| `KXBTCD-26JUL1014` | 5 | 98.744% | 98.862% | 10 | 0.775 min | 41.196 min |
| `KXBTCD-26JUL1015` | 5 | 98.739% | 80.434% | 11 | 15.379 min | 48.740 min |
| `KXBTCD-26JUL1016` | 5 | 99.309% | 98.024% | 10 | 2.022 min | 54.886 min |

The verified-time aggregation is a source diagnostic across sampled contract snapshot spans. It is not 88.4224% independent event coverage and must not be interpreted as 20 independent experiments.

## Sequence diagnostic finding

The original implementation conservatively treated any displayed snapshot sequence decrease as a hard boundary. The broader audit disproved that rule.

On the deliberately worst inspected contract, `KXBTCD-26JUL1013-T64099.99`:

- snapshots: 4,398;
- adjacent pairs: 4,397;
- exact pairs: 4,376;
- exact pair rate: 99.5224%;
- `cross_source_sequence_decrease`: **585 / 585 exact**;
- `same_source_sequence_decrease`: 0 / 3 exact in that contract.

Thus sequence values are not globally comparable across Predexon `live_early` and `websocket` snapshot sources. Sequence metadata is diagnostic only. The authoritative continuity test is ordered book reconstruction from full snapshot A to full snapshot B.

Same-source sequence decreases remain high-risk diagnostics, but they are not independently elevated to a universal boundary rule. If the actual A->B reconstruction succeeds, the interval remains valid; if it fails, the interval is cut.

## Accepted replay boundary rule

1. Begin from a trusted full-book seed snapshot.
2. Apply exact paid deltas in deterministic `(timestamp, sequence)` order.
3. Search only legal same-millisecond prefix/suffix boundary cuts; never reorder deltas.
4. If the reconstructed book matches the next trusted full snapshot exactly within snapshot-only `1e-9` quantity tolerance, continuity is accepted.
5. If no legal reconstruction matches, the adjacent pair is a hard boundary.
6. Never carry book state across a failed pair.
7. Never forward-fill, interpolate, infer, or repair a failed interval.
8. Displayed sequence decreases are retained as diagnostics, not boundary authority.

## Source qualification conclusion

Predexon paid KXBTCD tick history is accepted as a **usable exploratory historical microstructure source** when replay is restricted to reconciliation-verified segments.

The result supports building and debugging Candidate-E executable-edge / realizability research on the already-purchased 2026-07-10 shard.

It does **not** establish:

- strategy profitability;
- out-of-sample strategy generalization;
- 623 independent observations;
- fill certainty;
- queue position;
- live latency equivalence;
- permission to execute orders.

## Evidence-role firewall

The four 2026-07-10 hourly events are designated **exploratory/development sandbox evidence only**. Strategy variants, feature definitions, latency/fill assumptions, and economic diagnostics may be developed on this shard, but later claims of strategy generalization require fresh hourly events not used for design.

No C1/C2/C3 or protected Candidate-E reserve evidence is opened by this source work.

## Credit-spend constraint

No additional Predexon paid-data purchase is needed for the next development step.

Future Predexon acquisitions must:

- occur only after a fresh-event sampling/evaluation protocol is frozen;
- use only user-available promotional/free credit;
- not knowingly incur a card charge or paid top-up;
- preserve purchased raw data before transformation.

The exact remaining promotional balance is not asserted by this document.

## Next checkpoint

Design the exploratory Candidate-E executable-edge / realizability baseline on this four-event sandbox.

Candidate E remains frozen. The future replay must incorporate, at minimum, executable side price, fee, spread, available depth, latency stress, partial fills, missed fills, segment validity, and model/execution uncertainty before any economic conclusion.

No paper broker, demo order, or real-money execution is authorized.

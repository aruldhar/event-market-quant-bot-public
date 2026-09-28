# KXBTCD Candidate-E Continuous Convergence + Re-entry v1 Predeclaration

## Checkpoint 21N-T

This checkpoint freezes the new strategy version
`kxbtcd_candidate_e_continuous_convergence_reentry_v1`.

It is predeclaration-only. No continuous July 10 signals, fills, cash-out paths, re-entries, settlement labels,
or settlement-dependent P&L are opened here.

Parent 21N-S-B closed at checkpoint `194f514f50cddbe3073667735e5b510e7600fedb` with receipt `f737b3b7705edee7c745c8c4d13a87150ca607bc`. The fixed-anchor
experiment remains permanently `NON_EVALUABLE_NO_VALID_TWO_SIDED_DECISION_STATE`.

## Why the strategy changes

The old strategy evaluated six scheduled timestamps. That is clean for controlled historical testing but
operationally artificial: executable liquidity can appear between scheduled anchors.

The successor therefore asks: **when does an executable Candidate-E opportunity actually appear, can it be
cashed out using the frozen convergence rule, and can one later re-armed opportunity be taken after a full exit?**

This does not rescue or relabel the old strategy.

## Candidate E remains frozen

Champion-Final:
- `kxbtcd_btc_distance_offset_logistic.v1`
- fingerprint `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- beta `0.014939489324405949`

Formula:

`logit(pE) = logit(clip(q_market, 0.001, 0.999)) + 0.014939489324405949 × [10000 × ln(S_t/K)]`

Candidate E itself has no TTC term. Continuous use therefore changes **where the frozen model is evaluated**, not
the model. Non-anchor uses are labeled extrapolation; below 30 minutes is explicitly late-window extrapolation.

## Entry window and timing buckets

New entries are allowed from T−55 inclusive through T−2 inclusive. An open position may still be monitored for
cash-out until event close.

The old anchors are diagnostics only.

Buckets:
- `55_to_45`: `45 < TTC ≤ 55`
- `45_to_30`: `30 < TTC ≤ 45`
- `30_to_20`: `20 < TTC ≤ 30`
- `20_to_10`: `10 < TTC ≤ 20`
- `10_to_5`: `5 < TTC ≤ 10`
- `5_to_2`: `2 ≤ TTC ≤ 5`

## Causal event-driven decision clock

Entry decisions occur only when entry-relevant information can change:
1. T−55;
2. any structural market best YES bid price or quantity changes;
3. any structural market best YES ask price or quantity changes;
4. a new required completed Coinbase 1-minute state becomes available;
5. T−2.

Same-timestamp events collapse to one evaluation. A deep-book change that leaves best entry levels unchanged does
not manufacture a new entry attempt. Deep levels still matter to liquidation.

At each clock timestamp all five structural markets are evaluated.

## Continuous Coinbase BTC state

The historical primary source remains
`coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1`.

At decision time `t`, Candidate E uses the close of the immediately preceding fully completed UTC minute bucket:
`bucket_start = floor_utc_minute(t) − 60 seconds`.

That completed value is causally valid until the next expected minute completes. This is not permission to bridge
a missing bucket. Missing required candles fail closed. Future/incomplete candles, interpolation, nearest sampling,
missing-bucket stale carry, and source substitution are forbidden.

Candidate E has no 5-minute momentum term, so the old 5-minute lookback is not required here.

## Market and signal rule

The five structural roles remain `q10/q30/q50/q70/q90`, derived with the same full-ladder nearest-rank rule.

A market requires a verified, valid, uncrossed two-sided YES book because Candidate E still uses the midpoint.

`q_market = (best YES bid + best YES ask) / 2`

YES purchase price is best YES ask. NO purchase price is `1 − best YES bid`. The relevant best purchase level must
display at least 1.00 contract.

The frozen 0/1/2/3/5-cent net-edge margins remain parallel sensitivity policies. At a decision timestamp, choose
the qualifying signal with greatest edge; ties are ticker ascending, then YES before NO.

## Execution

One-contract IOC buys are simulated at 0/500/1000 ms. Same latency applies to entry and exit in a scenario.

Only one entry IOC may be pending at a time. Decision-clock timestamps that occur between an entry decision and that IOC's arrival are ignored for new entry decisions. A missed IOC does not consume the two-entry cap; after the miss resolves, scanning resumes at the first decision-clock timestamp strictly after the IOC arrival.
A partial fill counts as a filled entry; its remainder is canceled and cannot be topped up.

## Cash-out

The existing entry-time-fair-value convergence rule is retained.

The target is frozen at entry. Candidate E is not dynamically recomputed for exit. Every post-entry reconstructed
book-state change is monitored. The first state where the entire open quantity can be sold, after frozen fees, for
at least the entry-time fair value triggers one IOC exit after scenario latency.

A replay gap, partial exit, or missed exit leaves settlement fallback quantity and forbids re-entry.

## Re-entry

Maximum: **two filled entries per event × threshold × latency scenario**.

A second entry requires:
1. the first position was fully exited;
2. at a strictly later timestamp, the exact market-side signal used for Trade 1 becomes evaluable and is no longer
   qualifying for that threshold (or lacks one-contract decision-level depth);
3. source-unavailable/invalid states do not count as re-arm;
4. after re-arm, a later signal anywhere in the five-role YES/NO universe qualifies.

Trade 2 may be same market, different market, same side, or opposite side. Trade 3 is forbidden.

No overlapping positions, adds, averaging, or side switching while open.

## Trade-1 information

Trade-1 state and path information is logged for later research, but **cannot affect the Trade-2 decision in v1**.

The hypothesis that Trade-1 behavior may help predict whether to re-enter is preserved for future independent
evidence. Four July 10 events may not be used to fit or tune such a feature/model/filter.

## Comparison branches

Three linked branches share the same first realized fill:

- **A: matched first-entry hold** — hold to settlement, no re-entry.
- **B: liquidate once** — use convergence cash-out, no re-entry.
- **C: liquidate + re-enter** — cash out and permit one re-armed second entry.

Planned decomposition:
- B−A = cash-out effect.
- C−B = incremental re-entry effect.
- C−A = total cash-out + re-entry effect.

Final branch P&L requires settlement labels. During the outcome-blind phase we may inspect fills, paths and fully
closed round-trip cash change, but not settlement-dependent economics.

## Evidence status

July 10 remains four exposed exploratory events. This experiment can debug the continuous architecture and show
whether usable continuous paths exist. It cannot establish profitability or generalization.

No timing bucket, threshold, or latency may be selected as a winner from N=4.

## Next

**21N-U — Continuous BTC-State Materialization and Continuous Strategy Simulator Implementation Freeze.**

21N-U must freeze implementation before opening real continuous July 10 strategy paths. It should reuse the
frozen 21N-R lower-level replay, Candidate-E probability, structural selection, book normalization, fee accounting,
and IOC depth walking, but must not use the old anchor-restricted `build_signal_candidates` wrapper.

Settlement outcomes remain closed.

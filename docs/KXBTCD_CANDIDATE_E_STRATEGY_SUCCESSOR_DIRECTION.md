# Candidate-E Strategy Research — Failure Analysis Result and Successor Direction

## Checkpoint

**Checkpoint 21N-E — Failure Analysis Result Freeze and Successor Direction Preselection**

## Frozen diagnostic result

Checkpoint 21N-D completed the predeclared development-only failure analysis.

- analysis fingerprint: `e9b88ded9fe1db1f89e234ad626023c67038bbea84ae35863b817c3858f4a3ef`
- failure-analysis predeclaration: `33fb68841a174d50971d40aefae73ab564f96adcb8aefafcf5e86aa16d21bc8b`
- Strategy-v1 development result closeout: `9837823342eeb7b7c7d44a264b1507cd718310c2dccb83c837f9bb0bc4d1b392`
- primary population: 159 entries from the frozen 3c/displayed-quote policy
- successor selected by the diagnostic: no
- new strategy rule selected by the diagnostic: no
- C1+C2 Strategy-v1 economics accessed: no
- C3 accessed: no
- protected reserve accessed: no
- execution: no

## Main finding

The H2 -> H3 and B3 -> B4 deterioration is primarily a **reliability/calibration failure**, not a transaction-price or fee shift.

H2 -> H3:
- mean purchase price: 0.832857 -> 0.832951
- mean Candidate-E selected-side fair probability: 0.885879 -> 0.888803
- mean quoted net edge: 0.039530 -> 0.042409
- win rate: 0.888889 -> 0.836066
- calibration gap (win rate - mean fair): +0.003010 -> -0.052737
- net P&L: +2.68 -> -0.63

B3 -> B4:
- mean purchase price: 0.838919 -> 0.827805
- mean fair probability: 0.895577 -> 0.884441
- mean quoted edge: 0.043415 -> 0.042978
- win rate: 0.918919 -> 0.780488
- calibration gap: +0.023342 -> -0.103953
- net P&L: +2.47 -> -2.50

Fees were nearly unchanged across H2/H3. B4 actually paid slightly lower average purchase prices than B3, yet performed much worse. The evidence therefore does not support blaming the reversal on higher quote cost.

Losses were not a single-outlier event. H3 had 10 losing trades and B4 had 9. The worst five contributed about 54% and 60% of negative-loss magnitude respectively: concentrated enough to matter, but broad enough that removing one freak trade would not explain the failure.

## Entry model versus strategy refinement

For a binary contract held to settlement:

`E[P&L | X] = p(selected side wins | X) - purchase_price - fee`

Purchase price and fee are observed at entry. The unknown term is the settlement probability/reliability. Therefore a learned expected-P&L model is fundamentally another probability/reliability model plus known costs.

That matters because `kxbtcd_candidate_e_entry_residual_logistic.v1` already tried to learn an entry-state correction to Candidate E's settlement probability and failed its frozen C1+C2 validation gate.

### Recommended first successor family

Keep Candidate E unchanged as the probability engine, but require its apparent edge to survive an explicit **uncertainty/reliability adjustment** before entry.

Conceptually:

1. Candidate E produces `pE`.
2. Kalshi quote + fee determines break-even probability.
3. Apply a predeclared conservative adjustment to Candidate E's incremental confidence/edge.
4. Enter only if the conservative edge still clears the frozen rule; otherwise abstain.

The exact adjustment is **not selected in 21N-E**. It must be frozen later without mining the exposed 21N-D slices for the best threshold/TTC/role/side/price bucket.

### Learned entry/meta-model

A learned entry/meta-model is **deferred, not permanently rejected**. It can return later as a challenger only if it is scientifically distinct from rejected Model-2 and can beat the simpler reliability-adjusted baseline under fresh validation.

## Preselection recommendation

**Advance the deterministic reliability-adjusted entry baseline first. Defer a learned entry/meta-model to a later challenger.**

Reasons:

1. The observed failure mechanism is overconfidence/reliability instability.
2. Quote prices and fees did not explain the regime reversal.
3. Hold-to-settlement expected-return modeling largely reduces to settlement-probability modeling.
4. The prior learned residual probability Model-2 already failed.
5. The simpler baseline is easier to audit, harder to overfit, and gives any later learned model a meaningful benchmark.

This is a research-direction preselection, not authorization to run Strategy-v2.

## Unresolved questions for the next design checkpoint

Before Strategy-v2 may be scored:
- What exact reliability adjustment is allowed?
- Can it be justified independently of exposed H1/H2/H3 economic slices?
- What evidence is development versus validation?
- How much genuinely fresh strategy evidence is required?
- Should confirmation be prospective first or eventually use a predeclared small reserve slice?
- What advancement gate and adverse-price stress must the strategy pass?

No answer may be chosen post hoc from the current failure-analysis slices and then described as validated.

## Safety boundary

No C1+C2 Strategy-v1 economics, C3 strategy economics, protected reserve, paper broker, demo execution, or real execution is authorized by this checkpoint.

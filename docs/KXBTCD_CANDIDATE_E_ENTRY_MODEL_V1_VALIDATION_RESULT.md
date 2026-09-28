# Candidate-E Entry Model v1 — C1+C2 Validation Result

## Status

**REJECTED — frozen C1+C2 validation FAIL.**

Model: `kxbtcd_candidate_e_entry_residual_logistic.v1`

This result is a probability-scoring result only. It is not evidence of trading
profitability or executable edge.

## Frozen provenance

- development freeze: `a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e`
- validation preparation: `25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22`
- original validation implementation:
  `8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`
- post-outcome resume repair:
  `fee1063a637c99749e47d67bbb553a480d3e72037be1cb9015b26b67f2275aed`
- validation evaluation: `15a6557736204ca58039906434f8b7e83bca719f14cd0a3b4c9b9094e42ce033`
- validation receipt: `5e37a7abab6065414be00761ac79e09e853e587ab3ccf153e9f5a74081b11e2a`
- result closeout: `f27dba7fc5fcf9726a3699b8e611646d0d93b77a3dfdb8050048767a97c36ff7`

## C1+C2 validation result

- events: `1000`
- rows: `28894`
- Candidate E event-equal log loss:
  `0.0518981214127418`
- Model-2 event-equal log loss:
  `0.051982434232278454`
- Candidate-E-minus-Model2 log-loss delta:
  `-8.431281953665687e-05`
- Candidate E event-equal Brier:
  `0.015171565220600291`
- Model-2 event-equal Brier:
  `0.01519915292120419`
- Candidate-E-minus-Model2 Brier delta:
  `-2.7587700603898604e-05`
- median event Candidate-E-minus-Model2 log-loss delta:
  `2.3452135462756008e-05`
- block log-loss wins: `1/5`
- newest block `V4` win:
  `False`

## Gate conditions

The frozen five-condition gate produced:

- pooled Model-2 log loss strictly better: **FAIL**
- pooled Model-2 Brier no worse: **FAIL**
- at least 4/5 block log-loss wins: **FAIL**
- newest block log-loss win: **FAIL**
- positive median event log-loss delta: **PASS**

Because all five conditions were required, Model-2 v1 fails validation.

## Chronological block diagnostics

- V0: Candidate E LL `0.034925969749479736`, Model-2 LL `0.034967279677325304`, Candidate-E-minus-Model2 `-4.130992784556753e-05`, Model-2 win `False`
- V1: Candidate E LL `0.07562509474284637`, Model-2 LL `0.07554918858302571`, Candidate-E-minus-Model2 `7.590615982065729e-05`, Model-2 win `True`
- V2: Candidate E LL `0.04948023891648794`, Model-2 LL `0.04979224817499045`, Candidate-E-minus-Model2 `-0.00031200925850251304`, Model-2 win `False`
- V3: Candidate E LL `0.027137402948988604`, Model-2 LL `0.027149201013044254`, Candidate-E-minus-Model2 `-1.1798064055650037e-05`, Model-2 win `False`
- V4: Candidate E LL `0.07232190070590583`, Model-2 LL `0.0724542537130064`, Candidate-E-minus-Model2 `-0.00013235300710057185`, Model-2 win `False`

These block results are descriptive diagnostics of the frozen validation outcome.
They are not authorization to repair or retune Model-2 on C1+C2.

## Consequences

- Model-2 v1 is permanently rejected under this specification.
- C1+C2 are exposed evidence for Model-2 and cannot be reused as untouched
  validation for a repaired/retrained version.
- No post-hoc retune, rescore, feature repair, or gate repair on C1+C2 is allowed.
- C3 remains sealed for Model-2 v1 and must not be opened for this rejected model.
- The protected historical reserve remains untouched.
- Strategy-v1 P&L has not been calculated.
- Execution remains disabled.
- Any successor entry model requires a separate predeclaration and evidence plan.

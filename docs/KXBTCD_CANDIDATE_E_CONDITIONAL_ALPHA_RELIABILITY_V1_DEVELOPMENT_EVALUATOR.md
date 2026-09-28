# KXBTCD Candidate-E Conditional-Alpha Reliability v1 — Development Evaluator Freeze

## Checkpoint

**21N-K — H-development evaluator implementation freeze**

Implementation fingerprint:

`02530cdd8ba58b45cde85c0ba40f681355ce5b14c4a3ad53ee5f1072fff156a8`

Parent predeclaration:

`742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`

Parent J-B preparation:

`a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46`

## Purpose

21N-K freezes the exact code path that may later attach the already-exposed
H1_OOF/H2/H3 settlement labels and execute the predeclared conditional-alpha
development experiment.

No real project outcome is read and no real gamma is fitted in 21N-K itself.

## Frozen sequencing

The future one-time development run proceeds in this order:

1. verify the 21N-K safe-closeout receipt;
2. verify the exact J-B feature/preparation hashes;
3. verify the exact H1_OOF/H2/H3 Candidate-E source hashes;
4. attach outcomes by exact `state_id`;
5. fit every frozen lambda on H1_OOF and score H2;
6. fit every frozen lambda on H1_OOF+H2 and score H3;
7. select lambda by pooled H2+H3 event-equal log loss, exact tie -> larger lambda;
8. apply the complete frozen probability gate;
9. **only if the probability gate passes**, apply the frozen quoted-entry economic gate;
10. **only if both gates pass**, fit the selected lambda once on H1_OOF+H2+H3.

The probability-first sequencing is evidence-minimizing. It does not change any
21N-I acceptance condition. If the candidate already fails its required
probability gate, additional conditional-alpha P&L is unnecessary for the
predeclared advancement decision and remains unopened.

## Probability gate

The implementation preserves all 21N-I requirements: conditional alpha must beat
Kalshi q, Candidate E, and global alpha .50 on pooled event-equal log loss; pooled
Brier must be no worse than all three; H2 and H3 must each beat .50 log loss;
median event-level .50-minus-conditional log-loss improvement must be positive;
all fits/metrics must remain finite and the bounded-alpha invariants must pass.

## Economic gate

If and only if probability passes, economics use selected-lambda rolling-origin
H2+H3 predictions only:

- 1,500 score events;
- five contiguous 300-event chronological blocks;
- frozen first-qualifying-anchor one-contract quote screen;
- base and +1c advancement stress;
- +2c/+3c diagnostic stress;
- minimum 100 total entries and 20 per H2/H3;
- positive base and +1c pooled mean P&L/event;
- at least 4/5 positive base blocks;
- positive newest B4;
- positive H3 base mean.

This is quoted settlement-value research, not fill simulation.

## Evidence firewall

21N-K itself performs no real-data fit or scoring. C1+C2 remain unauthorized.
C3 remains locked. The protected reserve remains sealed. No network, order,
paper/demo, or real-money execution surface is added.

After safe closeout, exactly one H-development run may be performed with the
frozen CLI. Its result must be independently reproduced before any next phase.

No profitability claim is made.

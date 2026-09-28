# KXBTCD Candidate-E Incremental Alpha Entry Score v1 — Implementation

## Status

**IMPLEMENTATION FROZEN — REAL INCREMENTAL-SCORE DIAGNOSTIC NOT RUN**

Implementation fingerprint:

`8c88bb386e0ba13b3ab8761e67a73dd7105637d3667d5fc7394d163259b5471b`

Predeclaration fingerprint:

`bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa`

## Frozen score

For the exact 512 parent Candidate-E ENTER opportunities:

`S_beta = z(edge) + beta*z(logit(alpha))`

with beta in:

`0, 0.25, 0.5, 1, 2`.

The scaler is computed once from the pooled H2+H3 ENTER population using only:

- Candidate-E net quoted edge;
- conditional alpha transformed by logit.

It uses population standard deviations.

Outcome and realized P&L are not inputs to scaling or ranking.

## Selection

For every beta, rank all 512 opportunities by:

1. score descending;
2. event close time ascending;
3. event ticker ascending;
4. market ticker ascending;
5. YES before NO.

Select exactly 128.

No coverage or score-threshold search exists.

## Beta selection

After the later real run, beta is selected by highest pooled H2+H3 +1 cent
realized P&L per selected entry. Exact tie chooses smaller beta.

Beta=0 is the edge-only benchmark and cannot be removed.

## Incremental-alpha gate

Alpha earns a later formal strategy role only if the selected beta:

- is positive;
- beats beta=0 on pooled base and +1c P&L/entry;
- beats beta=0 separately on H2 and H3 base P&L/entry;
- is positive pooled at both base and +1c.

Even a PASS of this exploratory gate is not a strategy PASS or fresh validation.

## Safety lock

The real CLI requires the latest closeout receipt to be Checkpoint 21N-N-C-B.
Therefore this implementation package cannot expose the real incremental-score
P&L before implementation validation and safe push.

C1/C2, C3, protected reserve, network access, and execution remain prohibited.

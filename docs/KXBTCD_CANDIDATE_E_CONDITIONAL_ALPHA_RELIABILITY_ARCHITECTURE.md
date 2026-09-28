# Candidate-E Strategy-v2 Result Freeze and Conditional-Alpha Successor Architecture

## Checkpoint 21N-H

This checkpoint does two things only:

1. freezes the completed Strategy-v2 development result;
2. accepts the **conditional-alpha reliability model** as the next research architecture.

It does **not** fit the new model.

## Strategy-v2 final development result

Evaluation fingerprint:

`97ccad587cbfd32c9a390e91800b52da91f5b53e1a273cbecca39b802ab51e21`

Status:

`FAIL_NO_ALPHA`

Result artifact hashes:

- evaluation JSON: `2f30d56ad109cb77dd9ad2af8974293c101d5ff37a1ed3287a03d0868243829e`
- event P&L scenarios: `995954431856e021bcb26f22d8d0ffdcacce55a10a660e3ea5af176a38dc6587`
- alpha scores: `d970769a5acfd0f337033bde49184e57afa12a833a66d961fa09a859fe763034`
- receipt: `43e193923ad0ec89ace67d4f07645bb973c1853c6190bb1d326f458d4156d2e8`

### Alpha 0.50

- entries: 276
- base total P&L: +$4.75
- base mean/event: +0.0018482490
- +1c total P&L: +$2.02
- +1c mean/event: +0.0007859922
- base H3: +$3.02
- newest B4: positive
- positive chronological blocks: 3/5
- gate: FAIL

The only frozen gate failure was the required >=4/5 positive chronological blocks.

### Alpha 0.75

- entries: 591
- base total P&L: -$0.29
- +1c total P&L: -$6.05
- positive blocks: 2/5
- newest B4: negative
- H3: -$2.43
- gate: FAIL

### Consequence

The simple global reliability-shrinkage family is closed as a development FAIL.
Do not rescue alpha 0.25, search intermediate global alphas, or promote exposed
side/TTC/role diagnostics into validated filters on the same evidence.

Result-closeout fingerprint:

`02b8aab23161419abd1cdf02c79072f070067ed28f16ef186959e6fc5b3f5ee4`

## Accepted successor hypothesis

A single global alpha is too crude. The next candidate asks whether the amount
of trust placed in Candidate E should depend on the contemporaneous state.

For state i:

`alpha_i = sigmoid(gamma_0 + gamma^T X_i)`

Then:

`p_adj_i = q_i + alpha_i * (pE_i - q_i)`

where:

- `q_i` is the contemporaneous Kalshi market midpoint;
- `pE_i` is frozen Candidate E;
- `0 < alpha_i < 1`.

Plain-language interpretation:

- alpha near 1 -> trust most of Candidate E's disagreement with Kalshi;
- alpha near 0 -> trust little of the disagreement and stay near the market;
- different states may receive different alpha values.

Because alpha is constrained to (0,1), the adjusted probability stays between
Kalshi and Candidate E. The model cannot create a probability more extreme than
both endpoints.

## Why this is distinct from failed Model2

The rejected Model2 learned an unrestricted residual correction:

`logit(p2) = logit(pE) + g(X)`

The conditional-alpha candidate is more constrained. It learns only **how much
of Candidate E's disagreement with Kalshi to trust**. It does not freely rewrite
Candidate E.

The earlier Model2 C1+C2 validation failed and must not be resurrected or
rescored. Conditional alpha is a separately versioned successor hypothesis.

## Target separation

The new model should not directly regress on realized trade P&L.

The intended separation is:

`state -> reliability alpha -> adjusted probability -> quote/fee economics -> decision`

Settlement outcomes may later supervise the reliability model under a separately
frozen objective. Quoted purchase price and fees remain downstream economics.

This keeps probability/reliability estimation distinct from trade accounting.

## Evidence firewall

### Fully exposed

H1_OOF, H2, and H3 have now influenced Candidate-E research, Model2 development,
Strategy-v1 economics/failure analysis, and Strategy-v2 selection/economics.
They are development/exploratory evidence only.

### C1+C2

C1+C2 outcomes were opened for prior Model2 research. They are **not globally
fresh evidence**. Conditional-alpha use of C1+C2 is not authorized here.

### C3

Keep C3 locked against conditional-alpha development. This does not claim C3 is
globally untouched by all prior Candidate-E research; it means C3 must not
influence this successor's features, objective, regularization, or tuning before
its role is explicitly frozen.

### Protected reserve

The protected historical reserve remains sealed.

## Feature directions allowed for the next design

The next checkpoint may consider causal reliability features such as Candidate-E
versus market disagreement, spread, causal BTC movement, recent Kalshi quote
movement/range, recent public market activity, time-to-close, and structural role.

This is a design space, not the final feature vector.

## Explicit post-hoc exclusions

Do not convert the exposed Strategy-v2 diagnostics directly into rules such as
NO-only, avoid T-55, avoid B1/B2, a B3/B4-specific alpha, or an intermediate
global alpha chosen after seeing economics.

## Unresolved before any fit

Checkpoint 21N-I must freeze exact features/transforms, alpha parameterization,
training loss/event weighting, regularization/tuning, chronological development
procedure, benchmarks, downstream entry rule, advancement gates, and later
C1+C2/C3 evidence roles.

No conditional-alpha model may be fit before those are frozen and safely closed.

Architecture fingerprint:

`bb7ebb7b12a9b817465e9e522d65b2f5a129f9e5aaa12a1c8ac6e5fd666a6742`

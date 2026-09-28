# KXBTCD Candidate-C One-Time Terminal Locked-Test Evaluation

Status: **Checkpoint 17 Stage A complete — terminal procedure frozen; locked test remains outcome-sealed**

## Frozen identities

```text
full-development preprocessing fingerprint = d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3
final Candidate-C model fingerprint = 13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f
terminal evaluation procedure fingerprint = bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa
Stage-B implementation = byte-for-byte SHA-256-bound by the procedure freeze
```

## Frozen terminal scope

```text
locked-test events = 64
locked-test pre-outcome rows = 1,014
exact market request allow-list = 304
partition = locked_test only
```

The request allow-list is derived from event/market identifiers only. Stage A does not inspect outcomes and does not use locked-test feature density to redesign the candidate.

## Frozen inference

Raw benchmark:

`p_raw = q_market`

Candidate C:

load only `configs/kxbtcd_candidate_c_final_model.json` and apply its frozen inference function to the pre-existing `q_market` and `spread` values.

No fit, refit, lambda search, feature change, preprocessing change, optimizer change, or recalibration is permitted.

## Frozen metrics

For each model:

1. compute row log loss and Brier on the same 1,014 rows;
2. average row loss within each event;
3. average the 64 event means.

Primary metric: event-weighted log loss.

Secondary metric: event-weighted Brier.

## Frozen primary rule

```text
Candidate-C locked-test event-weighted log loss
<
raw-midpoint locked-test event-weighted log loss
```

An exact tie fails. Brier cannot override the primary rule.

## Exposure policy

Before Stage B creates its first terminal outcome request, it writes a durable attempt receipt that conservatively marks the complete 64-event terminal set permanently exposed.

A fresh second terminal attempt is prohibited. If the one logical attempt is interrupted, only the already frozen recovery/resume path may continue it; already exposed market outcomes are recovered from raw archives and are not re-requested.

After exposure, these 64 events may not be used for Candidate-C redesign and may never again be described as an untouched test.

## Git precondition

Stage B is fail-closed unless:

- branch is `main`;
- the entire worktree/index is clean;
- the operator has just fetched `origin`; and
- local `HEAD` exactly equals `origin/main`.

The network-capable HTTP client is instantiated only after this preflight and all frozen artifact/procedure validations pass.

## Stage-A safety state

```text
procedure derivation outcomes used = no
locked-test outcomes opened = 0
network requests = 0
model fit/tune/recalibration = no
paper execution = no
demo execution = no
real-money execution = no
orders placed = 0
```

## Required next action

Close and push the Stage-A procedure-freeze changes with the safe checkpoint closeout workflow. Verify the resulting receipt, fresh remote synchronization, and clean worktree. Only then may Stage B run `collect_kxbtcd_candidate_c_locked_test.py`.

<!-- CHECKPOINT17_TRANSPORT_AMENDMENT_20260815 -->
## Interrupted Stage-B attempt and transport amendment

The first terminal attempt was correctly fail-closed but exposed part of the
locked block. It persisted 9 of 304 market labels before
`/historical/markets/KXBTCD-26AUG0202-T55499.99` returned HTTP 404.

The root cause was endpoint-tier routing. Kalshi's observed market-settlement
cutoff was `2026-06-16T00:00:00Z`; the frozen request set spans both older
historical markets and newer recent-settled markets. The original implementation
used only `/historical/markets/{ticker}`.

No outcome values were used to choose the repair. The accepted amendment keeps
the original terminal fingerprint `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`, model, preprocessing,
request membership, metrics, and gate fixed. Separate transport amendment
fingerprint: `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`.

Resume behavior is mechanical: recover prior successful labels from raw
archives, skip them, query each missing ticker at `/markets/{ticker}`, and
only if that returns HTTP 404 retry the same ticker at
`/historical/markets/{ticker}`. Exact ticker/event identity and finalized
yes/no validation remain unchanged.

The 64-event terminal set is permanently exposed and may not be reused for
redesign or any future untouched-test claim.

<!-- CHECKPOINT17_TERMINAL_RESULT_20260815 -->
## Checkpoint 17 terminal locked-test result — 2026-08-15

Checkpoint 17 is complete. The frozen Candidate-C terminal evaluation **FAILED**
the predeclared primary gate.

- Completed terminal run: `collect_kxbtcd_candidate_c_locked_test_20260815T225546640797Z_54081035`
- Terminal evaluation fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`
- Transport amendment fingerprint: `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`
- Final Candidate-C model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`
- Locked test: 64 events / 1014 rows / 304 market labels
- Raw midpoint event-weighted log loss: `0.052191564366640519`
- Candidate-C event-weighted log loss: `0.068502780828836138`
- Raw-minus-Candidate-C log-loss delta: `-0.016311216462195618`
- Raw midpoint event-weighted Brier: `0.014139546080841911`
- Candidate-C event-weighted Brier: `0.014602932515903819`
- Primary gate: **FAIL**
- Tie rule: fail
- Locked-test set permanently exposed: yes
- Model refit / retune / recalibration: no / no / no
- Execution enabled: no
- Orders placed: 0

The first terminal attempt was interrupted after 9 labels because the original
collector used the historical-market endpoint for a live-tier August market.
The separately frozen transport-only amendment recovered those 9 labels and
collected the remaining 295 labels without changing model, preprocessing,
features, lambda, optimizer, scoring rows, metric definitions, primary gate,
tie rule, or test membership. The completed resume used 295
live-market requests and 103 historical
fallback requests.

**Interpretation boundary:** Candidate C does not advance under the frozen
terminal criterion. This result does not establish that no predictive signal
exists, and it does not establish profitability or execution suitability.
The 64-event terminal set is now permanently exposed and must not be used to
retune Candidate C, design a successor model, or support another untouched-test
claim.

### Final disposition

Candidate C is closed as a failed terminal candidate. The raw midpoint remains
the stronger probabilistic benchmark on this frozen terminal sample. This is a
model-validation conclusion only, not an execution or profitability claim.

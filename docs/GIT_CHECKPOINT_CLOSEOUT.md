# Safe Git Checkpoint Closeout

## Purpose

`scripts/close_checkpoint.ps1` is the Windows entry point for a fail-closed Git checkpoint-closeout workflow. It launches `scripts/checkpoint_closeout.py` with the repository-local `.venv` Python.

The helper exists to remove repetitive Git verification while preserving explicit human control at the two points that materially publish project history:

1. the checkpoint commit message;
2. the final push approval.

It is repository tooling only. It does not collect market data, authenticate to Kalshi, place orders, or change the trading authorization boundary.

## Normal command

From the repository root:

```powershell
.\scripts\close_checkpoint.ps1
```

The helper discovers all non-ignored changes and displays the exact set. You must approve that set before validation continues.

For a strict caller-supplied set:

```powershell
.\scripts\close_checkpoint.ps1 -Paths @(
    "src/example.py",
    "tests/test_example.py",
    "docs/PROJECT_STATE.md"
)
```

When `-Paths` is supplied, the set must equal the entire changed-file set exactly. A forgotten or unexpected changed file blocks the closeout.

## Automated sequence

A normal run performs the following sequence:

1. Require the repository-local `.venv` Python.
2. Verify repository name, branch, configured upstream, and GitHub repository identity.
3. Refuse merge, rebase, cherry-pick, revert, bisect, conflicts, or pre-existing staged changes.
4. Fetch `origin` and require local `main` and `origin/main` to be exactly synchronized.
5. Discover tracked modifications/deletions/renames plus non-ignored untracked files.
6. Refuse changes to the helper's own safety-critical files.
7. Refuse a manually modified generated closeout receipt.
8. Require exact changed-file approval.
9. Reject blocked paths such as `.env`, private-key files, credential directories, raw runtime data, logs, reports, databases, and model artifacts.
10. Run `git diff --check`.
11. Run each required configured validator.
12. Run the full configured pytest suite.
13. Stage only the approved paths with `git add -A -- <exact paths>`.
14. Require the staged path set to equal the approved path set exactly.
15. Require no remaining unstaged or untracked changes.
16. Run `git diff --cached --check`.
17. Scan added staged lines for high-confidence private-key and common token patterns.
18. Show exact staged names and a diff-stat summary.
19. Ask for the checkpoint commit message. Blank input cancels and safely unstages the helper-owned index changes.
20. Create the checkpoint commit and verify its parent, clean index, and clean worktree.
21. Generate `docs/LAST_CHECKPOINT_CLOSEOUT.json` with the exact checkpoint SHA, committed paths, validation evidence, and safety-check results.
22. Create a deterministic documentation-only receipt commit whose parent is the checkpoint commit.
23. Record pending push state inside `.git/` so an interrupted/declined push can be resumed only for the exact helper-created commit pair.
24. Ask once whether to push both commits.
25. Push without force, fetch again, verify local/remote SHA equality, require a clean worktree, and clear pending state.

## Why there are two commits

A Git commit cannot contain its own final SHA as ordinary file content without creating a self-reference problem.

The helper therefore creates:

1. the substantive checkpoint commit;
2. a generated receipt commit containing the exact SHA of commit 1.

The receipt commit does not attempt to record its own SHA. Future handoff documents can rely on `docs/LAST_CHECKPOINT_CLOSEOUT.json` for exact closeout evidence instead of requiring another manual documentation-only hash-update cycle.

## Resume a declined or failed push

If both local commits were created but the push was declined or failed because of the network:

```powershell
.\scripts\close_checkpoint.ps1 -PushExisting
```

This mode is intentionally narrow. It requires:

- a completely clean working tree and index;
- helper-created pending state inside `.git/`;
- local `main` exactly two commits ahead and zero behind `origin/main`;
- `HEAD` equal to the recorded receipt commit;
- `HEAD^` equal to the recorded checkpoint commit;
- the receipt commit to modify only `docs/LAST_CHECKPOINT_CLOSEOUT.json`;
- the receipt content to reference the recorded checkpoint commit.

It will not push an arbitrary local commit.

## Safety-critical self-modification rule

The helper refuses to certify changes to:

```text
scripts/checkpoint_closeout.py
scripts/close_checkpoint.ps1
configs/checkpoint_closeout.json
tests/test_checkpoint_closeout.py
```

A modified verifier should not be allowed to declare its own modified safety rules trustworthy.

Therefore, this initial tooling checkpoint and any later changes to these four files must use the manual selective-staging workflow. Once those changes are committed and pushed, the unchanged committed helper may again close normal project checkpoints.

The runtime policy is loaded from the committed `HEAD:configs/checkpoint_closeout.json`, not from an uncommitted working-copy version.

## Explicitly prohibited behavior

The helper contains no workflow for:

- `git add .`;
- force push;
- hard reset;
- `git clean`;
- destructive checkout of the working tree;
- automatic conflict resolution;
- automatic branch switching;
- bypassing failed validators or tests;
- staging ignored secret/runtime artifacts;
- silently pushing without approval.

If a check cannot establish a safe state, the helper exits without pushing.

## Current configured project checks

`configs/checkpoint_closeout.json` currently requires:

- branch: `main`;
- upstream: `origin/main`;
- repository identity: `aruldhar/event-market-quant-bot`;
- required source-registry validation;
- full `pytest -q` regression suite;
- generated receipt: `docs/LAST_CHECKPOINT_CLOSEOUT.json`.

Additional required validators should be added only through a separately reviewed helper-policy change.

## Failure modes

### Validation or tests fail

No checkpoint commit is created.

### Staging verification fails

The helper attempts to unstage only the paths it staged. Working-tree content is not deleted or reset.

### Commit hook changes the working tree

The checkpoint commit may exist locally, but the helper refuses to create/push the receipt until the state is inspected.

### Push is declined

Both commits remain local. Use `-PushExisting` later.

### Push fails

The commits remain local and the pending-state file remains inside `.git/`. After the network/remote issue is resolved, use `-PushExisting`.

### Remote changed before closeout

The helper fails before staging. Resolve the branch relationship manually; it never rebases, merges, or force-pushes automatically.

## Testing boundary

The Python engine is covered by pytest tests using temporary Git repositories for change discovery, renames, staging/unstaging, blocked paths, secret scanning, operation markers, ahead/behind state, pending state, committed-policy loading, and receipt construction.

The PowerShell wrapper is intentionally thin. Canonical acceptance still requires running the wrapper on the user's Windows Python 3.11 repository.

<!-- CLOSEOUT_UTF8_MAINTENANCE_20260904 -->
## Windows Git-output encoding

Git textual output consumed by the Python closeout engine is decoded explicitly
as UTF-8.

This boundary is intentional. A Windows closeout on 2026-09-04 encountered a
Git staged diff containing UTF-8 byte `0x9d`; Python's inherited `cp1252`
decoder failed before the secret scan could inspect the decoded diff.

The accepted repair keeps generic validator/test subprocess behavior unchanged
and applies `encoding="utf-8"` only through the helper's Git wrapper.

Regression coverage includes both:
- a unit test proving the Git wrapper requests UTF-8; and
- a real Windows temporary-repository Git-diff test executed with
  `PYTHONUTF8=0`.

The environment variable `PYTHONUTF8=1` is therefore not a required closeout
precondition.

#!/usr/bin/env python3
"""Fail-closed Git checkpoint closeout helper for Event-Market Quant Bot.

The helper automates deterministic verification, testing, selective staging,
commit creation, push verification, and clean-worktree checks. It intentionally
retains human control over the commit message and final push approval.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Iterable, Sequence


class CloseoutError(RuntimeError):
    """Raised when a fail-closed safety check blocks the closeout."""


@dataclass(frozen=True)
class RepoPolicy:
    name: str
    remote: str
    branch: str
    expected_remote_repository: str
    validators: tuple[tuple[str, str, bool], ...]
    test_args: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    blocked_exceptions: tuple[str, ...]
    receipt_path: str
    receipt_schema: str
    receipt_commit_message_prefix: str


@dataclass(frozen=True)
class ChangeSet:
    paths: tuple[str, ...]
    display_rows: tuple[str, ...]


HIGH_CONFIDENCE_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key material",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "GitHub token",
        re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "AWS access-key ID",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
    (
        "OpenAI-style secret key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
)

# A modified closeout helper cannot safely certify its own behavior. Changes to
# these files require the same manual review/staging process used to bootstrap
# this tooling checkpoint.
PROTECTED_TOOLING_PATHS: frozenset[str] = frozenset(
    {
        "scripts/checkpoint_closeout.py",
        "scripts/close_checkpoint.ps1",
        "configs/checkpoint_closeout.json",
        "tests/test_checkpoint_closeout.py",
    }
)



def run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = True,
    encoding: str | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        encoding=encoding,
        capture_output=capture,
        check=False,
    )
    if check and completed.returncode != 0:
        command = " ".join(args)
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise CloseoutError(f"Command failed: {command}\n{detail}")
    return completed


def git(
    repo: Path,
    *args: str,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(
        ("git", *args),
        cwd=repo,
        check=check,
        capture=capture,
        encoding="utf-8",
    )


def normalize_repo_path(path: str) -> str:
    value = path.replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    value = str(PurePosixPath(value))
    if value in ("", "."):
        raise CloseoutError("Repository path may not be empty.")
    if value.startswith("../") or value == ".." or PurePosixPath(value).is_absolute():
        raise CloseoutError(f"Path escapes repository root: {path}")
    return value


def normalize_remote_repository(url: str) -> str:
    """Return owner/repository from common GitHub HTTPS/SSH URL forms."""
    value = url.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]

    if value.startswith("git@github.com:"):
        value = value[len("git@github.com:") :]
    elif value.startswith("ssh://git@github.com/"):
        value = value[len("ssh://git@github.com/") :]
    elif value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    elif value.startswith("http://github.com/"):
        value = value[len("http://github.com/") :]
    else:
        raise CloseoutError(
            "Origin must be a recognizable github.com HTTPS or SSH remote."
        )
    return value.strip("/")


def load_policy(repo: Path) -> RepoPolicy:
    policy_path = "configs/checkpoint_closeout.json"
    completed = git(
        repo,
        "show",
        f"HEAD:{policy_path}",
        check=False,
    )
    if completed.returncode != 0:
        raise CloseoutError(
            "Committed closeout policy is missing. Bootstrap or helper-maintenance "
            "changes must be closed manually before this helper can certify them."
        )
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CloseoutError(f"Committed closeout policy is invalid JSON: {exc}") from exc

    if data.get("schema") != "checkpoint_closeout_config.v1":
        raise CloseoutError("Unsupported checkpoint closeout policy schema.")

    repository = data.get("repository")
    tests = data.get("tests")
    receipt = data.get("receipt")
    if (
        not isinstance(repository, dict)
        or not isinstance(tests, dict)
        or not isinstance(receipt, dict)
    ):
        raise CloseoutError(
            "Closeout policy is missing repository/tests/receipt objects."
        )

    validators: list[tuple[str, str, bool]] = []
    for item in data.get("validators", []):
        if not isinstance(item, dict):
            raise CloseoutError("Validator policy entries must be objects.")
        validators.append(
            (
                str(item.get("name") or "").strip(),
                normalize_repo_path(str(item.get("script") or "")),
                bool(item.get("required", True)),
            )
        )

    return RepoPolicy(
        name=str(repository.get("name") or "").strip(),
        remote=str(repository.get("remote") or "").strip(),
        branch=str(repository.get("branch") or "").strip(),
        expected_remote_repository=str(
            repository.get("expected_remote_repository") or ""
        ).strip(),
        validators=tuple(validators),
        test_args=tuple(str(x) for x in tests.get("args", [])),
        blocked_paths=tuple(str(x) for x in data.get("blocked_paths", [])),
        blocked_exceptions=tuple(
            str(x) for x in data.get("allowed_blocked_path_exceptions", [])
        ),
        receipt_path=normalize_repo_path(str(receipt.get("path") or "")),
        receipt_schema=str(receipt.get("schema") or "").strip(),
        receipt_commit_message_prefix=str(
            receipt.get("commit_message_prefix") or ""
        ).strip(),
    )


def require_local_venv(repo: Path) -> None:
    expected = repo / ".venv"
    executable = Path(sys.executable).resolve()
    try:
        executable.relative_to(expected.resolve())
    except ValueError as exc:
        raise CloseoutError(
            "Closeout must run with the repository .venv Python. "
            "Use .\\scripts\\close_checkpoint.ps1."
        ) from exc


def get_repo_root(start: Path) -> Path:
    completed = run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=start,
        check=True,
        capture=True,
    )
    return Path(completed.stdout.strip()).resolve()


def operation_markers(repo: Path) -> list[str]:
    git_dir_text = git(repo, "rev-parse", "--git-dir").stdout.strip()
    git_dir = Path(git_dir_text)
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()

    markers = {
        "MERGE_HEAD": git_dir / "MERGE_HEAD",
        "CHERRY_PICK_HEAD": git_dir / "CHERRY_PICK_HEAD",
        "REVERT_HEAD": git_dir / "REVERT_HEAD",
        "rebase-merge": git_dir / "rebase-merge",
        "rebase-apply": git_dir / "rebase-apply",
        "BISECT_LOG": git_dir / "BISECT_LOG",
    }
    return [name for name, path in markers.items() if path.exists()]


def verify_repo_identity(repo: Path, policy: RepoPolicy) -> None:
    if repo.name != policy.name:
        raise CloseoutError(
            f"Wrong repository directory: expected {policy.name!r}, got {repo.name!r}."
        )

    branch = git(repo, "branch", "--show-current").stdout.strip()
    if branch != policy.branch:
        raise CloseoutError(
            f"Wrong branch: expected {policy.branch!r}, got {branch or '<detached>'!r}."
        )

    upstream = git(
        repo,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )
    expected_upstream = f"{policy.remote}/{policy.branch}"
    if upstream.returncode != 0 or upstream.stdout.strip() != expected_upstream:
        got = upstream.stdout.strip() or "<none>"
        raise CloseoutError(
            f"Wrong upstream: expected {expected_upstream!r}, got {got!r}."
        )

    remote_url = git(repo, "remote", "get-url", policy.remote).stdout.strip()
    actual_repository = normalize_remote_repository(remote_url)
    if actual_repository.lower() != policy.expected_remote_repository.lower():
        raise CloseoutError(
            "Wrong remote repository: expected "
            f"{policy.expected_remote_repository!r}, got {actual_repository!r}."
        )

    markers = operation_markers(repo)
    if markers:
        raise CloseoutError(
            "Git operation in progress; resolve it manually first: "
            + ", ".join(markers)
        )

    unmerged = git(repo, "ls-files", "-u").stdout.strip()
    if unmerged:
        raise CloseoutError("Unmerged/conflicted paths exist; resolve them manually.")

    if git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
        raise CloseoutError(
            "Pre-existing staged changes detected. The helper will not mix commits."
        )


def fetch_and_sync_state(repo: Path, policy: RepoPolicy) -> tuple[int, int]:
    print(f"Fetching {policy.remote}/{policy.branch}...")
    git(repo, "fetch", "--prune", "--quiet", policy.remote)

    target = f"{policy.remote}/{policy.branch}"
    counts = git(
        repo,
        "rev-list",
        "--left-right",
        "--count",
        f"HEAD...{target}",
    ).stdout.strip().split()
    if len(counts) != 2:
        raise CloseoutError("Could not determine local/remote divergence.")
    ahead, behind = int(counts[0]), int(counts[1])
    return ahead, behind


def require_synced_before_closeout(repo: Path, policy: RepoPolicy) -> None:
    ahead, behind = fetch_and_sync_state(repo, policy)
    if ahead or behind:
        raise CloseoutError(
            "Local and remote must be synchronized before creating a new checkpoint "
            f"(ahead={ahead}, behind={behind})."
        )


def _parse_name_status_z(raw: str) -> tuple[list[str], list[str]]:
    tokens = raw.split("\0")
    if tokens and tokens[-1] == "":
        tokens.pop()

    paths: list[str] = []
    rows: list[str] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        i += 1
        if not status:
            continue
        code = status[0]
        if code in {"R", "C"}:
            if i + 1 >= len(tokens):
                raise CloseoutError("Unexpected Git rename/copy status output.")
            old = normalize_repo_path(tokens[i])
            new = normalize_repo_path(tokens[i + 1])
            i += 2
            paths.extend((old, new))
            rows.append(f"{status}\t{old} -> {new}")
        else:
            if i >= len(tokens):
                raise CloseoutError("Unexpected Git name-status output.")
            path = normalize_repo_path(tokens[i])
            i += 1
            paths.append(path)
            rows.append(f"{status}\t{path}")
    return paths, rows


def discover_changes(repo: Path) -> ChangeSet:
    tracked_raw = git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
    ).stdout
    tracked_paths, rows = _parse_name_status_z(tracked_raw)

    untracked_raw = git(
        repo,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    ).stdout
    untracked = [
        normalize_repo_path(item)
        for item in untracked_raw.split("\0")
        if item
    ]
    rows.extend(f"??\t{path}" for path in untracked)

    ordered: list[str] = []
    seen: set[str] = set()
    for path in (*tracked_paths, *untracked):
        if path not in seen:
            seen.add(path)
            ordered.append(path)

    return ChangeSet(paths=tuple(ordered), display_rows=tuple(rows))


def path_matches(path: str, pattern: str) -> bool:
    normalized = normalize_repo_path(path)
    pattern = pattern.replace("\\", "/")
    return fnmatch.fnmatch(normalized, pattern)


def validate_path_safety(paths: Iterable[str], policy: RepoPolicy) -> None:
    exceptions = tuple(policy.blocked_exceptions)
    for original in paths:
        path = normalize_repo_path(original)
        if any(path_matches(path, exc) for exc in exceptions):
            continue
        if any(path_matches(path, pattern) for pattern in policy.blocked_paths):
            raise CloseoutError(
                f"Blocked path cannot enter a checkpoint commit: {path}"
            )



def reject_tooling_self_modification(changes: ChangeSet) -> None:
    touched = sorted(set(changes.paths) & PROTECTED_TOOLING_PATHS)
    if touched:
        raise CloseoutError(
            "The closeout helper will not certify modifications to its own "
            "safety-critical tooling. Review and close these changes manually:\n  "
            + "\n  ".join(touched)
        )

def select_paths(
    changes: ChangeSet,
    requested: Sequence[str] | None,
) -> tuple[str, ...]:
    if not changes.paths:
        raise CloseoutError("No changed files found.")

    changed = set(changes.paths)
    if requested:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in requested:
            path = normalize_repo_path(item)
            if path not in seen:
                seen.add(path)
                normalized.append(path)

        requested_set = set(normalized)
        missing = sorted(requested_set - changed)
        unexpected = sorted(changed - requested_set)
        problems: list[str] = []
        if missing:
            problems.append(
                "Requested paths are not currently changed: " + ", ".join(missing)
            )
        if unexpected:
            problems.append(
                "Unexpected changed paths were not approved: " + ", ".join(unexpected)
            )
        if problems:
            raise CloseoutError("\n".join(problems))
        return tuple(normalized)

    print("\nChanged files detected:")
    for row in changes.display_rows:
        print(f"  {row}")
    answer = input("\nUse exactly this changed-file set? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise CloseoutError("Changed-file set was not approved.")
    return changes.paths


def _emit_completed_output(completed: subprocess.CompletedProcess[str]) -> str:
    chunks: list[str] = []
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
        chunks.append(completed.stdout)
    if completed.stderr:
        print(
            completed.stderr,
            end="" if completed.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
        chunks.append(completed.stderr)
    return "".join(chunks).strip()


def run_pre_stage_checks(
    repo: Path,
    policy: RepoPolicy,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []

    print("\nChecking unstaged diff whitespace...")
    diff_check = git(repo, "diff", "--check", check=False)
    if diff_check.returncode != 0:
        detail = (diff_check.stdout or diff_check.stderr).strip()
        raise CloseoutError("git diff --check failed:\n" + detail)

    for name, script, required in policy.validators:
        path = repo / script
        if not path.exists():
            if required:
                raise CloseoutError(
                    f"Required validator is missing: {name} ({script})"
                )
            print(f"Skipping optional validator {name}: {script} not present")
            continue
        print(f"\nRunning validator: {name}")
        completed = run(
            (sys.executable, str(path)),
            cwd=repo,
            check=False,
            capture=True,
        )
        output = _emit_completed_output(completed)
        evidence.append(
            {
                "kind": "validator",
                "name": name,
                "command": [script],
                "returncode": completed.returncode,
                "output": output,
            }
        )
        if completed.returncode != 0:
            raise CloseoutError(f"Validator failed: {name}")

    if not policy.test_args:
        raise CloseoutError("No test command configured.")
    print("\nRunning full test suite...")
    completed = run(
        (sys.executable, *policy.test_args),
        cwd=repo,
        check=False,
        capture=True,
    )
    output = _emit_completed_output(completed)
    evidence.append(
        {
            "kind": "tests",
            "name": "full pytest suite",
            "command": list(policy.test_args),
            "returncode": completed.returncode,
            "output": output,
        }
    )
    if completed.returncode != 0:
        raise CloseoutError("Full test suite failed.")

    return evidence


def stage_paths(repo: Path, paths: Sequence[str]) -> None:
    git(repo, "add", "-A", "--", *paths)


def unstage_paths(repo: Path, paths: Sequence[str]) -> None:
    if not paths:
        return
    git(repo, "reset", "--quiet", "HEAD", "--", *paths, check=False)


def staged_paths(repo: Path) -> set[str]:
    raw = git(
        repo,
        "diff",
        "--cached",
        "--name-status",
        "-z",
        "--find-renames",
    ).stdout
    paths, _ = _parse_name_status_z(raw)
    return set(paths)


def verify_staged_set(
    repo: Path,
    approved_paths: Sequence[str],
    policy: RepoPolicy,
) -> None:
    approved = set(approved_paths)
    actual = staged_paths(repo)
    if actual != approved:
        missing = sorted(approved - actual)
        extra = sorted(actual - approved)
        details: list[str] = []
        if missing:
            details.append("not staged: " + ", ".join(missing))
        if extra:
            details.append("unexpected staged: " + ", ".join(extra))
        raise CloseoutError("Staged path set mismatch: " + "; ".join(details))

    validate_path_safety(actual, policy)

    remaining = discover_changes(repo)
    if remaining.paths:
        # After staging, git diff sees only unstaged tracked changes and ls-files sees
        # untracked files. Any result means something escaped the approved staging set.
        raise CloseoutError(
            "Unstaged/untracked changes remain after staging: "
            + ", ".join(remaining.paths)
        )

    diff_check = git(repo, "diff", "--cached", "--check", check=False)
    if diff_check.returncode != 0:
        detail = (diff_check.stdout or diff_check.stderr).strip()
        raise CloseoutError("git diff --cached --check failed:\n" + detail)


def scan_staged_additions_for_secrets(repo: Path) -> None:
    diff = git(
        repo,
        "diff",
        "--cached",
        "--no-ext-diff",
        "--unified=0",
        "--no-color",
    ).stdout
    findings: list[str] = []
    current_file = "<unknown>"
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        for label, pattern in HIGH_CONFIDENCE_SECRET_PATTERNS:
            if pattern.search(added):
                findings.append(f"{current_file}: possible {label}")
    if findings:
        raise CloseoutError(
            "High-confidence credential/secret pattern found in staged additions:\n  "
            + "\n  ".join(sorted(set(findings)))
        )


def show_staged_summary(repo: Path) -> None:
    print("\nExact staged file set:")
    names = git(repo, "diff", "--cached", "--name-status").stdout.strip()
    print(names or "  <none>")

    print("\nStaged diff summary:")
    stat = git(repo, "diff", "--cached", "--stat").stdout.strip()
    print(stat or "  <none>")


def prompt_commit_message() -> str:
    message = input("\nCommit message (blank cancels safely): ").strip()
    if not message:
        raise CloseoutError("Commit cancelled: no commit message supplied.")
    if "\n" in message or "\r" in message:
        raise CloseoutError("Commit message must be a single line.")
    return message


def create_commit(repo: Path, message: str, baseline_head: str) -> str:
    print("\nCreating commit...")
    run(("git", "commit", "-m", message), cwd=repo, check=True, capture=False)
    new_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    parent = git(repo, "rev-parse", "HEAD^").stdout.strip()
    if parent != baseline_head:
        raise CloseoutError(
            "Created commit parent does not match verified baseline; refusing to push."
        )

    if git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
        raise CloseoutError("Index is still staged after commit; refusing to push.")

    status = git(repo, "status", "--porcelain").stdout.strip()
    if status:
        raise CloseoutError(
            "Working tree changed during commit (possibly by a hook); refusing to push."
        )
    return new_head



def build_closeout_receipt(
    *,
    policy: RepoPolicy,
    baseline_head: str,
    checkpoint_commit: str,
    checkpoint_message: str,
    committed_paths: Sequence[str],
    validation_evidence: Sequence[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": policy.receipt_schema,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repository": policy.expected_remote_repository,
        "branch": policy.branch,
        "remote": policy.remote,
        "baseline_commit": baseline_head,
        "checkpoint_commit": checkpoint_commit,
        "checkpoint_message": checkpoint_message,
        "committed_paths": list(committed_paths),
        "validation": list(validation_evidence),
        "safety": {
            "preexisting_staged_changes": False,
            "remote_synchronized_before_commit": True,
            "blocked_path_check": "PASS",
            "staged_path_exact_match": "PASS",
            "staged_diff_check": "PASS",
            "high_confidence_secret_scan": "PASS",
            "worktree_clean_after_checkpoint_commit": True,
        },
        "note": (
            "This receipt records the checkpoint commit. The documentation-only "
            "receipt commit containing this file is intentionally not self-referenced."
        ),
    }


def write_receipt_commit(
    repo: Path,
    policy: RepoPolicy,
    receipt: dict[str, object],
    checkpoint_commit: str,
) -> str:
    receipt_path = repo / policy.receipt_path
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    validate_path_safety((policy.receipt_path,), policy)
    git(repo, "add", "-A", "--", policy.receipt_path)

    actual = staged_paths(repo)
    if actual != {policy.receipt_path}:
        unstage_paths(repo, (policy.receipt_path,))
        raise CloseoutError(
            "Receipt commit staged an unexpected path set; refusing to continue."
        )

    diff_check = git(repo, "diff", "--cached", "--check", check=False)
    if diff_check.returncode != 0:
        unstage_paths(repo, (policy.receipt_path,))
        detail = (diff_check.stdout or diff_check.stderr).strip()
        raise CloseoutError("Receipt diff check failed:\n" + detail)

    scan_staged_additions_for_secrets(repo)

    message = f"{policy.receipt_commit_message_prefix} {checkpoint_commit[:12]}"
    print(f"\nCreating generated closeout receipt commit: {message}")
    run(("git", "commit", "-m", message), cwd=repo, check=True, capture=False)

    receipt_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    parent = git(repo, "rev-parse", "HEAD^").stdout.strip()
    if parent != checkpoint_commit:
        raise CloseoutError(
            "Receipt commit parent does not match checkpoint commit; refusing to push."
        )

    if git(repo, "status", "--porcelain").stdout.strip():
        raise CloseoutError("Worktree is not clean after receipt commit.")
    return receipt_commit


def pending_state_path(repo: Path) -> Path:
    git_dir_text = git(repo, "rev-parse", "--git-dir").stdout.strip()
    git_dir = Path(git_dir_text)
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()
    return git_dir / "checkpoint_closeout_pending.json"


def write_pending_state(
    repo: Path,
    policy: RepoPolicy,
    checkpoint_commit: str,
    receipt_commit: str,
) -> None:
    path = pending_state_path(repo)
    payload = {
        "schema": "checkpoint_closeout_pending.v1",
        "remote": policy.remote,
        "branch": policy.branch,
        "checkpoint_commit": checkpoint_commit,
        "receipt_commit": receipt_commit,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_pending_state(repo: Path) -> dict[str, object]:
    path = pending_state_path(repo)
    if not path.is_file():
        raise CloseoutError(
            "No helper-created pending closeout state exists. "
            "-PushExisting will not push an arbitrary local commit."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"Pending closeout state is unreadable: {exc}") from exc
    if payload.get("schema") != "checkpoint_closeout_pending.v1":
        raise CloseoutError("Unsupported pending closeout state schema.")
    return payload


def clear_pending_state(repo: Path) -> None:
    path = pending_state_path(repo)
    try:
        path.unlink()
    except FileNotFoundError:
        pass

def push_commit(
    repo: Path,
    policy: RepoPolicy,
    checkpoint_commit: str,
    receipt_commit: str,
) -> bool:
    answer = input(
        "\nPush both local commits to "
        f"{policy.remote}/{policy.branch}?\n"
        f"  checkpoint: {checkpoint_commit[:12]}\n"
        f"  receipt:    {receipt_commit[:12]}\n"
        "Approve push? [y/N]: "
    ).strip().lower()
    if answer not in {"y", "yes"}:
        print(
            "\nBoth commits remain local and were NOT pushed. "
            "To finish later, run:\n"
            "  .\\scripts\\close_checkpoint.ps1 -PushExisting"
        )
        return False

    print("\nPushing...")
    run(
        ("git", "push", policy.remote, f"HEAD:{policy.branch}"),
        cwd=repo,
        check=True,
        capture=False,
    )

    git(repo, "fetch", "--prune", "--quiet", policy.remote)
    local = git(repo, "rev-parse", "HEAD").stdout.strip()
    remote = git(repo, "rev-parse", f"{policy.remote}/{policy.branch}").stdout.strip()
    if local != remote or local != receipt_commit:
        raise CloseoutError(
            "Post-push local/remote commit mismatch; inspect Git state manually."
        )

    if git(repo, "status", "--porcelain").stdout.strip():
        raise CloseoutError("Worktree is not clean after push.")

    clear_pending_state(repo)

    print("\nCHECKPOINT CLOSEOUT: PASS")
    print(f"Checkpoint:  {checkpoint_commit}")
    print(f"Receipt:     {receipt_commit}")
    print(f"Branch:      {policy.branch}")
    print("Remote sync: PASS")
    print("Worktree:    CLEAN")
    return True


def push_existing(repo: Path, policy: RepoPolicy) -> int:
    verify_repo_identity(repo, policy)

    if git(repo, "status", "--porcelain").stdout.strip():
        raise CloseoutError(
            "-PushExisting requires a completely clean working tree and index."
        )

    pending = read_pending_state(repo)
    if pending.get("remote") != policy.remote or pending.get("branch") != policy.branch:
        raise CloseoutError("Pending closeout target does not match current policy.")

    ahead, behind = fetch_and_sync_state(repo, policy)
    if behind != 0 or ahead != 2:
        raise CloseoutError(
            "-PushExisting is allowed only for the helper-created two-commit "
            f"checkpoint+receipt pair (ahead={ahead}, behind={behind})."
        )

    checkpoint_commit = str(pending.get("checkpoint_commit") or "")
    receipt_commit = str(pending.get("receipt_commit") or "")
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    parent = git(repo, "rev-parse", "HEAD^").stdout.strip()
    if head != receipt_commit or parent != checkpoint_commit:
        raise CloseoutError(
            "Current local commits do not match the helper-created pending state."
        )

    changed = git(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        receipt_commit,
    ).stdout.splitlines()
    normalized = {normalize_repo_path(x) for x in changed if x.strip()}
    if normalized != {policy.receipt_path}:
        raise CloseoutError(
            "Pending receipt commit contains paths other than the managed receipt."
        )

    receipt_file = repo / policy.receipt_path
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseoutError(f"Managed receipt is unreadable: {exc}") from exc
    if receipt.get("checkpoint_commit") != checkpoint_commit:
        raise CloseoutError("Managed receipt does not reference the pending checkpoint.")

    print(
        f"\nVerified pending checkpoint: {checkpoint_commit[:12]}\n"
        f"Verified receipt commit:     {receipt_commit[:12]}"
    )
    push_commit(repo, policy, checkpoint_commit, receipt_commit)
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed Git checkpoint closeout helper."
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        help=(
            "Exact repository-relative changed paths approved for this checkpoint. "
            "If omitted, the helper displays all changes and asks for approval."
        ),
    )
    parser.add_argument(
        "--push-existing",
        action="store_true",
        help=(
            "Safely push one already-created local commit when the worktree is clean "
            "and local main is exactly one commit ahead of origin/main."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    staged_by_helper: tuple[str, ...] = ()
    commit_created = False

    try:
        repo = get_repo_root(Path.cwd())
        policy = load_policy(repo)
        require_local_venv(repo)

        print("Event-Market Quant Bot — Safe Checkpoint Closeout")
        print(f"Repository: {policy.name}")
        print(f"Target:     {policy.remote}/{policy.branch}")

        if args.push_existing:
            if args.paths:
                raise CloseoutError("--paths cannot be combined with --push-existing.")
            return push_existing(repo, policy)

        verify_repo_identity(repo, policy)
        require_synced_before_closeout(repo, policy)

        changes = discover_changes(repo)
        reject_tooling_self_modification(changes)
        if policy.receipt_path in set(changes.paths):
            raise CloseoutError(
                f"{policy.receipt_path} is managed by the helper and must not be "
                "manually modified before closeout."
            )
        approved_paths = select_paths(changes, args.paths)
        validate_path_safety(approved_paths, policy)

        print("\nApproved changed files:")
        for path in approved_paths:
            print(f"  {path}")

        validation_evidence = run_pre_stage_checks(repo, policy)

        baseline_head = git(repo, "rev-parse", "HEAD").stdout.strip()
        print("\nStaging only approved paths...")
        stage_paths(repo, approved_paths)
        staged_by_helper = tuple(approved_paths)

        try:
            verify_staged_set(repo, approved_paths, policy)
            scan_staged_additions_for_secrets(repo)
            show_staged_summary(repo)
            message = prompt_commit_message()
        except BaseException:
            unstage_paths(repo, staged_by_helper)
            staged_by_helper = ()
            raise

        try:
            new_head = create_commit(repo, message, baseline_head)
            commit_created = True
            staged_by_helper = ()
        except BaseException:
            if not commit_created:
                unstage_paths(repo, staged_by_helper)
                staged_by_helper = ()
            raise

        print(f"\nCreated checkpoint commit: {new_head[:12]}  {message}")

        receipt = build_closeout_receipt(
            policy=policy,
            baseline_head=baseline_head,
            checkpoint_commit=new_head,
            checkpoint_message=message,
            committed_paths=approved_paths,
            validation_evidence=validation_evidence,
        )
        receipt_commit = write_receipt_commit(
            repo,
            policy,
            receipt,
            new_head,
        )
        write_pending_state(repo, policy, new_head, receipt_commit)
        print(f"Created receipt commit:    {receipt_commit[:12]}")

        push_commit(repo, policy, new_head, receipt_commit)
        return 0

    except KeyboardInterrupt:
        if staged_by_helper and not commit_created:
            try:
                repo = get_repo_root(Path.cwd())
                unstage_paths(repo, staged_by_helper)
            except Exception:
                pass
        print("\nCancelled. No push was performed.", file=sys.stderr)
        return 130
    except CloseoutError as exc:
        print(f"\nCLOSEOUT BLOCKED\n{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

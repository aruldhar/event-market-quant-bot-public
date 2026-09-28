from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "checkpoint_closeout.py"
SPEC = importlib.util.spec_from_file_location("checkpoint_closeout", SCRIPT_PATH)
assert SPEC and SPEC.loader
closeout = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = closeout
SPEC.loader.exec_module(closeout)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "event-market-quant-bot"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-m", "base")
    return repo


def _policy() -> closeout.RepoPolicy:
    return closeout.RepoPolicy(
        name="event-market-quant-bot",
        remote="origin",
        branch="main",
        expected_remote_repository="aruldhar/event-market-quant-bot",
        validators=(),
        test_args=("-m", "pytest", "-q"),
        blocked_paths=(
            ".env",
            ".env.*",
            "*.pem",
            "*.key",
            "secrets/**",
            "credentials/**",
            "data/raw/**",
            "logs/**",
        ),
        blocked_exceptions=(".env.example", "logs/.gitkeep"),
        receipt_path="docs/LAST_CHECKPOINT_CLOSEOUT.json",
        receipt_schema="checkpoint_closeout_receipt.v1",
        receipt_commit_message_prefix="Record checkpoint closeout",
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://github.com/aruldhar/event-market-quant-bot.git",
            "aruldhar/event-market-quant-bot",
        ),
        (
            "git@github.com:aruldhar/event-market-quant-bot.git",
            "aruldhar/event-market-quant-bot",
        ),
        (
            "ssh://git@github.com/aruldhar/event-market-quant-bot.git",
            "aruldhar/event-market-quant-bot",
        ),
    ],
)
def test_normalize_remote_repository(url: str, expected: str) -> None:
    assert closeout.normalize_remote_repository(url) == expected


def test_git_wrapper_forces_utf8_decoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(
        args,
        *,
        cwd,
        check=True,
        capture=True,
        encoding=None,
    ):
        observed["args"] = tuple(args)
        observed["cwd"] = cwd
        observed["check"] = check
        observed["capture"] = capture
        observed["encoding"] = encoding
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(closeout, "run", fake_run)

    completed = closeout.git(
        tmp_path,
        "diff",
        "--cached",
        "--no-color",
        check=False,
        capture=True,
    )

    assert completed.returncode == 0
    assert observed["args"] == (
        "git",
        "diff",
        "--cached",
        "--no-color",
    )
    assert observed["cwd"] == tmp_path
    assert observed["check"] is False
    assert observed["capture"] is True
    assert observed["encoding"] == "utf-8"


def test_normalize_remote_rejects_non_github() -> None:
    with pytest.raises(closeout.CloseoutError):
        closeout.normalize_remote_repository("https://example.com/repo.git")


def test_normalize_repo_path_rejects_escape() -> None:
    with pytest.raises(closeout.CloseoutError):
        closeout.normalize_repo_path("../secret.txt")


def test_discover_changes_finds_modified_deleted_and_untracked(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "delete_me.txt").write_text("delete\n", encoding="utf-8")
    _git(repo, "add", "delete_me.txt")
    _git(repo, "commit", "-m", "add delete target")

    (repo / "base.txt").write_text("changed\n", encoding="utf-8")
    (repo / "delete_me.txt").unlink()
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    changes = closeout.discover_changes(repo)
    assert set(changes.paths) == {"base.txt", "delete_me.txt", "new.txt"}


def test_discover_and_staged_paths_include_both_sides_of_rename(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "old.txt").write_text("rename\n", encoding="utf-8")
    _git(repo, "add", "old.txt")
    _git(repo, "commit", "-m", "add rename target")

    _git(repo, "mv", "old.txt", "new.txt")
    # git mv stages automatically, but the helper forbids pre-existing staging.
    _git(repo, "reset", "HEAD", "--", "old.txt", "new.txt")

    changes = closeout.discover_changes(repo)
    assert {"old.txt", "new.txt"}.issubset(set(changes.paths))

    closeout.stage_paths(repo, changes.paths)
    assert {"old.txt", "new.txt"}.issubset(closeout.staged_paths(repo))


def test_select_paths_rejects_unapproved_changed_file() -> None:
    changes = closeout.ChangeSet(
        paths=("a.txt", "b.txt"),
        display_rows=("M\ta.txt", "M\tb.txt"),
    )
    with pytest.raises(closeout.CloseoutError, match="Unexpected changed paths"):
        closeout.select_paths(changes, ["a.txt"])


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "private.key",
        "secrets/token.txt",
        "credentials/kalshi.json",
        "data/raw/run.jsonl",
        "logs/runtime.jsonl",
    ],
)
def test_blocked_paths_fail_closed(path: str) -> None:
    with pytest.raises(closeout.CloseoutError):
        closeout.validate_path_safety([path], _policy())


@pytest.mark.parametrize("path", [".env.example", "logs/.gitkeep"])
def test_blocked_path_exceptions_are_allowed(path: str) -> None:
    closeout.validate_path_safety([path], _policy())


def test_unstage_paths_preserves_worktree_content(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "base.txt").write_text("working tree survives\n", encoding="utf-8")

    closeout.stage_paths(repo, ["base.txt"])
    assert closeout.staged_paths(repo) == {"base.txt"}

    closeout.unstage_paths(repo, ["base.txt"])
    assert closeout.staged_paths(repo) == set()
    assert (repo / "base.txt").read_text(encoding="utf-8") == "working tree survives\n"


def test_secret_scan_blocks_private_key_added_line(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "danger.txt").write_text(
        "-----BEGIN PRIVATE KEY-----\nabc\n",
        encoding="utf-8",
    )
    closeout.stage_paths(repo, ["danger.txt"])

    with pytest.raises(closeout.CloseoutError, match="private-key material"):
        closeout.scan_staged_additions_for_secrets(repo)


def test_secret_scan_allows_normal_text(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "safe.txt").write_text("normal checkpoint text\n", encoding="utf-8")
    closeout.stage_paths(repo, ["safe.txt"])
    closeout.scan_staged_additions_for_secrets(repo)


def test_build_receipt_records_checkpoint_without_self_reference() -> None:
    receipt = closeout.build_closeout_receipt(
        policy=_policy(),
        baseline_head="a" * 40,
        checkpoint_commit="b" * 40,
        checkpoint_message="Example checkpoint",
        committed_paths=["src/example.py"],
        validation_evidence=[
            {
                "kind": "tests",
                "name": "full pytest suite",
                "returncode": 0,
                "output": "1 passed",
            }
        ],
    )
    assert receipt["schema"] == "checkpoint_closeout_receipt.v1"
    assert receipt["checkpoint_commit"] == "b" * 40
    assert receipt["baseline_commit"] == "a" * 40
    assert "receipt_commit" not in receipt
    assert receipt["safety"]["staged_path_exact_match"] == "PASS"


def test_pending_state_round_trip_inside_git_dir(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    policy = _policy()
    closeout.write_pending_state(repo, policy, "a" * 40, "b" * 40)

    state = closeout.read_pending_state(repo)
    assert state["checkpoint_commit"] == "a" * 40
    assert state["receipt_commit"] == "b" * 40

    closeout.clear_pending_state(repo)
    with pytest.raises(closeout.CloseoutError, match="No helper-created pending"):
        closeout.read_pending_state(repo)


def test_fetch_and_sync_state_reports_ahead_and_behind(tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = _init_repo(tmp_path)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")

    policy = _policy()
    ahead, behind = closeout.fetch_and_sync_state(repo, policy)
    assert (ahead, behind) == (0, 0)

    (repo / "local.txt").write_text("local\n", encoding="utf-8")
    _git(repo, "add", "local.txt")
    _git(repo, "commit", "-m", "local")
    ahead, behind = closeout.fetch_and_sync_state(repo, policy)
    assert (ahead, behind) == (1, 0)


def test_operation_marker_is_detected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    git_dir = Path(_git(repo, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    (git_dir / "MERGE_HEAD").write_text("deadbeef\n", encoding="utf-8")

    assert "MERGE_HEAD" in closeout.operation_markers(repo)


def test_helper_sources_do_not_contain_destructive_git_commands() -> None:
    engine = SCRIPT_PATH.read_text(encoding="utf-8").lower()
    wrapper = (
        SCRIPT_PATH.parent / "close_checkpoint.ps1"
    ).read_text(encoding="utf-8").lower()
    combined = engine + "\n" + wrapper

    prohibited = [
        "reset --hard",
        "git clean -",
        "push --force",
        "push -f",
        "git add .",
        "checkout -- .",
    ]
    for token in prohibited:
        assert token not in combined


def test_tooling_self_modification_is_rejected() -> None:
    changes = closeout.ChangeSet(
        paths=("scripts/checkpoint_closeout.py", "docs/README.md"),
        display_rows=(),
    )
    with pytest.raises(closeout.CloseoutError, match="will not certify"):
        closeout.reject_tooling_self_modification(changes)


def test_load_policy_reads_committed_head_not_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "configs").mkdir()
    committed = {
        "schema": "checkpoint_closeout_config.v1",
        "repository": {
            "name": "event-market-quant-bot",
            "remote": "origin",
            "branch": "main",
            "expected_remote_repository": "aruldhar/event-market-quant-bot",
        },
        "validators": [],
        "tests": {"args": ["-m", "pytest", "-q"]},
        "blocked_paths": [".env"],
        "allowed_blocked_path_exceptions": [".env.example"],
        "receipt": {
            "path": "docs/LAST_CHECKPOINT_CLOSEOUT.json",
            "schema": "checkpoint_closeout_receipt.v1",
            "commit_message_prefix": "Record checkpoint closeout",
        },
    }
    path = repo / "configs" / "checkpoint_closeout.json"
    path.write_text(json.dumps(committed), encoding="utf-8")
    _git(repo, "add", "configs/checkpoint_closeout.json")
    _git(repo, "commit", "-m", "policy")

    # Tamper with the working copy. load_policy must still use HEAD.
    working = dict(committed)
    working["repository"] = dict(committed["repository"])
    working["repository"]["branch"] = "evil-branch"
    path.write_text(json.dumps(working), encoding="utf-8")

    policy = closeout.load_policy(repo)
    assert policy.branch == "main"

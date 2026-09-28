from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1_validation import (
    DEPENDENCY_FILES,
    IMPLEMENTATION_FILES,
    IMPLEMENTATION_FREEZE_DEFAULT,
    PARENT_COMMIT,
    build_implementation_freeze,
    sha256_file,
    write_json,
)

def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(IMPLEMENTATION_FREEZE_DEFAULT),
    )
    args = parser.parse_args()

    git("fetch", "origin")
    head = git("rev-parse", "HEAD")
    remote = git("rev-parse", "origin/main")
    if head != PARENT_COMMIT or remote != PARENT_COMMIT:
        raise RuntimeError(
            f"expected HEAD == origin/main == {PARENT_COMMIT}; "
            f"HEAD={head}, origin/main={remote}"
        )

    for relative in DEPENDENCY_FILES:
        if not Path(relative).is_file():
            raise RuntimeError(f"missing dependency: {relative}")
        result = subprocess.run(
            ["git", "diff", "--quiet", "--", relative],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"tracked dependency has local changes: {relative}")

    for relative in IMPLEMENTATION_FILES:
        if not Path(relative).is_file():
            raise RuntimeError(f"missing validation implementation file: {relative}")

    implementation_hashes = {
        relative: sha256_file(relative)
        for relative in IMPLEMENTATION_FILES
    }
    dependency_hashes = {
        relative: sha256_file(relative)
        for relative in DEPENDENCY_FILES
    }
    document = build_implementation_freeze(
        implementation_sha256s=implementation_hashes,
        dependency_sha256s=dependency_hashes,
    )

    output = Path(args.output)
    if output.exists():
        from src.kxbtcd_candidate_e_entry_model_v1_validation import read_json
        if read_json(output) != document:
            raise RuntimeError(
                f"existing implementation freeze differs: {output}"
            )
        print("Candidate-E Entry Model v1 validation implementation freeze: ALREADY FROZEN")
    else:
        write_json(output, document)
        print("Candidate-E Entry Model v1 validation implementation freeze: CREATED")

    print(
        "validation_implementation_fingerprint="
        + document["validation_implementation_fingerprint"]
    )
    print("outcomes_read_during_implementation_freeze=false")
    print("validation_scores_calculated=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

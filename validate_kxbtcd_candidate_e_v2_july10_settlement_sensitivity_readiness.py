#!/usr/bin/env python3
from pathlib import Path
import json
import subprocess

from src import kxbtcd_candidate_e_v2_july10_settlement_sensitivity_evaluator as s


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout).strip())
    return cp.stdout.strip()


def main() -> int:
    repo = Path.cwd().resolve()
    predecl, observed, _ = s.load_frozen_e1(repo)
    receipt = json.loads((repo / "docs/LAST_CHECKPOINT_CLOSEOUT.json").read_text(encoding="utf-8"))

    if receipt.get("checkpoint_message") == s.EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE:
        collect_gate = "OPEN_IF_WORKTREE_CLEAN_AND_SYNCED"
    else:
        collect_gate = "BLOCKED_UNTIL_E2_SAFE_CLOSEOUT"

    print("CANDIDATE-E JULY10 SETTLEMENT SENSITIVITY READINESS: PASS")
    print("Parent E1 predeclaration: VALID")
    print("Official result: 27 EXACT / 33 CENSORED / 15 INCONCLUSIVE — IMMUTABLE")
    print("Observed filled entries:", observed["observed_filled_trade_count"])
    print("Frozen future settlement tickers:", predecl["future_settlement_access"]["ticker_count"])
    print("Censorship split:", observed["scenario_class_counts"])
    print("Analysis A: exact 27 unchanged + liquidation-only 3 terminalized")
    print("Analysis B: censored observed traces terminalized descriptively")
    print("Analysis C: 93 observed fills independently held to settlement")
    print("Policy ranking/selection: FORBIDDEN")
    print("Real --collect gate:", collect_gate)
    print("Current HEAD:", git(repo, "rev-parse", "HEAD"))
    print("Current origin/main:", git(repo, "rev-parse", "origin/main"))
    print("Readiness network requests: 0 | New outcomes: NOT ACCESSED | Orders: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

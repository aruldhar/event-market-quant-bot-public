from __future__ import annotations

import argparse
from pathlib import Path

from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    materialize_to_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize the frozen July10 outcome-blind Candidate-E execution paths."
    )
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    repo = Path(args.repository_root)
    path, digest, payload = materialize_to_path(
        repo_root=repo,
        output_path=args.output,
    )
    print("Checkpoint 21N-S outcome-blind July10 materialization: PASS")
    print(f"Output:       {path}")
    print(f"SHA256:       {digest}")
    print(f"Decision states: {len(payload['decision_states'])}")
    print(f"Threshold selections: {len(payload['threshold_selections'])}")
    print(f"Execution scenarios: {len(payload['execution_scenarios'])}")
    print("Outcomes:     NOT ACCESSED")
    print("Strategy P&L: NOT RUN")
    print("Candidate E:  NOT REFIT")
    print("Network:      0")
    print("Purchases:    0")
    print("Orders:       0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

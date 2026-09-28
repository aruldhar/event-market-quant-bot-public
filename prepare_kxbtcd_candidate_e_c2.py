"""Create/freeze Champion-R1 after 21E-A has been safely closed.

This command is network-free. It fits the unchanged Candidate-E Distance
specification on already-exposed H1+H2+H3+C1 only. It does not materialize C2,
open C2 outcomes, touch C3, or perform execution.
"""
from __future__ import annotations

from src.kxbtcd_candidate_e_c2_preparation import (
    CandidateEC2PreparationError,
    write_or_validate_r1_model,
)


def main() -> None:
    path, document = write_or_validate_r1_model()
    print("Checkpoint 21E-B Champion-R1 fit: PASS")
    print(f"Champion-R1 fingerprint: {document['champion_r1_fingerprint']}")
    print(f"beta_distance: {document['model']['beta_distance']}")
    print("Fit scope: 3,500 exposed H1+H2+H3+C1 events")
    print("C2 outcomes opened: 0")
    print("Network requests: 0")
    print("Orders placed: 0")
    print(f"Model artifact: {path.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC2PreparationError as exc:
        raise SystemExit(f"Champion-R1 preparation error: {exc}") from exc

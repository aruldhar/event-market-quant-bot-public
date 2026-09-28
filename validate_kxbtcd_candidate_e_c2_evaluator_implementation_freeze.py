"""Validate the frozen Candidate-E C2 evaluator implementation offline."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c2_evaluation import (
    CandidateEC2EvaluationError,
    validate_c2_implementation_freeze,
)


def main() -> None:
    document = validate_c2_implementation_freeze(
        verify_local_frozen_data=True,
    )
    identity = document["C2_identity"]

    print(
        "Candidate-E C2 evaluator implementation "
        "freeze validation: PASS"
    )
    print(
        "Implementation fingerprint: "
        f"{document['c2_implementation_fingerprint']}"
    )
    print(
        "C2 validation fingerprint: "
        f"{document['c2_validation_fingerprint']}"
    )
    print(
        "Champion-R1 fingerprint: "
        f"{document['champion_r1_fingerprint']}"
    )
    print(
        "C2 events / rows / markets: "
        f"{identity['event_count']} / "
        f"{identity['row_count']} / "
        f"{identity['market_count']}"
    )
    print("C2 outcomes opened: 0")
    print("Network requests: 0")
    print("Orders placed: 0")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC2EvaluationError as exc:
        raise SystemExit(
            "Candidate-E C2 evaluator implementation "
            f"freeze validation: FAIL\n{exc}"
        ) from exc

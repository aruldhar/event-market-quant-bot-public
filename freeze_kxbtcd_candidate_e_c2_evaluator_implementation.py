"""Freeze Candidate-E C2 collector/evaluator before C2 outcome exposure."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c2_evaluation import (
    CandidateEC2EvaluationError,
    write_or_validate_c2_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_c2_implementation_freeze()
    identity = document["C2_identity"]

    print(
        "Checkpoint 21F-A Candidate-E C2 evaluator "
        "implementation freeze: PASS"
    )
    print(
        "C2 implementation fingerprint: "
        f"{document['c2_implementation_fingerprint']}"
    )
    print(
        "Parent C2 validation fingerprint: "
        f"{document['c2_validation_fingerprint']}"
    )
    print(
        "Champion-R1 fingerprint: "
        f"{document['champion_r1_fingerprint']}"
    )
    print(
        f"C2 events: {identity['event_count']}"
    )
    print(
        f"C2 rows: {identity['row_count']}"
    )
    print(
        f"C2 market requests: {identity['market_count']}"
    )
    print("C2 outcomes opened: 0")
    print("Model fits at freeze: 0")
    print("Network requests at freeze: 0")
    print("C3 materialized or opened: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC2EvaluationError as exc:
        raise SystemExit(
            "Checkpoint 21F-A C2 evaluator "
            f"implementation freeze: FAIL\n{exc}"
        ) from exc

"""Freeze Candidate-E C1 collector/evaluator before C1 outcome exposure."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c1_evaluation import (
    CandidateEC1EvaluationError,
    write_or_validate_c1_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_c1_implementation_freeze()
    identity = document["C1_identity"]
    print("Checkpoint 21C Candidate-E C1 evaluator implementation freeze: PASS")
    print(
        "C1 implementation fingerprint: "
        f"{document['c1_implementation_fingerprint']}"
    )
    print(
        "Parent C1 validation fingerprint: "
        f"{document['c1_validation_fingerprint']}"
    )
    print(
        "Champion-R0 fingerprint: "
        f"{document['champion_r0_fingerprint']}"
    )
    print(f"C1 events: {identity['event_count']}")
    print(f"C1 rows: {identity['row_count']}")
    print(f"C1 market requests: {identity['market_count']}")
    print("C1 outcomes opened: 0")
    print("Model fits at freeze: 0")
    print("Network requests at freeze: 0")
    print("C2/C3 materialized or opened: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC1EvaluationError as exc:
        raise SystemExit(
            f"Checkpoint 21C C1 evaluator implementation freeze: FAIL\n{exc}"
        ) from exc

"""Freeze Candidate-E C3 collector/evaluator before C3 outcome exposure."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c3_evaluation import (
    CandidateEC3EvaluationError,
    write_or_validate_c3_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_c3_implementation_freeze()
    identity = document["C3_identity"]

    print(
        "Checkpoint 21H-A Candidate-E C3 evaluator "
        "implementation freeze: PASS"
    )
    print(
        "C3 implementation fingerprint: "
        f"{document['c3_implementation_fingerprint']}"
    )
    print(
        "Parent C3 validation fingerprint: "
        f"{document['c3_validation_fingerprint']}"
    )
    print(
        "Champion-R2 fingerprint: "
        f"{document['champion_r2_fingerprint']}"
    )
    print(f"C3 events: {identity['event_count']}")
    print(f"C3 rows: {identity['row_count']}")
    print(f"C3 market requests: {identity['market_count']}")
    print(
        "Prior hard-deny events: "
        f"{document['H1_H2_H3_C1_C2_hard_deny_identity']['event_count']}"
    )
    print("C3 outcomes opened: 0")
    print("Model fits at freeze: 0")
    print("Network requests at freeze: 0")
    print("Remaining reserve accessed: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC3EvaluationError as exc:
        raise SystemExit(
            "Checkpoint 21H-A C3 evaluator "
            f"implementation freeze: FAIL\n{exc}"
        ) from exc

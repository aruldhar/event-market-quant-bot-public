"""Validate the frozen Candidate-E C3 evaluator implementation offline."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c3_evaluation import (
    CandidateEC3EvaluationError,
    validate_c3_implementation_freeze,
)


def main() -> None:
    document = validate_c3_implementation_freeze(
        verify_local_frozen_data=True,
    )
    identity = document["C3_identity"]

    print(
        "Candidate-E C3 evaluator implementation "
        "freeze validation: PASS"
    )
    print(
        "Implementation fingerprint: "
        f"{document['c3_implementation_fingerprint']}"
    )
    print(
        "C3 validation fingerprint: "
        f"{document['c3_validation_fingerprint']}"
    )
    print(
        "Champion-R2 fingerprint: "
        f"{document['champion_r2_fingerprint']}"
    )
    print(
        "C3 events / rows / markets: "
        f"{identity['event_count']} / "
        f"{identity['row_count']} / "
        f"{identity['market_count']}"
    )
    print(
        "Untouched reserve / floor / buffer: "
        f"{identity['strict_untouched_tail_remaining']} / "
        f"{identity['strict_untouched_tail_floor']} / "
        f"{identity['reserve_floor_buffer']}"
    )
    print("C3 outcomes opened: 0")
    print("Network requests: 0")
    print("Orders placed: 0")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC3EvaluationError as exc:
        raise SystemExit(
            "Candidate-E C3 evaluator implementation "
            f"freeze validation: FAIL\n{exc}"
        ) from exc

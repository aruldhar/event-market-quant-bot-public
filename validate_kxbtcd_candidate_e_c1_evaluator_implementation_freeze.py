"""Offline validator for the frozen Checkpoint-21C C1 evaluator implementation."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c1_evaluation import (
    CandidateEC1EvaluationError,
    validate_c1_implementation_freeze,
)


def main() -> None:
    document = validate_c1_implementation_freeze(verify_local_frozen_data=True)
    print("Checkpoint 21C C1 evaluator implementation validation: PASS")
    print(f"Fingerprint: {document['c1_implementation_fingerprint']}")
    print(f"C1 validation: {document['c1_validation_fingerprint']}")
    print(f"Champion-R0: {document['champion_r0_fingerprint']}")
    print("C1 outcomes opened at freeze: 0")
    print("Network requests at freeze: 0")
    print("C2/C3 access: prohibited")
    print("Orders placed: 0")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC1EvaluationError as exc:
        raise SystemExit(f"Checkpoint 21C validator: FAIL\n{exc}") from exc

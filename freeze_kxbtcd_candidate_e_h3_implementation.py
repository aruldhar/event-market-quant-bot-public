"""Freeze Candidate-E H3 collector/evaluator before H3 exposure."""
from __future__ import annotations

from src.kxbtcd_candidate_e_h3_evaluation import (
    CandidateEH3EvaluationError,
    write_or_validate_h3_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_h3_implementation_freeze()
    print("Checkpoint-20H Candidate-E H3 implementation freeze: PASS")
    print(
        "H3 implementation fingerprint: "
        f"{document['h3_implementation_fingerprint']}"
    )
    print(
        "Parent H3 validation fingerprint: "
        f"{document['h3_validation_fingerprint']}"
    )
    print(
        "Final H1+H2 model fingerprint: "
        f"{document['final_h1_h2_model_fingerprint']}"
    )
    print(f"H3 events: {document['H3_identity']['event_count']}")
    print(f"H3 rows: {document['H3_identity']['row_count']}")
    print(f"H3 market requests: {document['H3_identity']['market_count']}")
    print("H3 outcomes opened: 0")
    print("Model fits at freeze: 0")
    print("Network requests at freeze: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEH3EvaluationError as exc:
        raise SystemExit(
            f"Checkpoint-20H H3 implementation freeze: FAIL\n{exc}"
        ) from exc

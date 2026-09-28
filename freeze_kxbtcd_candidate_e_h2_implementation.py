"""Freeze Candidate-E H2 evaluator/collector implementation before H2 exposure."""
from __future__ import annotations

from src.kxbtcd_candidate_e_h2_evaluation import (
    CandidateEH2EvaluationError,
    write_or_validate_h2_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_h2_implementation_freeze()
    print("Checkpoint-20D Candidate-E H2 implementation freeze: PASS")
    print(
        "H2 implementation fingerprint: "
        f"{document['h2_implementation_fingerprint']}"
    )
    print(
        "Parent H2 validation fingerprint: "
        f"{document['h2_validation_fingerprint']}"
    )
    print(
        "Final H1 model fingerprint: "
        f"{document['final_h1_model_fingerprint']}"
    )
    print(f"H2 events: {document['H2_identity']['event_count']}")
    print(f"H2 rows: {document['H2_identity']['row_count']}")
    print(f"H2 market requests: {document['H2_identity']['market_count']}")
    print("H2 outcomes opened: 0")
    print("H3 outcomes opened: 0")
    print("Model fits at freeze: 0")
    print("Network requests at freeze: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEH2EvaluationError as exc:
        raise SystemExit(f"Checkpoint-20D H2 implementation freeze: FAIL\n{exc}") from exc

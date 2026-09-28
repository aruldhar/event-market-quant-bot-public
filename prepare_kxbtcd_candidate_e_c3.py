"""Fit/freeze Candidate-E Champion-R2 using exposed H1+H2+H3+C1+C2 only.

This command is network-free and must be run only after Checkpoint 21G-A is
safely closed and pushed. It does not materialize C3 or open C3 outcomes.
"""
from __future__ import annotations

from src.kxbtcd_candidate_e_c3_preparation import (
    CandidateEC3PreparationError,
    write_or_validate_r2_model,
)


def main() -> None:
    path, document = (
        write_or_validate_r2_model()
    )
    fit_scope = document[
        "fit_scope"
    ]
    fit_result = document[
        "fit_result"
    ]

    print(
        "Checkpoint 21G-B Champion-R2 fit: PASS"
    )
    print(
        "Champion-R2 fingerprint: "
        f"{document['champion_r2_fingerprint']}"
    )
    print(
        "beta_distance: "
        f"{document['model']['beta_distance']}"
    )
    print(
        "Fit scope: "
        f"{fit_scope['event_count']} exposed "
        "H1+H2+H3+C1+C2 events / "
        f"{fit_scope['row_count']} rows"
    )
    print(
        "Fit objective: "
        f"{fit_result['fit_objective']}"
    )
    print(
        "Iterations: "
        f"{fit_result['iterations']}"
    )
    print(
        "Converged: "
        f"{fit_result['converged']}"
    )
    print("C3 rows used: 0")
    print("C3 outcomes opened: 0")
    print("Network requests: 0")
    print("Orders placed: 0")
    print(f"Artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC3PreparationError as exc:
        raise SystemExit(
            f"Checkpoint 21G-B Champion-R2 fit: FAIL\n{exc}"
        ) from exc

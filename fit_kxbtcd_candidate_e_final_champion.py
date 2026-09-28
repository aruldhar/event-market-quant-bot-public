"""Fit/freeze Candidate-E Champion-Final on all 4,500 exposed events.

DO NOT run until Checkpoint 21I-A has been safely closed and pushed.

This command is offline. It uses only previously exposed H1/H2/H3/C1/C2/C3
rows and outcomes. It performs no network requests and does not access the
remaining 4,676-event historical reserve.
"""
from __future__ import annotations

from src.kxbtcd_candidate_e_final_fit import (
    CandidateEFinalFitError,
    write_or_validate_final_model,
)


def main() -> None:
    path, document = write_or_validate_final_model()
    scope = document["fit_scope"]
    fit = document["fit_result"]

    print("Checkpoint 21I-B Champion-Final fit: PASS")
    print(
        "Champion-Final fingerprint: "
        f"{document['champion_final_fingerprint']}"
    )
    print(
        "beta_distance: "
        f"{document['model']['beta_distance']}"
    )
    print(
        "Fit scope: "
        f"{scope['event_count']} exposed H1+H2+H3+C1+C2+C3 events / "
        f"{scope['row_count']} rows"
    )
    print(
        "Fit objective: "
        f"{fit['fit_objective']}"
    )
    print(f"Iterations: {fit['iterations']}")
    print(f"Converged: {fit['converged']}")
    print("Fresh validation claim: no")
    print("Remaining historical reserve rows used: 0")
    print("Remaining historical reserve outcomes accessed: no")
    print("Network requests: 0")
    print("Orders placed: 0")
    print(f"Artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEFinalFitError as exc:
        raise SystemExit(
            f"Checkpoint 21I-B Champion-Final fit: FAIL\n{exc}"
        ) from exc

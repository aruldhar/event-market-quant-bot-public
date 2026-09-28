"""Freeze Candidate-E Champion-R2 / C3 preparation implementation."""
from __future__ import annotations

from src.kxbtcd_candidate_e_c3_preparation import (
    CandidateEC3PreparationError,
    write_or_validate_implementation_freeze,
)


def main() -> None:
    path, document = (
        write_or_validate_implementation_freeze()
    )
    fit = document["R2_fit_contract"]
    materialization = document[
        "C3_materialization_contract"
    ]

    print(
        "Checkpoint 21G-A Candidate-E C3 "
        "preparation implementation freeze: PASS"
    )
    print(
        "Implementation fingerprint: "
        f"{document['implementation_freeze_fingerprint']}"
    )
    print(
        "Parent C2 result fingerprint: "
        f"{document['parent_c2_result_fingerprint']}"
    )
    print(
        "Champion-R2 fit scope: "
        f"{fit['event_count']} exposed events / "
        f"{fit['row_count']} rows"
    )
    print(
        "C3 strict-tail start index: "
        f"{materialization['strict_tail_start_index']}"
    )
    print(
        "C3 maximum candidate identities: "
        f"{materialization['max_candidate_identities_for_C3']}"
    )
    print("Champion-R2 fit performed: 0")
    print("C3 materialized: 0")
    print("C3 outcomes opened: 0")
    print("Network requests at freeze: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC3PreparationError as exc:
        raise SystemExit(
            "Checkpoint 21G-A C3 preparation "
            f"implementation freeze: FAIL\n{exc}"
        ) from exc

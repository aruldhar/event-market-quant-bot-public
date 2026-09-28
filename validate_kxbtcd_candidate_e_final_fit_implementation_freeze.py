"""Validate the frozen Candidate-E final historical fit implementation."""
from __future__ import annotations

from src.kxbtcd_candidate_e_final_fit import (
    CandidateEFinalFitError,
    load_and_validate_implementation_freeze,
)


def main() -> None:
    document = load_and_validate_implementation_freeze()
    fit = document["final_fit_contract"]
    reserve = document["reserve_policy"]

    print(
        "Candidate-E final historical fit implementation "
        "freeze validation: PASS"
    )
    print(
        "Implementation fingerprint: "
        f"{document['implementation_freeze_fingerprint']}"
    )
    print(
        "Final fit events / rows: "
        f"{fit['event_count']} / {fit['row_count']}"
    )
    print(
        "Untouched reserve / floor / buffer: "
        f"{reserve['strict_untouched_tail_remaining']} / "
        f"{reserve['strict_untouched_tail_floor']} / "
        f"{reserve['strict_untouched_tail_buffer']}"
    )
    print("Final fit performed: 0")
    print("Network requests: 0")
    print("Orders placed: 0")


if __name__ == "__main__":
    try:
        main()
    except CandidateEFinalFitError as exc:
        raise SystemExit(
            "Candidate-E final-fit implementation validation: FAIL\n"
            f"{exc}"
        ) from exc

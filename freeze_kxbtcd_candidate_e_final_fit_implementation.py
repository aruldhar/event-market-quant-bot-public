"""Freeze Candidate-E final historical fit implementation before fitting."""
from __future__ import annotations

from src.kxbtcd_candidate_e_final_fit import (
    CandidateEFinalFitError,
    write_or_validate_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_implementation_freeze()
    fit = document["final_fit_contract"]
    reserve = document["reserve_policy"]

    print(
        "Checkpoint 21I-A Candidate-E final historical fit "
        "implementation freeze: PASS"
    )
    print(
        "Implementation fingerprint: "
        f"{document['implementation_freeze_fingerprint']}"
    )
    print(
        "Parent C3 result-closeout fingerprint: "
        f"{document['parent_c3_result_closeout_fingerprint']}"
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
    print("Final fit performed at freeze: 0")
    print("Network requests at freeze: 0")
    print("Reserve accessed at freeze: 0")
    print("Orders placed: 0")
    print(f"Freeze artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEFinalFitError as exc:
        raise SystemExit(
            "Checkpoint 21I-A final-fit implementation freeze: FAIL\n"
            f"{exc}"
        ) from exc

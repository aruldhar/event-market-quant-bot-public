"""Freeze Checkpoint-21B-A C1-preparation implementation bytes. No network/outcomes."""
from src.kxbtcd_candidate_e_c1_preparation import (
    CandidateEC1PreparationError,
    write_or_validate_implementation_freeze,
)


def main() -> None:
    path, document = write_or_validate_implementation_freeze()
    print("Checkpoint 21B-A C1 preparation implementation freeze: PASS")
    print(f"Fingerprint: {document['implementation_freeze_fingerprint']}")
    print("Network requests: 0")
    print("C1 outcomes opened: 0")
    print("C2/C3 materialization authorized: false")
    print("Orders placed: 0")
    print(f"Freeze: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC1PreparationError as exc:
        raise SystemExit(f"Checkpoint-21B-A freeze error: {exc}") from exc

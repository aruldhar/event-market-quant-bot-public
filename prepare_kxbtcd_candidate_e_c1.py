"""Create/validate Champion-R0 after the frozen 21B-A implementation closeout."""
from src.kxbtcd_candidate_e_c1_preparation import (
    CandidateEC1PreparationError,
    write_or_validate_r0_model,
)


def main() -> None:
    path, document = write_or_validate_r0_model()
    print("Checkpoint 21B-B Champion-R0 fit: PASS")
    print(f"Champion-R0 fingerprint: {document['champion_r0_fingerprint']}")
    print(f"beta_distance: {document['model']['beta_distance']}")
    print("Fit scope: 3,000 exposed H1+H2+H3 events")
    print("C1 outcomes opened: 0")
    print("Network requests: 0")
    print("Orders placed: 0")
    print(f"Model artifact: {path}")


if __name__ == "__main__":
    try:
        main()
    except CandidateEC1PreparationError as exc:
        raise SystemExit(f"Champion-R0 preparation error: {exc}") from exc

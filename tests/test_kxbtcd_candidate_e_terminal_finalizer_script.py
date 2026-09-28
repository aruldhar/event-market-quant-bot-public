from pathlib import Path


def test_terminal_finalizer_archives_before_an_explicit_verified_prune():
    text = Path("deploy/finalize-kxbtcd-terminal-run.sh").read_text(encoding="utf-8")

    assert "set -eu" in text
    assert "settlement_closeout.json" in text
    assert "candidate_e_offsite_archive" in text
    assert "candidate_e_verified_local_prune" in text
    assert "--confirm-prune" in text
    assert text.index("candidate_e_offsite_archive") < text.index(
        "candidate_e_verified_local_prune"
    )
    assert "if [ \"$confirm_prune\" = true ]" in text
    assert "shared shadow ledger is always retained" in text

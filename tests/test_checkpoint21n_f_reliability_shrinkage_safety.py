from pathlib import Path

def test_no_network_or_execution_surface():
    paths = [
        Path("src/kxbtcd_candidate_e_reliability_shrinkage_entry_v2.py"),
        Path("audit_kxbtcd_candidate_e_reliability_shrinkage_entry_v2_opportunities.py"),
    ]
    forbidden = (
        "import requests", "from requests", "import websockets", "from websockets",
        ".create_order(", ".cancel_order(", ".submit_order(", "requests.",
        "websockets.connect(",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text

def test_predeclaration_explicitly_blocks_outcomes_and_pnl():
    text = Path("docs/KXBTCD_CANDIDATE_E_RELIABILITY_SHRINKAGE_ENTRY_V2_PREDECLARATION.md").read_text(encoding="utf-8")
    assert "No Strategy-v2 P&L is opened in 21N-F" in text
    assert "at least 10% of the 820 alpha=1" in text
    assert "C1+C2 Strategy-v1 and Strategy-v2 economics remain unopened" in text

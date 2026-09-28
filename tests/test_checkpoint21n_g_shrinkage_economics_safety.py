from pathlib import Path

def test_protocol_explicitly_excludes_025_and_1():
    text = Path("docs/KXBTCD_CANDIDATE_E_RELIABILITY_SHRINKAGE_ENTRY_V2_DEVELOPMENT_ECONOMICS.md").read_text(encoding="utf-8")
    assert "Exactly two:" in text
    assert "`alpha = 0.50`" in text
    assert "`alpha = 0.75`" in text
    assert "**Outcome scoring is prohibited.**" in text
    assert "**Outcome rescoring is prohibited.**" in text
    assert "C1+C2 Strategy-v2 economics are **not authorized now**" in text

def test_evaluator_has_no_network_or_order_surface():
    paths = (
        Path("src/kxbtcd_candidate_e_reliability_shrinkage_entry_v2_economics.py"),
        Path("evaluate_kxbtcd_candidate_e_reliability_shrinkage_entry_v2_development_economics.py"),
    )
    forbidden = (
        "import requests", "from requests", "import websockets", "from websockets",
        ".create_order(", ".cancel_order(", ".submit_order(", "requests.",
        "websockets.connect(",
    )
    for path in paths:
        lower = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in lower

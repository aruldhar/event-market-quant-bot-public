from pathlib import Path

def test_successor_direction_is_non_authorizing():
    text=Path("docs/KXBTCD_CANDIDATE_E_STRATEGY_SUCCESSOR_DIRECTION.md").read_text(encoding="utf-8")
    assert "Advance the deterministic reliability-adjusted entry baseline first" in text
    assert "exact adjustment is **not selected" in text
    assert "deferred, not permanently rejected" in text
    assert "No C1+C2 Strategy-v1 economics" in text

from src.kxbtcd_candidate_e_soak_kalshi_credentials import kalshi_read_only_credentials


def test_read_only_credentials_load_without_historical_imports(tmp_path, monkeypatch):
    key = tmp_path / "key.pem"
    key.write_text("key", encoding="utf-8")
    (tmp_path / ".env").write_text("KALSHI_ENVIRONMENT=production\nKALSHI_API_KEY_ID=id\nKALSHI_PRIVATE_KEY_PATH=" + str(key) + "\n", encoding="utf-8")
    for name in ("KALSHI_ENVIRONMENT", "KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH"):
        monkeypatch.delenv(name, raising=False)
    key_id, key_path = kalshi_read_only_credentials(tmp_path)
    assert key_id == "id"
    assert key_path == key

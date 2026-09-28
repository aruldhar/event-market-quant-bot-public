"""Minimal Kalshi read-only credential boundary with no historical-data imports."""
from __future__ import annotations

import os
from pathlib import Path
import time


class SoakKalshiCredentialError(RuntimeError):
    pass


def kalshi_read_only_credentials(repo_root="."):
    path = Path(repo_root) / ".env"
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if "=" in raw and not raw.lstrip().startswith("#"):
                key, value = raw.split("=", 1)
                if key.strip() and key.strip() not in os.environ:
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
    if os.environ.get("KALSHI_ENVIRONMENT", "").strip().lower() not in {"production", "prod"}:
        raise SoakKalshiCredentialError("KALSHI_ENVIRONMENT must be production")
    key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
    key_path = Path(os.environ.get("KALSHI_PRIVATE_KEY_PATH", "").strip()).expanduser()
    if not key_id or not key_path.is_file():
        raise SoakKalshiCredentialError("Kalshi key ID/private-key path are not configured")
    return key_id, key_path


def create_kalshi_ws_headers(key_id, private_key_path):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    timestamp = str(int(time.time() * 1000))
    message = (timestamp + "GET/trade-api/ws/v2").encode("utf-8")
    private_key = serialization.load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
    signature = private_key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    import base64
    return {"KALSHI-ACCESS-KEY": str(key_id), "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii")}

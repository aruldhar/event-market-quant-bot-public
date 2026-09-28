"""Credential-boundary validation for Candidate-E raw-journal request metadata.

Raw source payloads must remain exact. This module only constrains local
request metadata so credentials, headers, signing material, cookies, or tokens
cannot be persisted through ``request_identity``.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any
from urllib.parse import urlsplit


ALLOWED_REQUEST_IDENTITY_FIELDS = frozenset({
    "method",
    "url",
    "params",
    "status_code",
    "elapsed_monotonic_ns",
    "channel",
    # Existing production-shaped Coinbase metadata. These are deliberately
    # explicit rather than opening request_identity to arbitrary fields.
    "phase",
    "latest_attempt_index",
    "cb_before",
    "cb_after",
    "product_id",
})

ALLOWED_COINBASE_RECOVERY_PHASES = frozenset({
    "latest_visibility",
    "older_pagination",
})
ALLOWED_COINBASE_PRODUCT_IDS = frozenset({
    "BTC-USD",
})

_SENSITIVE_KEY_TOKENS = (
    "authorization",
    "proxyauthorization",
    "cookie",
    "setcookie",
    "secret",
    "token",
    "signature",
    "privatekey",
    "apikey",
    "accesskey",
    "kalshiaccess",
)

_SENSITIVE_VALUE_MARKERS = (
    "bearer ",
    "kalshi-access-key",
    "kalshi-access-signature",
    "kalshi-access-timestamp",
    "private key-----",
)


class RawJournalSecurityError(ValueError):
    pass


def _normalize_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _reject_sensitive_key(key: str, path: str) -> None:
    normalized = _normalize_key(key)
    if any(token in normalized for token in _SENSITIVE_KEY_TOKENS):
        raise RawJournalSecurityError(
            f"{path} contains forbidden credential/header field {key!r}"
        )


def _validate_string(value: str, path: str) -> str:
    text = str(value)
    lowered = text.lower()
    if any(marker in lowered for marker in _SENSITIVE_VALUE_MARKERS):
        raise RawJournalSecurityError(
            f"{path} contains credential-like material"
        )
    return text


def _validate_optional_cursor(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RawJournalSecurityError(
            f"{path} must be a string or None"
        )
    text = _validate_string(value, path)
    if not text or len(text) > 2048:
        raise RawJournalSecurityError(
            f"{path} must be 1..2048 characters when present"
        )
    return text


def _sanitize_param_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RawJournalSecurityError(f"{path} must be finite")
        return value
    if isinstance(value, str):
        return _validate_string(value, path)
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_param_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str) or not raw_key:
                raise RawJournalSecurityError(
                    f"{path} keys must be non-empty strings"
                )
            _reject_sensitive_key(raw_key, path)
            out[raw_key] = _sanitize_param_value(
                raw_value,
                f"{path}.{raw_key}",
            )
        return out
    raise RawJournalSecurityError(
        f"{path} has unsupported metadata type {type(value).__name__}"
    )


def sanitize_request_identity(
    request_identity: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return JSON-safe request metadata after a fail-closed credential check.

    Only an explicit top-level field set is accepted. Unknown top-level fields
    are rejected instead of silently copied. Nested ``params`` keys are
    recursively checked for credential/header names. URLs must not contain a
    query string, fragment, or user-info; query parameters belong in ``params``.
    """
    if request_identity is None:
        return {}
    if not isinstance(request_identity, Mapping):
        raise RawJournalSecurityError(
            "request_identity must be a mapping or None"
        )

    out: dict[str, Any] = {}
    for raw_key, raw_value in request_identity.items():
        if not isinstance(raw_key, str) or not raw_key:
            raise RawJournalSecurityError(
                "request_identity keys must be non-empty strings"
            )
        _reject_sensitive_key(raw_key, "request_identity")
        if raw_key not in ALLOWED_REQUEST_IDENTITY_FIELDS:
            raise RawJournalSecurityError(
                f"request_identity field {raw_key!r} is not allowlisted"
            )

        if raw_key == "method":
            method = _validate_string(
                str(raw_value),
                "request_identity.method",
            ).upper()
            if method != "GET":
                raise RawJournalSecurityError(
                    "request_identity.method must be GET in read-only mode"
                )
            out[raw_key] = method
            continue

        if raw_key == "url":
            url = _validate_string(
                str(raw_value),
                "request_identity.url",
            )
            parsed = urlsplit(url)
            if parsed.scheme not in {"https", "wss"} or not parsed.netloc:
                raise RawJournalSecurityError(
                    "request_identity.url must be an absolute https/wss URL"
                )
            if parsed.username is not None or parsed.password is not None:
                raise RawJournalSecurityError(
                    "request_identity.url may not contain user-info"
                )
            if parsed.query or parsed.fragment:
                raise RawJournalSecurityError(
                    "request_identity.url may not contain query/fragment data"
                )
            out[raw_key] = url
            continue

        if raw_key == "params":
            if not isinstance(raw_value, Mapping):
                raise RawJournalSecurityError(
                    "request_identity.params must be a mapping"
                )
            out[raw_key] = _sanitize_param_value(
                raw_value,
                "request_identity.params",
            )
            continue

        if raw_key == "status_code":
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise RawJournalSecurityError(
                    "request_identity.status_code must be an integer"
                )
            if not 100 <= raw_value <= 599:
                raise RawJournalSecurityError(
                    "request_identity.status_code outside HTTP range"
                )
            out[raw_key] = raw_value
            continue

        if raw_key == "elapsed_monotonic_ns":
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise RawJournalSecurityError(
                    "request_identity.elapsed_monotonic_ns must be an integer"
                )
            if raw_value < 0:
                raise RawJournalSecurityError(
                    "request_identity.elapsed_monotonic_ns must be nonnegative"
                )
            out[raw_key] = raw_value
            continue

        if raw_key == "channel":
            channel = _validate_string(
                str(raw_value),
                "request_identity.channel",
            )
            if not channel or len(channel) > 128:
                raise RawJournalSecurityError(
                    "request_identity.channel must be 1..128 characters"
                )
            out[raw_key] = channel
            continue

        if raw_key == "phase":
            if not isinstance(raw_value, str):
                raise RawJournalSecurityError(
                    "request_identity.phase must be a string"
                )
            phase = _validate_string(
                raw_value,
                "request_identity.phase",
            )
            if phase not in ALLOWED_COINBASE_RECOVERY_PHASES:
                raise RawJournalSecurityError(
                    "request_identity.phase is not an allowed Coinbase recovery phase"
                )
            out[raw_key] = phase
            continue

        if raw_key == "latest_attempt_index":
            if raw_value is None:
                out[raw_key] = None
                continue
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise RawJournalSecurityError(
                    "request_identity.latest_attempt_index must be a positive integer or None"
                )
            if raw_value <= 0:
                raise RawJournalSecurityError(
                    "request_identity.latest_attempt_index must be positive when present"
                )
            out[raw_key] = raw_value
            continue

        if raw_key == "cb_before":
            out[raw_key] = _validate_optional_cursor(
                raw_value,
                "request_identity.cb_before",
            )
            continue

        if raw_key == "cb_after":
            out[raw_key] = _validate_optional_cursor(
                raw_value,
                "request_identity.cb_after",
            )
            continue

        if raw_key == "product_id":
            if not isinstance(raw_value, str):
                raise RawJournalSecurityError(
                    "request_identity.product_id must be a string"
                )
            product_id = _validate_string(
                raw_value,
                "request_identity.product_id",
            )
            if product_id not in ALLOWED_COINBASE_PRODUCT_IDS:
                raise RawJournalSecurityError(
                    "request_identity.product_id is not an allowed Coinbase product"
                )
            out[raw_key] = product_id
            continue

        raise AssertionError("unreachable allowlist branch")

    return out

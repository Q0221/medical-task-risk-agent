"""Minimal signed token helpers for API authentication.

The project currently has no password column or external IdP integration, so
we use an HMAC-signed bearer token without adding third-party dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings


class TokenError(ValueError):
    """Raised when a bearer token cannot be trusted."""


def create_access_token(
    *,
    user_id: int,
    role: str,
    role_codes: list[str],
    expires_in_minutes: int | None = None,
) -> tuple[str, int]:
    now = int(time.time())
    expires_at = now + int(
        (expires_in_minutes or settings.AUTH_TOKEN_EXPIRE_MINUTES) * 60
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "role_codes": role_codes,
        "iat": now,
        "exp": expires_at,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64_json(header)}.{_b64_json(payload)}"
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}", expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature = token.split(".", 2)
    except ValueError as exc:
        raise TokenError("invalid token format") from exc

    signing_input = f"{header_part}.{payload_part}"
    expected = _sign(signing_input)
    if not hmac.compare_digest(expected, signature):
        raise TokenError("invalid token signature")

    try:
        header = json.loads(_b64_decode(header_part))
        payload = json.loads(_b64_decode(payload_part))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("invalid token payload") from exc

    if header.get("alg") != "HS256":
        raise TokenError("unsupported token algorithm")

    exp = int(payload.get("exp") or 0)
    if exp <= int(time.time()):
        raise TokenError("token expired")
    if not payload.get("sub"):
        raise TokenError("token missing subject")
    return payload


def _sign(value: str) -> str:
    digest = hmac.new(
        settings.AUTH_SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64_bytes(digest)


def _b64_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _b64_bytes(raw)


def _b64_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")

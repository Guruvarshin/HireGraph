"""Signed-JWT authentication (HS256), implemented with the standard library so it
adds no dependency.

Why this exists: identity used to be an `X-Recruiter-ID` header the client set
freely - a spoofable, client-asserted tenant boundary (an IDOR: anyone could read
or delete another recruiter's pipelines by changing the header). Now the OAuth
callback mints a signed token; every protected route verifies the signature via
the `current_recruiter` dependency, so identity can't be forged without the
server-side secret.

A short-lived HS256 token carrying {sub: email, name} is enough here - the server
is the only issuer and verifier, so a symmetric secret is appropriate.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Header, HTTPException


# Stable secret across restarts (tokens must survive a reload). Set JWT_SECRET in
# production; the dev default keeps local runs working with zero config.
_SECRET = os.getenv("JWT_SECRET") or "dev-insecure-secret-change-me"
_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days

# Emergency/dev escape hatch: when "true", requests with no valid Bearer token may
# fall back to the legacy X-Recruiter-ID header. DEFAULT OFF so the spoofing hole
# is closed. Only enable for local dev or as a demo safety net.
_DEV_FALLBACK = os.getenv("AUTH_DEV_FALLBACK", "false").lower() == "true"


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def _sign(signing_input: bytes) -> str:
    sig = hmac.new(_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_access_token(email: str, name: str = "") -> str:
    """Mint a signed token for a recruiter identity."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": email.lower().strip(),
        "name": name,
        "iat": now,
        "exp": now + _TTL_SECONDS,
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    return f"{h}.{p}.{_sign(signing_input)}"


def decode_token(token: str) -> dict:
    """Verify signature + expiry and return the payload, or raise ValueError."""
    try:
        h, p, sig = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")

    expected = _sign(f"{h}.{p}".encode())
    # Constant-time comparison to avoid timing attacks on the signature.
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Bad signature")

    payload = json.loads(_b64url_decode(p))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    if not payload.get("sub"):
        raise ValueError("Token missing subject")
    return payload


def _identity_from(authorization: str | None, x_recruiter_id: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        try:
            return decode_token(token)["sub"]
        except ValueError:
            return None  # invalid token: fall through to (disabled) fallback / 401
    if _DEV_FALLBACK and x_recruiter_id:
        return x_recruiter_id.lower().strip()
    return None


# ---- FastAPI dependencies -------------------------------------------------

def current_recruiter(
    authorization: str | None = Header(None),
    x_recruiter_id: str | None = Header(None, alias="X-Recruiter-ID"),
) -> str:
    """Require a valid identity; 401 otherwise. Returns the recruiter's email."""
    identity = _identity_from(authorization, x_recruiter_id)
    if not identity:
        raise HTTPException(status_code=401, detail="Authentication required (missing or invalid token).")
    return identity


def current_recruiter_optional(
    authorization: str | None = Header(None),
    x_recruiter_id: str | None = Header(None, alias="X-Recruiter-ID"),
) -> str | None:
    """Return the identity if present/valid, else None (never raises)."""
    return _identity_from(authorization, x_recruiter_id)

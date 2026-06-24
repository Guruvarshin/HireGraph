from __future__ import annotations

import os
import secrets
import urllib.parse
from datetime import datetime, timezone

import requests as http_requests
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from memory.database import (
    save_google_tokens,
    get_google_tokens,
    delete_google_tokens,
    save_recruiter_profile,
    get_recruiter_profile,
)

router = APIRouter()

_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
_FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Sign-in only: non-sensitive scopes that require no Google verification.
_SCOPES = " ".join([
    "openid",
    "email",
    "profile",
])

_AUTH_URI      = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URI     = "https://oauth2.googleapis.com/token"
_USERINFO_URI  = "https://www.googleapis.com/oauth2/v3/userinfo"


@router.get("/google")
def auth_google():
    if not _CLIENT_ID or not _CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env",
        )

    params = {
        "client_id":     _CLIENT_ID,
        "redirect_uri":  _REDIRECT_URI,
        "response_type": "code",
        "scope":         _SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         secrets.token_urlsafe(16),  # CSRF protection only
    }
    return RedirectResponse(url=_AUTH_URI + "?" + urllib.parse.urlencode(params), status_code=302)


@router.get("/google/callback")
def auth_google_callback(request: Request):
    code  = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/setup?auth_error={urllib.parse.quote(error)}",
            status_code=302,
        )
    if not code:
        raise HTTPException(status_code=400, detail="Missing code in OAuth callback.")

    # Exchange code for tokens
    resp = http_requests.post(
        _TOKEN_URI,
        data={
            "code":          code,
            "client_id":     _CLIENT_ID,
            "client_secret": _CLIENT_SECRET,
            "redirect_uri":  _REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        timeout=10,
    )
    token_data = resp.json()
    if not resp.ok or "access_token" not in token_data:
        err = token_data.get("error_description") or token_data.get("error") or str(token_data)
        raise HTTPException(status_code=400, detail=f"Google token exchange failed: {err}")

    access_token = token_data["access_token"]

    # Fetch the user's email from Google
    ui_resp = http_requests.get(
        _USERINFO_URI,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if not ui_resp.ok:
        raise HTTPException(status_code=400, detail="Could not fetch user info from Google.")

    user_info = ui_resp.json()
    email      = user_info.get("email", "").lower().strip()
    given_name = user_info.get("given_name", "") or user_info.get("name", "")

    if not email:
        raise HTTPException(status_code=400, detail="Google did not return an email address.")

    # Calculate expiry
    expires_in = token_data.get("expires_in", 3600)
    expiry_iso = datetime.fromtimestamp(
        datetime.utcnow().timestamp() + expires_in, tz=timezone.utc
    ).isoformat()

    # Store token keyed by email
    save_google_tokens(
        user_id=email,
        token_data={
            "access_token":  access_token,
            "refresh_token": token_data.get("refresh_token"),
            "token_expiry":  expiry_iso,
        },
    )

    # Seed recruiter profile with Google name if not already set
    existing = get_recruiter_profile(email)
    if not existing:
        save_recruiter_profile(email=email, name=given_name, role="")

    # Redirect with email so the frontend can store it as its identity
    redirect_url = (
        f"{_FRONTEND_URL}/setup"
        f"?auth_success=true"
        f"&user_email={urllib.parse.quote(email)}"
        f"&user_name={urllib.parse.quote(given_name)}"
    )
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/status")
def auth_status(
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):
    token = get_google_tokens(user_id=x_recruiter_id)
    if not token:
        return {"authenticated": False}
    profile = get_recruiter_profile(x_recruiter_id) or {}
    return {
        "authenticated": True,
        "email":  x_recruiter_id,
        "name":   profile.get("name", token.get("recruiter_name", "")),
        "role":   profile.get("role", token.get("recruiter_role", "")),
    }


@router.patch("/profile")
def update_profile(
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
    name: str = Query(...),
    role: str = Query(...),
):
    save_recruiter_profile(email=x_recruiter_id, name=name.strip(), role=role.strip())
    return {"name": name.strip(), "role": role.strip()}


@router.delete("/logout")
def auth_logout(
    x_recruiter_id: str = Header(..., alias="X-Recruiter-ID"),
):
    delete_google_tokens(user_id=x_recruiter_id)
    return {"message": "Google account disconnected."}

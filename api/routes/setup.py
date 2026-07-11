from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from utils.jwt_auth import current_recruiter

router = APIRouter()


def _check_mongodb() -> dict:
    try:
        from memory.database import get_client
        client = get_client()

        client.admin.command("ping")
        return {"ok": True, "message": "Connected"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _check_pinecone() -> dict:
    try:
        from pinecone import Pinecone
        index_name = os.getenv("PINECONE_INDEX_NAME", "recruiting-pipeline")
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY", ""))
        existing = [i.name for i in pc.list_indexes()]
        if index_name in existing:
            return {"ok": True, "message": f"Index '{index_name}' found"}
        return {
            "ok": False,
            "message": (
                f"Index '{index_name}' not found. "
                "Run: python scripts/setup.py to create it."
            ),
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _check_openai() -> dict:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

        client.models.list()
        model = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o")
        return {"ok": True, "message": f"API key valid, agent model: {model}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _check_google(user_id: str) -> dict:
    try:
        from memory.database import get_google_tokens
        token = get_google_tokens(user_id=user_id)
        if token:
            expiry = token.get("token_expiry", "unknown")
            return {
                "ok": True,
                "message": f"Gmail connected. Token expiry: {expiry}",
            }
        return {
            "ok": False,
            "message": "Not connected. Visit /auth/google to authenticate.",
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@router.get("/status")
def setup_status(
    x_recruiter_id: str = Depends(current_recruiter),
):


    mongodb  = _check_mongodb()
    pinecone = _check_pinecone()
    openai   = _check_openai()
    google   = _check_google(user_id=x_recruiter_id)

    all_ok = all([
        mongodb["ok"],
        pinecone["ok"],
        openai["ok"],
        google["ok"],
    ])

    return {
        "mongodb":  mongodb,
        "pinecone": pinecone,
        "openai":   openai,
        "google":   google,
        "all_ok":   all_ok,
    }

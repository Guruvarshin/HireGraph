from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

load_dotenv()


_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            os.getenv("MONGODB_URI"),
            serverSelectionTimeoutMS=5000,
        )
    return _client


def get_db():
    return get_client()[os.getenv("MONGODB_DB_NAME", "recruiting_pipeline")]


def ensure_indexes() -> None:
    db = get_db()

    try:
        db["pipeline_runs"].drop_indexes()
    except:
        pass

    db["pipeline_runs"].create_index(
        [("thread_id", ASCENDING)], unique=True
    )
    db["pipeline_runs"].create_index(
        [("user_id", ASCENDING)]
    )
    db["pipeline_runs"].create_index(
        [("user_id", ASCENDING), ("created_at", ASCENDING)]
    )

    try:
        db["google_tokens"].drop_indexes()
    except:
        pass

    db["google_tokens"].create_index(
        [("user_id", ASCENDING)], unique=True
    )

    try:
        db["recruiters"].drop_indexes()
    except:
        pass

    db["recruiters"].create_index([("email", ASCENDING)], unique=True)

    try:
        db["lg_checkpoints"].drop_indexes()
    except:
        pass

    db["lg_checkpoints"].create_index(
        [("thread_id", ASCENDING)]
    )


def _runs() -> Collection:
    return get_db()["pipeline_runs"]


def create_pipeline_run(
    thread_id: str,
    user_id: str,
    jd_title: str = "Untitled Role",
) -> str:
    now = datetime.utcnow().isoformat()
    doc = {
        "thread_id":          thread_id,
        "user_id":            user_id,
        "status":             "pending",
        "current_stage":      "jd_parsing",
        "error_message":      None,
        "jd_title":           jd_title,
        "job_description":    None,
        "candidates":         [],
        "shortlist":          [],
        "interview_plans":    [],
        "interview_feedback": [],
        "evaluations":        [],
        "offer_drafts":       [],
        "created_at":         now,
        "updated_at":         now,
    }
    try:
        _runs().insert_one(doc)
    except DuplicateKeyError:
        pass
    return thread_id


def get_pipeline_run(thread_id: str) -> Optional[dict]:
    doc = _runs().find_one({"thread_id": thread_id}, {"_id": 0})
    return doc


def update_pipeline_run(thread_id: str, updates: dict) -> None:
    updates["updated_at"] = datetime.utcnow().isoformat()
    _runs().update_one(
        {"thread_id": thread_id},
        {"$set": updates},
    )


def list_pipeline_runs(user_id: str) -> list[dict]:
    cursor = _runs().find(
        {"user_id": user_id},
        {
            "_id":            0,
            "thread_id":      1,
            "jd_title":       1,
            "status":         1,
            "current_stage":  1,
            "shortlist_count": 1,
            "created_at":     1,
            "updated_at":     1,
        },
    ).sort("created_at", ASCENDING)
    return list(cursor)


def delete_pipeline_run(thread_id: str) -> None:
    """Delete a pipeline run and its LangGraph checkpoints (full cleanup)."""
    db = get_db()
    db["pipeline_runs"].delete_one({"thread_id": thread_id})
    # Remove the authoritative graph state so no orphaned checkpoints remain.
    for coll in ("lg_checkpoints", "lg_checkpoint_writes"):
        try:
            db[coll].delete_many({"thread_id": thread_id})
        except Exception:
            pass


def mark_pipeline_failed(thread_id: str, error_message: str) -> None:
    update_pipeline_run(thread_id, {
        "status":        "failed",
        "error_message": error_message,
    })


def mark_pipeline_completed(thread_id: str) -> None:
    update_pipeline_run(thread_id, {
        "status":        "completed",
        "current_stage": "completed",
    })


def _tokens() -> Collection:
    return get_db()["google_tokens"]


def _recruiters() -> Collection:
    return get_db()["recruiters"]


def save_google_tokens(user_id: str, token_data: dict) -> None:
    token_data["user_id"]    = user_id
    token_data["updated_at"] = datetime.utcnow().isoformat()
    _tokens().update_one(
        {"user_id": user_id},
        {"$set": token_data},
        upsert=True,
    )


def get_google_tokens(user_id: str) -> Optional[dict]:
    return _tokens().find_one({"user_id": user_id}, {"_id": 0})


def delete_google_tokens(user_id: str) -> None:
    _tokens().delete_one({"user_id": user_id})


def save_recruiter_profile(email: str, name: str, role: str) -> None:
    now = datetime.utcnow().isoformat()
    _recruiters().update_one(
        {"email": email},
        {"$set": {"email": email, "name": name, "role": role, "updated_at": now}},
        upsert=True,
    )


def get_recruiter_profile(email: str) -> Optional[dict]:
    return _recruiters().find_one({"email": email}, {"_id": 0})

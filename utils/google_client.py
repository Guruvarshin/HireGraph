from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from memory.database import get_db


_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_TOKEN_URI     = "https://oauth2.googleapis.com/token"

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

_TOKENS_COLLECTION = "google_tokens"


def _naive_utc(iso_str: str) -> datetime:
    """Parse an ISO datetime string → offset-naive UTC datetime.
    google-auth compares expiry with datetime.utcnow() which is offset-naive,
    so we must strip tzinfo after converting to UTC.
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _get_credentials(user_id: str) -> Credentials:
    db = get_db()
    token_record = db[_TOKENS_COLLECTION].find_one({"user_id": user_id}, {"_id": 0})

    if not token_record:
        raise ValueError(
            f"No Google token found for user '{user_id}'. "
            "Complete Google OAuth on the setup page first."
        )

    creds = Credentials(
        token=token_record.get("access_token"),
        refresh_token=token_record.get("refresh_token"),
        token_uri=_TOKEN_URI,
        client_id=_CLIENT_ID,
        client_secret=_CLIENT_SECRET,
        scopes=_SCOPES,
    )

    expiry_str = token_record.get("token_expiry")
    if expiry_str:
        try:
            creds.expiry = _naive_utc(expiry_str)
        except Exception:
            pass

    if not creds.valid:
        if creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to refresh Google token for user '{user_id}': {exc}. "
                    "Re-authenticate on the setup page."
                ) from exc

            db[_TOKENS_COLLECTION].update_one(
                {"user_id": user_id},
                {"$set": {
                    "access_token": creds.token,
                    "token_expiry": (
                        creds.expiry.isoformat() if creds.expiry else None
                    ),
                }},
            )
        else:
            raise RuntimeError(
                f"Google token for user '{user_id}' is expired and no refresh token "
                "is available. Re-authenticate on the setup page."
            )

    return creds


def _gmail_service(user_id: str):
    return build("gmail", "v1", credentials=_get_credentials(user_id))


def _calendar_service(user_id: str):
    return build("calendar", "v3", credentials=_get_credentials(user_id))


def _build_raw_email(to_email: str, subject: str, body_html: str) -> str:
    msg = MIMEMultipart("alternative")
    msg["To"]      = to_email
    msg["Subject"] = subject

    plain = (body_html
             .replace("<br>", "\n").replace("<br/>", "\n")
             .replace("<p>", "\n").replace("</p>", "")
             .replace("<li>", "• ").replace("</li>", "\n")
             .replace("<strong>", "").replace("</strong>", "")
             .replace("<ul>", "").replace("</ul>", ""))
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")


def _gmail_send(user_id: str, to_email: str, subject: str, body_html: str) -> str:
    raw = _build_raw_email(to_email, subject, body_html)
    try:
        result = _gmail_service(user_id).users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"Gmail send failed → {to_email}: {exc}") from exc
    return result.get("id", "")


def send_offer_email(
    user_id: str,
    to_email: str,
    candidate_name: str,
    offer_letter_text: str,
) -> str:
    body_html = offer_letter_text.replace("\n", "<br>")
    return _gmail_send(user_id, to_email, f"Job Offer — {candidate_name}", body_html)


def send_interview_invite(
    user_id: str,
    to_email: str,
    candidate_name: str,
    job_title: str,
    rounds: list[dict],
) -> str:
    rounds_html = "".join(
        f"<li><strong>Round {r.get('round_number')}: "
        f"{r.get('type', 'interview').replace('_', ' ').title()}</strong> "
        f"({r.get('duration_minutes', 60)} min)"
        + (f" — {r.get('scheduled_at')}" if r.get("scheduled_at") else "")
        + "</li>"
        for r in rounds
    )

    body_html = f"""
<p>Dear {candidate_name},</p>
<p>We are pleased to invite you to interview for the <strong>{job_title}</strong> role.</p>
<p>Your interview process consists of the following rounds:</p>
<ul>{rounds_html}</ul>
<p>You will receive a separate calendar invite for each round. Please let us know if you have any questions.</p>
<p>Best regards,<br>The Hiring Team</p>
"""
    return _gmail_send(user_id, to_email, f"Interview Invitation — {job_title}", body_html)


def create_calendar_event(
    user_id: str,
    summary: str,
    description: str,
    start_iso: str,
    end_iso: str,
    attendee_emails: list[str],
) -> str:
    service = _calendar_service(user_id)

    event_body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": "UTC"},
        "end":   {"dateTime": end_iso,   "timeZone": "UTC"},
        "attendees": [{"email": e} for e in attendee_emails if e],
        "reminders": {"useDefault": True},
    }

    try:
        result = service.events().insert(
            calendarId="primary",
            body=event_body,
            sendUpdates="all",
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"Calendar event creation failed: {exc}") from exc

    return result.get("id", "")

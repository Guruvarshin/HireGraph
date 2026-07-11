from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests

# Sends email through the Brevo HTTP API (HTTPS), since cloud hosts commonly
# block outbound SMTP ports. GMAIL_ADDRESS must be a verified Brevo sender.
_BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
_SENDER_EMAIL  = os.getenv("GMAIL_ADDRESS", "")
_SENDER_NAME   = os.getenv("EMAIL_SENDER_NAME", "HireGraph")
_BREVO_URL     = "https://api.brevo.com/v3/smtp/email"


def _send_email(
    to_email: str,
    subject: str,
    body_html: str,
    reply_to: str = "",
    ics_attachments: list[tuple[str, str]] | None = None,
) -> str:
    if not _BREVO_API_KEY:
        raise RuntimeError(
            "BREVO_API_KEY is not set. Sign up at brevo.com, verify your sender "
            "email, create an API key, and set BREVO_API_KEY in the environment."
        )
    if not _SENDER_EMAIL:
        raise RuntimeError("GMAIL_ADDRESS (used as the verified Brevo sender) is not set.")

    payload: dict = {
        "sender":      {"name": _SENDER_NAME, "email": _SENDER_EMAIL},
        "to":          [{"email": to_email}],
        "subject":     subject,
        "htmlContent": body_html,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}

    # .ics calendar attachments - Brevo wants base64 content + filename
    attachments = []
    for filename, ics_text in (ics_attachments or []):
        encoded = base64.b64encode(ics_text.encode("utf-8")).decode("utf-8")
        attachments.append({"name": filename, "content": encoded})
    if attachments:
        payload["attachment"] = attachments

    try:
        resp = requests.post(
            _BREVO_URL,
            json=payload,
            headers={
                "api-key":      _BREVO_API_KEY,
                "content-type": "application/json",
                "accept":       "application/json",
            },
            timeout=30,
        )
    except Exception as exc:
        raise RuntimeError(f"Email send failed -> {to_email}: {exc}") from exc

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Email send failed -> {to_email}: HTTP {resp.status_code} {resp.text}"
        )

    try:
        return resp.json().get("messageId", "")
    except Exception:
        return ""


def _ics_dt(dt: datetime) -> str:
    """Format a datetime as an iCalendar UTC timestamp (YYYYMMDDTHHMMSSZ)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _build_ics(
    summary: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    organizer_email: str,
    attendee_emails: list[str],
) -> str:
    """Build a minimal RFC 5545 VEVENT that any calendar app can import."""
    attendee_lines = "\r\n".join(
        f"ATTENDEE;ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{e}"
        for e in attendee_emails if e
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HireGraph//Recruiting//EN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@hiregraph",
        f"DTSTAMP:{_ics_dt(datetime.now(timezone.utc))}",
        f"DTSTART:{_ics_dt(start_dt)}",
        f"DTEND:{_ics_dt(end_dt)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"ORGANIZER:mailto:{organizer_email}" if organizer_email else "",
        attendee_lines,
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(l for l in lines if l)


def send_offer_email(
    user_id: str,
    to_email: str,
    candidate_name: str,
    offer_letter_text: str,
) -> str:
    body_html = offer_letter_text.replace("\n", "<br>")
    return _send_email(
        to_email=to_email,
        subject=f"Job Offer - {candidate_name}",
        body_html=body_html,
        reply_to=user_id,
    )


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
        + (f" - {r.get('scheduled_at')}" if r.get("scheduled_at") else "")
        + "</li>"
        for r in rounds
    )

    body_html = f"""
<p>Dear {candidate_name},</p>
<p>We are pleased to invite you to interview for the <strong>{job_title}</strong> role.</p>
<p>Your interview process consists of the following rounds:</p>
<ul>{rounds_html}</ul>
<p>Calendar invites for each scheduled round are attached - open them to add the
events to your calendar. Please reply to this email with any questions.</p>
<p>Best regards,<br>The Hiring Team</p>
"""

    # One .ics attachment per round that has a real scheduled time.
    ics_attachments: list[tuple[str, str]] = []
    for r in rounds:
        scheduled_at = r.get("scheduled_at")
        if not scheduled_at or scheduled_at == "TBD":
            continue
        try:
            start_dt = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
        except Exception:
            continue

        duration = r.get("duration_minutes", 60)
        end_dt = start_dt + timedelta(minutes=duration)
        round_type = r.get("type", "interview").replace("_", " ").title()
        round_no = r.get("round_number", "")

        ics = _build_ics(
            summary=f"{round_type} Interview - {candidate_name} ({job_title})",
            description=f"Round {round_no}: {round_type} interview for {job_title}.",
            start_dt=start_dt,
            end_dt=end_dt,
            organizer_email=user_id,
            attendee_emails=[to_email] + r.get("interviewer_emails", []),
        )
        ics_attachments.append((f"interview_round_{round_no}.ics", ics))

    result = _send_email(
        to_email=to_email,
        subject=f"Interview Invitation - {job_title}",
        body_html=body_html,
        reply_to=user_id,
        ics_attachments=ics_attachments or None,
    )

    # Also email each interviewer. They are attendees inside the .ics, but a .ics
    # attachment does not deliver an invite on its own (no calendar server sends
    # it), so we send them the same attachments directly.
    interviewer_emails = sorted({
        e for r in rounds for e in r.get("interviewer_emails", []) if e
    })
    interviewer_body = f"""
<p>Hello,</p>
<p>You are scheduled to interview <strong>{candidate_name}</strong> for the
<strong>{job_title}</strong> role. The rounds are:</p>
<ul>{rounds_html}</ul>
<p>Calendar invites for each scheduled round are attached - open them to add the
events to your calendar.</p>
<p>Best regards,<br>The Hiring Team</p>
"""
    for iv in interviewer_emails:
        try:
            _send_email(
                to_email=iv,
                subject=f"Interview to conduct - {candidate_name} ({job_title})",
                body_html=interviewer_body,
                reply_to=user_id,
                ics_attachments=ics_attachments or None,
            )
        except Exception:
            pass   # one interviewer failing must not block the others

    return result

from __future__ import annotations

import os
import smtplib
import socket
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

# Gmail SMTP — uses an App Password (not OAuth), so it needs NO Google
# verification, no consent screen, and can email any recipient for free.
# Enable 2-Step Verification on the account, then create an App Password:
#   https://myaccount.google.com/apppasswords
_GMAIL_ADDRESS      = os.getenv("GMAIL_ADDRESS", "")
_GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
_SMTP_HOST          = "smtp.gmail.com"
_SMTP_PORT          = 587
_SMTP_SSL_PORT      = 465


def _smtp_connect() -> smtplib.SMTP:
    """Open an authenticated Gmail SMTP connection, forcing IPv4.

    Many cloud hosts (Railway/Render containers) have broken IPv6 egress, which
    makes smtplib raise '[Errno 101] Network is unreachable' when Gmail's DNS
    resolves to an IPv6 address. Resolving to IPv4 ourselves avoids that. We try
    STARTTLS on 587 first, then implicit SSL on 465 as a fallback.
    """
    def _ipv4(host: str) -> str:
        return socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]

    ipv4 = _ipv4(_SMTP_HOST)
    last_exc: Exception | None = None

    # Attempt 1: STARTTLS on 587
    try:
        server = smtplib.SMTP(timeout=30)
        server.connect(ipv4, _SMTP_PORT)
        server._host = _SMTP_HOST            # keep hostname for TLS cert verification
        server.starttls(context=ssl.create_default_context())
        server.login(_GMAIL_ADDRESS, _GMAIL_APP_PASSWORD)
        return server
    except Exception as exc:
        last_exc = exc

    # Attempt 2: implicit SSL on 465
    try:
        server = smtplib.SMTP_SSL(timeout=30, context=ssl.create_default_context())
        server._host = _SMTP_HOST
        server.connect(ipv4, _SMTP_SSL_PORT)
        server.login(_GMAIL_ADDRESS, _GMAIL_APP_PASSWORD)
        return server
    except Exception as exc:
        last_exc = exc

    raise RuntimeError(
        f"Could not open Gmail SMTP connection (tried 587 STARTTLS and 465 SSL): {last_exc}. "
        "If this is a deployed host, it may block outbound SMTP ports — use an HTTP email API instead."
    ) from last_exc


def _send_email(
    to_email: str,
    subject: str,
    body_html: str,
    reply_to: str = "",
    ics_attachments: list[tuple[str, str]] | None = None,
) -> str:
    if not _GMAIL_ADDRESS or not _GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env. "
            "Generate an App Password at https://myaccount.google.com/apppasswords"
        )

    msg = MIMEMultipart("mixed")
    msg["From"]    = _GMAIL_ADDRESS
    msg["To"]      = to_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to

    # Body: plain-text + HTML alternative
    alt = MIMEMultipart("alternative")
    plain = (body_html
             .replace("<br>", "\n").replace("<br/>", "\n")
             .replace("<p>", "\n").replace("</p>", "")
             .replace("<li>", "• ").replace("</li>", "\n")
             .replace("<strong>", "").replace("</strong>", "")
             .replace("<ul>", "").replace("</ul>", ""))
    alt.attach(MIMEText(plain, "plain"))
    alt.attach(MIMEText(body_html, "html"))
    msg.attach(alt)

    # .ics calendar attachments
    for filename, ics_text in (ics_attachments or []):
        part = MIMEBase("text", "calendar", method="REQUEST", name=filename)
        part.set_payload(ics_text)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)

    try:
        server = _smtp_connect()
        try:
            server.sendmail(_GMAIL_ADDRESS, [to_email], msg.as_string())
        finally:
            try:
                server.quit()
            except Exception:
                pass
    except Exception as exc:
        raise RuntimeError(f"Gmail SMTP send failed → {to_email}: {exc}") from exc

    return msg["Subject"]


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
        subject=f"Job Offer — {candidate_name}",
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
        + (f" — {r.get('scheduled_at')}" if r.get("scheduled_at") else "")
        + "</li>"
        for r in rounds
    )

    body_html = f"""
<p>Dear {candidate_name},</p>
<p>We are pleased to invite you to interview for the <strong>{job_title}</strong> role.</p>
<p>Your interview process consists of the following rounds:</p>
<ul>{rounds_html}</ul>
<p>Calendar invites for each scheduled round are attached — open them to add the
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
            summary=f"{round_type} Interview — {candidate_name} ({job_title})",
            description=f"Round {round_no}: {round_type} interview for {job_title}.",
            start_dt=start_dt,
            end_dt=end_dt,
            organizer_email=user_id,
            attendee_emails=[to_email] + r.get("interviewer_emails", []),
        )
        ics_attachments.append((f"interview_round_{round_no}.ics", ics))

    return _send_email(
        to_email=to_email,
        subject=f"Interview Invitation — {job_title}",
        body_html=body_html,
        reply_to=user_id,
        ics_attachments=ics_attachments or None,
    )

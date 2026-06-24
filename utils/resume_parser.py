from __future__ import annotations

import io
import json
import os
import re

from fastapi import UploadFile


async def extract_resume_text(file: UploadFile) -> tuple[str, str, str]:
    """
    Returns (clean_text, candidate_name, candidate_email).
    Mechanically extracts raw text then uses gpt-4o-mini to clean it
    and pull out the candidate's name and email.
    """
    content = await file.read()
    filename = (file.filename or "").lower()

    raw_text = _mechanical_extract(content, filename)
    if not raw_text.strip():
        raise ValueError(f"Could not extract any text from {file.filename}")

    return _ai_parse(raw_text, file.filename or "")


def _mechanical_extract(content: bytes, filename: str) -> str:
    if filename.endswith(".pdf"):
        return _extract_pdf(content)
    elif filename.endswith(".docx"):
        return _extract_docx(content)
    # Fallback: try PDF then DOCX then raw UTF-8
    for fn in [_extract_pdf, _extract_docx]:
        try:
            text = fn(content)
            if text.strip():
                return text
        except Exception:
            pass
    return content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(
        page.extract_text() or "" for page in reader.pages
    ).strip()


def _extract_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


_PARSE_PROMPT = """\
You are a resume parser. The user will provide raw text extracted from a resume (possibly messy due to PDF formatting).

Your job:
1. Clean up the text - fix broken words, remove duplicate whitespace, restore logical reading order.
2. Extract the candidate's full name and email address.

Return ONLY valid JSON with exactly this structure:
{
  "name": "<candidate full name or null if not found>",
  "email": "<candidate email address or null if not found>",
  "clean_text": "<the full resume text, cleaned and readable, preserving all information>"
}

Rules:
- clean_text must contain the FULL resume content - do not summarise or truncate.
- Preserve all job titles, dates, skills, education, and achievements.
- name and email may be null if genuinely not present in the text.
"""


def _ai_parse(raw_text: str, filename: str) -> tuple[str, str, str]:
    """Use gpt-4o-mini to clean the resume text and extract name/email."""
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Truncate very long resumes to avoid token waste (keep first 6000 chars)
    truncated = raw_text[:6000]

    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_PARSER_MODEL", "gpt-4o-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _PARSE_PROMPT},
                {"role": "user", "content": f"RESUME (from file: {filename}):\n\n{truncated}"},
            ],
        )
        parsed = json.loads(response.choices[0].message.content)
    except Exception:
        # If AI fails, fall back to raw text + filename-derived name
        name = _name_from_filename(filename)
        return raw_text, name, ""

    clean_text = parsed.get("clean_text") or raw_text
    name = parsed.get("name") or _name_from_filename(filename)
    email = parsed.get("email") or ""

    # Validate email looks real
    if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        email = ""

    return clean_text, name, email


def _name_from_filename(filename: str) -> str:
    """e.g. 'john_doe_resume.pdf' -> 'john doe resume'"""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return stem.replace("_", " ").replace("-", " ").strip() or filename

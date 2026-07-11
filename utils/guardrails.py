from __future__ import annotations
import os
import time

from utils.tracing import traceable

_MAX_ATTEMPTS = 3   # retry transient errors (throttling/timeout) before failing closed

_GUARDRAIL_ID      = os.getenv("BEDROCK_GUARDRAIL_ID", "")
_GUARDRAIL_VERSION = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
_AWS_REGION        = os.getenv("AWS_REGION", "us-east-1")
_REQUIRED          = os.getenv("GUARDRAIL_REQUIRED", "false").lower() in ("1", "true", "yes")

_OFF = {"text": None, "blocked": False, "injection_detected": False, "pii_redacted": False, "enabled": False}


def is_enabled() -> bool:
    return bool(_GUARDRAIL_ID)


@traceable(name="Guardrail: AWS Bedrock screen", run_type="tool")
def apply_guardrail(text: str, source: str = "INPUT") -> dict:
    if not _GUARDRAIL_ID:
        if _REQUIRED:
            raise RuntimeError(
                "GUARDRAIL_REQUIRED is set but BEDROCK_GUARDRAIL_ID is not configured. "
                "Resume screening is mandatory; refusing to process unscreened input."
            )
        return {**_OFF, "text": text}

    if not text.strip():
        return {**_OFF, "text": text}

    try:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=_AWS_REGION)
    except Exception as exc:
        if _REQUIRED:
            raise RuntimeError(f"Mandatory guardrail unavailable (boto3/client): {exc}") from exc
        return {**_OFF, "text": text}

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = client.apply_guardrail(
                guardrailIdentifier=_GUARDRAIL_ID,
                guardrailVersion=_GUARDRAIL_VERSION,
                source=source,                       # "INPUT" = user-supplied content
                content=[{"text": {"text": text}}],
            )
            outputs = resp.get("outputs", [])
            cleaned = outputs[0]["text"] if outputs and outputs[0].get("text") else text
            assessments = resp.get("assessments", [])
            blocked = _is_blocked(assessments)
            return {
                "text": cleaned,
                "blocked": blocked,
                "injection_detected": blocked or _has_injection(assessments),
                "pii_redacted": _has_pii(assessments),
                "enabled": True,
            }
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(0.5 * (attempt + 1))   # 0.5s then 1.0s backoff

    if _REQUIRED:
        # Fail closed: do not process a resume we could not screen.
        raise RuntimeError(
            f"Mandatory guardrail screening failed after {_MAX_ATTEMPTS} attempts: {last_exc}"
        ) from last_exc
    return {**_OFF, "text": text}


def _is_blocked(assessments: list) -> bool:
    for a in assessments:
        for f in a.get("contentPolicy", {}).get("filters", []):
            if f.get("action") == "BLOCKED":
                return True
        for t in a.get("topicPolicy", {}).get("topics", []):
            if t.get("action") == "BLOCKED":
                return True
        for w in a.get("wordPolicy", {}).get("customWords", []):
            if w.get("action") == "BLOCKED":
                return True
    return False


def _has_injection(assessments: list) -> bool:
    for a in assessments:
        for f in a.get("contentPolicy", {}).get("filters", []):
            if f.get("type") == "PROMPT_ATTACK" and f.get("action") in ("BLOCKED", "ANONYMIZED"):
                return True
    return False


def _has_pii(assessments: list) -> bool:
    for a in assessments:
        sip = a.get("sensitiveInformationPolicy", {})
        if sip.get("piiEntities") or sip.get("regexes"):
            return True
    return False

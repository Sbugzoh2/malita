"""
Malita (Pty) Ltd — minimal outbound email via SMTP.

No third-party email service dependency — just plain smtplib against
whatever SMTP credentials are configured. If none are set (the common case
until you set one up), send_email() simply returns False so callers can
fall back to showing the content directly in the UI instead of failing.

Configure via environment variables:
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD
  SMTP_FROM (optional, defaults to SMTP_USER)

On Streamlit Cloud, values entered under "Secrets" are normally mirrored
into os.environ automatically, but that mirroring has been inconsistent
across Streamlit versions for some deployments — so as a fallback, this
module also reads st.secrets directly when os.environ doesn't have a value
and streamlit happens to be importable (it won't be when this runs under
api_server.py/FastAPI, which is fine — that path just relies on os.environ).
"""

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger("malita.email")


def _get_setting(key: str) -> str | None:
    value = os.environ.get(key)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(key)
    except Exception:
        return None


def is_email_configured() -> bool:
    return bool(_get_setting("SMTP_HOST") and _get_setting("SMTP_USER") and _get_setting("SMTP_PASSWORD"))


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Best-effort send — returns True only on confirmed success. Any
    misconfiguration or SMTP error is swallowed (never crashes the caller,
    since the caller always has a UI fallback for the "not sent" case) but
    is logged, so the actual cause is visible in the app's server logs
    instead of only ever showing the generic "not sent" fallback."""
    host = _get_setting("SMTP_HOST")
    user = _get_setting("SMTP_USER")
    password = _get_setting("SMTP_PASSWORD")

    if not (host and user and password):
        missing = [name for name, value in [("SMTP_HOST", host), ("SMTP_USER", user), ("SMTP_PASSWORD", password)] if not value]
        logger.warning("send_email: not configured, missing %s", ", ".join(missing))
        return False

    port = int(_get_setting("SMTP_PORT") or "587")
    from_addr = _get_setting("SMTP_FROM") or user

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return True
    except Exception:
        logger.exception("send_email: failed sending to %s via %s:%s", to_email, host, port)
        return False

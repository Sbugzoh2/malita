"""
Malita (Pty) Ltd — outbound email, via Brevo's HTTP API or plain SMTP.

Render blocks outbound SMTP connections (ports 25/465/587) on its
infrastructure - smtplib there fails with "OSError: [Errno 101] Network is
unreachable" no matter how correct the SMTP credentials are, even though
the identical code works fine on Streamlit Cloud. Brevo's API sends mail
over plain HTTPS instead, which isn't blocked, so it's the reliable option
wherever the app is hosted - configure BREVO_API_KEY and this is used
automatically. SMTP stays supported as a fallback for hosts that don't
block it (e.g. Streamlit Cloud, where SMTP_HOST/USER/PASSWORD already work).

If neither is configured, send_email() simply returns False so callers can
fall back to showing the content directly in the UI instead of failing.

Configure via environment variables, one of:
  BREVO_API_KEY, BREVO_FROM_EMAIL (optional, defaults to a Brevo default sender)
or:
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

import requests

logger = logging.getLogger("malita.email")

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


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
    if _get_setting("BREVO_API_KEY"):
        return True
    return bool(_get_setting("SMTP_HOST") and _get_setting("SMTP_USER") and _get_setting("SMTP_PASSWORD"))


def _send_via_brevo(to_email: str, subject: str, body: str, api_key: str) -> bool:
    from_email = _get_setting("BREVO_FROM_EMAIL") or "noreply@malita.app"
    try:
        resp = requests.post(
            BREVO_SEND_URL,
            headers={"api-key": api_key, "Content-Type": "application/json", "accept": "application/json"},
            json={
                "sender": {"email": from_email, "name": "Malita"},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": body,
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.warning("send_email: Brevo API rejected the send (status %s): %s", resp.status_code, resp.text[:500])
            return False
        return True
    except Exception:
        logger.exception("send_email: Brevo API request failed for %s", to_email)
        return False


def _send_via_smtp(to_email: str, subject: str, body: str, host: str, user: str, password: str) -> bool:
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


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Best-effort send — returns True only on confirmed success. Any
    misconfiguration or send error is swallowed (never crashes the caller,
    since the caller always has a UI fallback for the "not sent" case) but
    is logged, so the actual cause is visible in the app's server logs
    instead of only ever showing the generic "not sent" fallback."""
    brevo_key = _get_setting("BREVO_API_KEY")
    if brevo_key:
        return _send_via_brevo(to_email, subject, body, brevo_key)

    host = _get_setting("SMTP_HOST")
    user = _get_setting("SMTP_USER")
    password = _get_setting("SMTP_PASSWORD")
    if not (host and user and password):
        missing = [name for name, value in [("SMTP_HOST", host), ("SMTP_USER", user), ("SMTP_PASSWORD", password)] if not value]
        logger.warning("send_email: not configured, missing %s (or set BREVO_API_KEY)", ", ".join(missing))
        return False

    return _send_via_smtp(to_email, subject, body, host, user, password)

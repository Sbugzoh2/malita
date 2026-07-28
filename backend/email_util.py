"""
Malita (Pty) Ltd — minimal outbound email via SMTP.

No third-party email service dependency — just plain smtplib against
whatever SMTP credentials are configured. If none are set (the common case
until you set one up), send_email() simply returns False so callers can
fall back to showing the content directly in the UI instead of failing.

Configure via environment variables:
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD
  SMTP_FROM (optional, defaults to SMTP_USER)
"""

import os
import smtplib
from email.mime.text import MIMEText


def is_email_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Best-effort send — returns True only on confirmed success. Any
    misconfiguration or SMTP error is swallowed (never crashes the caller),
    since the caller always has a UI fallback for the "not sent" case."""
    if not is_email_configured():
        return False

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    from_addr = os.environ.get("SMTP_FROM", user)

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
        return False

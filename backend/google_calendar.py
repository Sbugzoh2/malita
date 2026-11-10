"""
Malita (Pty) Ltd — Google Calendar/Meet integration.

Auto-creates a Google Calendar event with a real Google Meet link whenever
a tutor accepts a learner's session request (see backend/tutoring.py's
accept_tutoring_request), rather than asking either party to paste in
their own link.

WHY A SINGLE STORED OAUTH REFRESH TOKEN, NOT A SERVICE ACCOUNT:
A bare Google Cloud service account (no Google Workspace) CANNOT create a
Meet-enabled Calendar event on a personal/business Gmail calendar at all —
domain-wide delegation (the thing that lets a service account act "as" a
user) only works within a paid Google Workspace domain. Since this is a
small startup on a regular Gmail account, the only way to auto-create Meet
links is a real OAuth user-consent flow: ONE human (whoever owns the
"malita.sessions@..." or similar calendar) grants consent ONCE, and the
resulting refresh token is stored here and reused indefinitely for every
session afterward. This module is that one-time consent flow plus the
ongoing event-creation call.

ONE-TIME SETUP REQUIRED (Google Cloud Console):
  1. console.cloud.google.com -> select or create a project -> APIs &
     Services -> Library -> enable "Google Calendar API".
  2. APIs & Services -> OAuth consent screen -> User type "External" ->
     fill in app name/support email -> add the Calendar scope
     (https://www.googleapis.com/auth/calendar.events) -> add the ONE
     Google account that will own the calendar as a "test user".
  3. APIs & Services -> Credentials -> Create Credentials -> OAuth client
     ID -> Application type "Web application" -> add an Authorized
     redirect URI of {API_BASE_URL}/admin/google-calendar/oauth-callback.
  4. Set GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET env
     vars from that OAuth client.
  5. As an admin, visit {API_BASE_URL}/admin/google-calendar/connect in a
     browser (while logged into the Google account from step 2) and
     approve the consent screen - this captures and stores the refresh
     token server-side. Nothing more to do after this step.

IMPORTANT CAVEAT - read this before relying on it:
While the OAuth consent screen's "Publishing status" is "Testing" (the
default, and the only option until Google reviews/verifies the app),
Google expires every refresh token after 7 days, forcing step 5 to be
repeated weekly. The Calendar scope used here is classified "sensitive"
by Google (not "restricted" - no third-party security assessment needed),
so getting a token that never expires requires submitting the OAuth
consent screen for Google's standard verification (a privacy policy URL,
verified domain ownership, and a short demo video of the consent flow) -
typically days to a few weeks. Until that's done, expect to redo step 5
about once a week. Nothing in this module breaks if the token has
expired - create_meet_session() just raises GoogleCalendarError and the
caller leaves the session without a Meet link rather than failing the
whole acceptance.
"""

import os
import datetime as dt

import requests

from .db import get_session, GoogleCalendarCredentials

GOOGLE_CALENDAR_CLIENT_ID = os.environ.get("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET = os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET", "")
# Narrower than the full "calendar" scope (least privilege) - both are
# classified "sensitive" by Google either way, so this doesn't change the
# verification tier, but it's still the correct scope to request.
_SCOPE = "https://www.googleapis.com/auth/calendar.events"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class GoogleCalendarError(Exception):
    pass


def is_configured() -> bool:
    return bool(GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET)


def build_auth_url(redirect_uri: str) -> str:
    """The URL an admin's browser is redirected to for the one-time
    consent (step 5 above, and whenever a weekly Testing-mode token needs
    renewing)."""
    if not is_configured():
        raise GoogleCalendarError(
            "Google Calendar isn't configured yet (missing GOOGLE_CALENDAR_CLIENT_ID/"
            "GOOGLE_CALENDAR_CLIENT_SECRET) - see backend/google_calendar.py for setup."
        )
    params = {
        "client_id": GOOGLE_CALENDAR_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "access_type": "offline",
        # Forces Google to hand back a refresh token even on a repeat
        # consent (e.g. the weekly Testing-mode renewal) - without this,
        # a second consent by the same account silently omits it.
        "prompt": "consent",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{_AUTH_URL}?{query}"


def handle_oauth_callback(code: str, redirect_uri: str) -> str:
    """Exchanges the authorization code for tokens and stores the refresh
    token (there is only ever one row - a fresh consent replaces it).
    Returns the connected account's email, for a friendly confirmation
    message."""
    if not is_configured():
        raise GoogleCalendarError("Google Calendar isn't configured (missing client id/secret).")
    resp = requests.post(
        _TOKEN_URL,
        data={
            "code": code,
            "client_id": GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": GOOGLE_CALENDAR_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise GoogleCalendarError(f"Google rejected the authorization code (HTTP {resp.status_code}): {resp.text[:300]}")
    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise GoogleCalendarError(
            "Google didn't return a refresh token - this usually means consent was already "
            "granted without 'prompt=consent'. Try the connect link again."
        )
    access_token = tokens.get("access_token", "")

    account_email = None
    try:
        info_resp = requests.get(_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
        if info_resp.status_code == 200:
            account_email = info_resp.json().get("email")
    except requests.RequestException:
        pass

    with get_session() as db:
        existing = db.query(GoogleCalendarCredentials).first()
        if existing:
            existing.refresh_token = refresh_token
            existing.account_email = account_email or existing.account_email
        else:
            db.add(GoogleCalendarCredentials(refresh_token=refresh_token, account_email=account_email))

    return account_email or "(unknown account)"


def _get_access_token() -> str:
    if not is_configured():
        raise GoogleCalendarError("Google Calendar isn't configured (missing client id/secret).")
    with get_session() as db:
        creds = db.query(GoogleCalendarCredentials).first()
        if not creds:
            raise GoogleCalendarError(
                "Google Calendar hasn't been connected yet - an admin needs to visit "
                "/admin/google-calendar/connect once."
            )
        refresh_token = creds.refresh_token

    resp = requests.post(
        _TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": GOOGLE_CALENDAR_CLIENT_SECRET,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        # Most common cause: the stored refresh token expired (see this
        # module's docstring - weekly, while in Google's "Testing" mode).
        raise GoogleCalendarError(
            f"Could not refresh the Google Calendar connection (HTTP {resp.status_code}) - "
            "it may have expired and need reconnecting via /admin/google-calendar/connect."
        )
    return resp.json()["access_token"]


def create_meet_session(
    *, summary: str, description: str, start: dt.datetime, duration_minutes: int,
    attendee_emails: list[str],
) -> dict:
    """Creates a Calendar event with an auto-generated Google Meet link
    and invites attendee_emails. Returns {"meet_link": str, "event_id": str}.
    Raises GoogleCalendarError on any failure - callers must treat this as
    optional and never let it block the session itself (see
    backend/tutoring.py's accept_tutoring_request)."""
    access_token = _get_access_token()
    end = start + dt.timedelta(minutes=duration_minutes)
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": "Africa/Johannesburg"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Africa/Johannesburg"},
        "attendees": [{"email": e} for e in attendee_emails if e],
        "conferenceData": {
            "createRequest": {
                "requestId": f"malita-{start.timestamp():.0f}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    resp = requests.post(
        f"{_EVENTS_URL}?conferenceDataVersion=1&sendUpdates=all",
        json=body,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code not in (200, 201):
        raise GoogleCalendarError(f"Could not create the Calendar event (HTTP {resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    meet_link = ""
    for entry_point in data.get("conferenceData", {}).get("entryPoints", []):
        if entry_point.get("entryPointType") == "video":
            meet_link = entry_point.get("uri", "")
            break
    if not meet_link:
        raise GoogleCalendarError("Calendar event created but no Meet link was returned.")
    return {"meet_link": meet_link, "event_id": data.get("id", "")}

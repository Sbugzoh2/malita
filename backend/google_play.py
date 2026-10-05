"""
Malita (Pty) Ltd — Google Play Billing purchase verification.

Mirrors backend/payfast.py's job but for subscriptions bought through
Google Play, needed because Google requires every app offering digital
subscriptions on the Play Store to support Play Billing - PayFast alone
isn't allowed to be the only option (see README_GOOGLE_PLAY_BILLING.txt
for the full policy background). Under User Choice Billing, PayFast and
Play Billing sit side by side; this module handles the Play Billing side.

Verifies a purchase token server-side against the Android Publisher API
rather than trusting whatever the phone app reports - same reasoning as
payfast.py's verify_with_payfast() double-checking PayFast's ITN instead
of trusting the webhook body on signature alone.

ONE-TIME SETUP REQUIRED (in Google Play Console + Google Cloud Console):
  1. Play Console -> Setup -> API access -> link (or create) a Google
     Cloud project for this app.
  2. In that Cloud project: IAM & Admin -> Service Accounts -> create one
     (e.g. "malita-play-billing"). Create a JSON key for it and download it.
  3. Back in Play Console -> API access -> find that service account ->
     grant it "Financial data" access (view-only is enough for
     verification/acknowledgement).
  4. Deploy the JSON key's contents (or a path to the file) as the
     GOOGLE_PLAY_SERVICE_ACCOUNT_JSON environment variable alongside your
     other secrets (PAYFAST_*, etc.) - never commit the key file itself.
  5. Set GOOGLE_PLAY_PACKAGE_NAME if it ever differs from the Android
     package id already in mobile/app.json (com.malita.mathstutor).

Until that's configured, verify_subscription_purchase() raises
GooglePlayVerificationError with a clear message instead of silently
granting access - a missing/misconfigured service account must never be
able to be worked around by just not checking.
"""

import os
import json
import datetime as dt

import requests
from google.oauth2 import service_account
import google.auth.transport.requests

PACKAGE_NAME = os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", "com.malita.mathstutor")
_SCOPES = ["https://www.googleapis.com/auth/androidpublisher"]
_ANDROID_PUBLISHER_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3"

# Google's subscriptionsv2 states that mean the learner currently has paid
# access - everything else (EXPIRED, CANCELED-and-lapsed, etc.) should not
# grant the tier. IN_GRACE_PERIOD is included because Google is still
# retrying the renewal charge - treat it as active rather than punishing
# the learner for a payment hiccup that might still resolve.
_ACTIVE_STATES = {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"}

_credentials = None


class GooglePlayVerificationError(Exception):
    """Raised whenever a purchase can't be trusted - missing server
    config, Google rejecting the token, or the subscription not actually
    being in an active state. Callers should treat this the same way as
    an invalid PayFast signature: refuse to grant the tier."""


def _load_credentials():
    global _credentials
    if _credentials is not None:
        return _credentials
    raw = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    # Accept either the raw JSON contents (easiest for most hosting
    # platforms' "paste a secret" env var UI) or a path to the key file.
    info = json.loads(raw) if raw.strip().startswith("{") else json.loads(open(raw).read())
    _credentials = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    return _credentials


def _access_token() -> str:
    creds = _load_credentials()
    if creds is None:
        raise GooglePlayVerificationError(
            "Google Play purchase verification isn't configured on this server "
            "(missing GOOGLE_PLAY_SERVICE_ACCOUNT_JSON) - see backend/google_play.py "
            "for one-time setup steps."
        )
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def verify_subscription_purchase(product_id: str, purchase_token: str) -> dict:
    """Calls the Android Publisher API's subscriptionsv2.get endpoint for
    this purchase token and returns {"active": bool, "expiry": datetime|None}.

    Raises GooglePlayVerificationError if Google rejects the token outright
    (e.g. a forged/garbage token from a tampered client) or credentials
    aren't configured - callers must not fall back to trusting the client
    in that case."""
    token = _access_token()
    url = (
        f"{_ANDROID_PUBLISHER_BASE}/applications/{PACKAGE_NAME}"
        f"/purchases/subscriptionsv2/tokens/{purchase_token}"
    )
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    if resp.status_code != 200:
        raise GooglePlayVerificationError(
            f"Google Play rejected this purchase token (HTTP {resp.status_code})."
        )

    data = resp.json()
    state = data.get("subscriptionState", "")
    active = state in _ACTIVE_STATES

    expiry = None
    for item in data.get("lineItems", []):
        expiry_str = item.get("expiryTime")
        if expiry_str:
            # RFC3339 e.g. "2026-11-05T12:00:00.000Z" - strip sub-second
            # precision and the trailing "Z" before parsing.
            expiry = dt.datetime.strptime(expiry_str.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            break

    return {"active": active, "expiry": expiry}


def acknowledge_purchase(product_id: str, purchase_token: str) -> None:
    """Google auto-refunds any subscription purchase that isn't
    acknowledged within 3 days. The mobile app's IAP library normally
    acknowledges it on-device right after purchase, but doing it again
    here (server-side, right after we've verified the purchase) is
    harmless - Google just no-ops an already-acknowledged token - and
    guarantees it happens even if the app is killed immediately after
    purchase, before its own acknowledgement call can complete."""
    try:
        token = _access_token()
    except GooglePlayVerificationError:
        return
    url = (
        f"{_ANDROID_PUBLISHER_BASE}/applications/{PACKAGE_NAME}"
        f"/purchases/subscriptions/{product_id}/tokens/{purchase_token}:acknowledge"
    )
    try:
        requests.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    except requests.RequestException:
        pass  # best-effort - the on-device acknowledgement is the primary path

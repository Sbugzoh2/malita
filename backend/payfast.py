"""
Malita (Pty) Ltd — PayFast integration.

Two directions of traffic:
  1. OUTGOING checkout: we build a signed URL/form that redirects the
     learner to PayFast to pay. We control the field order here completely.
  2. INCOMING ITN (Instant Transaction Notification): PayFast POSTs payment
     results to our webhook. We must verify the signature AND confirm the
     data with PayFast's own servers before trusting it (PayFast's own
     recommended security process — never trust an ITN on signature alone).

IMPORTANT — VERIFY BEFORE GOING LIVE:
PayFast's own documentation has, at different times, described the outgoing
signature field order as either a fixed field order or alphabetical, and
this has caused real production signature-mismatch bugs for other
developers. Before accepting real payments:
  1. Log into your PayFast dashboard -> Sandbox -> use their built-in
     "signature tool" to generate a signature from a sample parameter set,
     and compare it to what generate_signature() below produces.
  2. Do a full sandbox test purchase end-to-end (see README) before
     switching PASSPHRASE/merchant IDs to live/production values.
"""

import os
import socket
import hashlib
import html
import json
import urllib.parse
import datetime as dt
from collections import OrderedDict

import requests

PAYFAST_MERCHANT_ID = os.environ.get("PAYFAST_MERCHANT_ID", "14006256")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "m5ne6hlhz1wak")
PAYFAST_PASSPHRASE = os.environ.get("PAYFAST_PASSPHRASE", "MtnJse212535942Ukzn_Sb")  # required for recurring billing
PAYFAST_SANDBOX = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"

PAYFAST_HOST = "sandbox.payfast.co.za" if PAYFAST_SANDBOX else "www.payfast.co.za"
PAYFAST_PROCESS_URL = f"https://{PAYFAST_HOST}/eng/process"
PAYFAST_VALIDATE_URL = f"https://{PAYFAST_HOST}/eng/query/validate"

# Fixed field order matching PayFast's documented parameter definition order.
# We build the checkout data dict in this exact order so the signature
# string is deterministic and matches what PayFast expects to verify.
CHECKOUT_FIELD_ORDER = [
    "merchant_id", "merchant_key", "return_url", "cancel_url", "notify_url",
    "name_first", "name_last", "email_address", "cell_number",
    "m_payment_id", "amount", "item_name", "item_description",
    "custom_int1", "custom_int2", "custom_int3", "custom_int4", "custom_int5",
    "custom_str1", "custom_str2", "custom_str3", "custom_str4", "custom_str5",
    "email_confirmation", "confirmation_address",
    "payment_method",
    "subscription_type", "billing_date", "recurring_amount", "frequency", "cycles",
]


def _payfast_urlencode(value: str) -> str:
    # PayFast expects '+' for spaces (classic application/x-www-form-urlencoded),
    # not %20 — use urllib.parse.quote_plus to match.
    return urllib.parse.quote_plus(str(value).strip())


def generate_signature(data: dict, passphrase: str = "") -> str:
    """Build the '&'-joined, url-encoded parameter string in PayFast's
    documented field order (skipping empty values), optionally append the
    passphrase, MD5 hash it, and return the lowercase hex digest."""
    ordered = OrderedDict()
    for key in CHECKOUT_FIELD_ORDER:
        if key in data and data[key] not in (None, ""):
            ordered[key] = data[key]
    # include any keys not in our known list too (forward-compatible)
    for key, value in data.items():
        if key not in ordered and value not in (None, ""):
            ordered[key] = value

    param_string = "&".join(
        f"{k}={_payfast_urlencode(v)}" for k, v in ordered.items()
    )
    if passphrase:
        param_string += f"&passphrase={_payfast_urlencode(passphrase)}"

    return hashlib.md5(param_string.encode("utf-8")).hexdigest()


def build_checkout_payload(
    *, m_payment_id: str, amount: float, item_name: str,
    name_first: str, email_address: str,
    return_url: str, cancel_url: str, notify_url: str,
    recurring: bool = False, recurring_amount: float = None, frequency: int = 3,
    cycles: int = 0, custom_fields: dict = None,
) -> dict:
    """Returns a dict of form fields (including 'signature') ready to be
    posted/redirected to PAYFAST_PROCESS_URL.

    frequency: PayFast codes — 3=monthly, 4=quarterly, 5=biannually, 6=annual.
    cycles: 0 = indefinite (bills until cancelled) — normal for a subscription.
    """
    data = {
        "merchant_id": PAYFAST_MERCHANT_ID,
        "merchant_key": PAYFAST_MERCHANT_KEY,
        "return_url": return_url,
        "cancel_url": cancel_url,
        "notify_url": notify_url,
        "name_first": name_first,
        "email_address": email_address,
        "m_payment_id": m_payment_id,
        "amount": f"{amount:.2f}",
        "item_name": item_name,
    }
    if recurring:
        data.update({
            "subscription_type": "1",
            "recurring_amount": f"{(recurring_amount if recurring_amount is not None else amount):.2f}",
            "frequency": str(frequency),
            "cycles": str(cycles),
        })

    if custom_fields:
        data.update(custom_fields)

    # Signature MUST be generated last, once every field we're actually
    # sending (including custom_str1/2 etc.) is already in the dict —
    # otherwise PayFast will compute a different signature than we did and
    # reject the payment as tampered.
    data["signature"] = generate_signature(data, PAYFAST_PASSPHRASE)
    return data


def _hidden_fields_html(payload: dict) -> str:
    return "\n".join(
        f'<input type="hidden" name="{html.escape(str(k))}" value="{html.escape(str(v))}">'
        for k, v in payload.items()
    )


def build_checkout_redirect_snippet(payload: dict) -> str:
    """A components.html-style snippet that builds a real POST <form> on
    the PARENT document (same window.parent.document trick app.py's PWA
    setup already uses to reach past its own sandboxed iframe) and submits
    it. PayFast's sandbox used to tolerate a plain GET link with the
    payload in the query string, but live PayFast returns its own generic
    500 "Server Error" for that same GET request — the documented
    integration is a real form POST, so that's what this builds."""
    return f"""
    <script>
    (function() {{
        try {{
            var doc = window.parent.document;
            var form = doc.createElement('form');
            form.method = 'POST';
            form.action = {json.dumps(PAYFAST_PROCESS_URL)};
            var fields = {json.dumps(payload)};
            for (var key in fields) {{
                var input = doc.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = fields[key];
                form.appendChild(input);
            }}
            doc.body.appendChild(form);
            form.submit();
        }} catch (e) {{
            console.error('PayFast redirect failed:', e);
        }}
    }})();
    </script>
    """


def build_checkout_page_html(payload: dict) -> str:
    """A standalone HTML page (not a components.html snippet) that
    auto-submits the same POST on load — used by the API's
    /billing/checkout-page endpoint, which the mobile app opens directly
    in the phone's browser via Linking.openURL (which can only navigate to
    a URL, not inject a form into an existing page)."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Redirecting to PayFast…</title></head>
<body onload="document.getElementById('payfast-checkout-form').submit();">
<form id="payfast-checkout-form" method="POST" action="{html.escape(PAYFAST_PROCESS_URL)}">
{_hidden_fields_html(payload)}
</form>
<p style="font-family: sans-serif; text-align: center; margin-top: 40px;">Redirecting to PayFast…</p>
</body></html>"""


# ---------------------------------------------------------------------------
# INCOMING ITN (webhook) verification
# ---------------------------------------------------------------------------

def verify_itn_signature(post_data: dict) -> bool:
    """Recompute the signature from the POSTed data (preserving the order
    fields arrived in, per PayFast's own reference implementation) and
    compare to the 'signature' field PayFast sent us."""
    received_signature = post_data.get("signature", "")
    data_without_sig = OrderedDict(
        (k, v) for k, v in post_data.items() if k != "signature"
    )
    param_string = "&".join(
        f"{k}={_payfast_urlencode(v)}" for k, v in data_without_sig.items()
    )
    if PAYFAST_PASSPHRASE:
        param_string += f"&passphrase={_payfast_urlencode(PAYFAST_PASSPHRASE)}"

    expected = hashlib.md5(param_string.encode("utf-8")).hexdigest()
    return expected == received_signature


def is_payfast_ip(remote_ip: str) -> bool:
    """PayFast recommend confirming the ITN really came from their servers.
    We do a reverse-DNS check for a payfast.co.za / payfast.io hostname.
    Not bulletproof on its own — always combine with verify_with_payfast()."""
    try:
        host, _, _ = socket.gethostbyaddr(remote_ip)
        return host.endswith("payfast.co.za") or host.endswith("payfast.io")
    except (socket.herror, socket.gaierror):
        return False


def verify_with_payfast(post_data: dict, timeout: int = 15) -> bool:
    """Second line of defense recommended by PayFast: post the ITN data
    straight back to their validate endpoint and require the literal
    response 'VALID'. Do this BEFORE granting/renewing a subscription."""
    body = {k: v for k, v in post_data.items()}
    try:
        resp = requests.post(PAYFAST_VALIDATE_URL, data=body, timeout=timeout)
        return resp.text.strip() == "VALID"
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# OUTGOING: cancel a recurring subscription
# ---------------------------------------------------------------------------
# IMPORTANT — VERIFY BEFORE RELYING ON THIS: this follows PayFast's
# documented Subscriptions API (api.payfast.co.za), signing sorted
# `merchant-id`/`version`/`timestamp` params the same way as the ITN
# signature above. As with the checkout signature (see module docstring),
# confirm this against a real PayFast sandbox subscription before trusting
# it in production — if it ever returns False, tell the user to also
# cancel directly from their PayFast dashboard so they're never stuck
# still being billed.
PAYFAST_API_URL = "https://api.payfast.co.za"


def cancel_payfast_subscription(token: str, timeout: int = 15) -> bool:
    """Best-effort call to PayFast's subscription-cancel endpoint. Returns
    True only on a confirmed 200 response — any error/exception returns
    False so the caller can warn the user rather than assume it worked."""
    if not token:
        return False

    timestamp = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    params = {
        "merchant-id": PAYFAST_MERCHANT_ID,
        "version": "v1",
        "timestamp": timestamp,
    }
    signature_string = "&".join(
        f"{k}={_payfast_urlencode(v)}" for k, v in sorted(params.items())
    )
    if PAYFAST_PASSPHRASE:
        signature_string += f"&passphrase={_payfast_urlencode(PAYFAST_PASSPHRASE)}"
    signature = hashlib.md5(signature_string.encode("utf-8")).hexdigest()

    headers = {**params, "signature": signature}
    url = f"{PAYFAST_API_URL}/subscriptions/{token}/cancel"
    if PAYFAST_SANDBOX:
        url += "?testing=true"

    try:
        resp = requests.put(url, headers=headers, timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False

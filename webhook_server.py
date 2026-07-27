"""
Malita (Pty) Ltd — PayFast ITN webhook receiver.

WHY THIS IS A SEPARATE SERVICE FROM app.py:
Streamlit is built as a single interactive frontend — it doesn't expose
arbitrary custom HTTP routes the way a real backend does, so it can't
reliably receive PayFast's server-to-server webhook POSTs. This tiny
FastAPI app is the one piece of "real backend" the business needs; it does
nothing except: verify each PayFast notification, double-check it with
PayFast's own servers, and update the subscription in the shared database
that app.py also reads from.

RUN IT WITH:
    uvicorn webhook_server:app --host 0.0.0.0 --port 8001

DEPLOY IT SOMEWHERE PUBLICLY REACHABLE (e.g. a small VPS, Railway, Render,
Fly.io) and point PAYFAST's notify_url — and the NOTIFY_URL env var used
when building checkout links in app.py — at:
    https://your-domain.com/payfast/notify
"""

import json
import datetime as dt
from collections import OrderedDict

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from backend.db import init_db, get_session, Subscription, WebhookEvent
from backend.payfast import verify_itn_signature, verify_with_payfast

app = FastAPI(title="Malita PayFast Webhook")

init_db()

# Map PayFast's billing frequency code to an approximate renewal period,
# used only to extend current_period_end for our own display purposes.
FREQUENCY_DAYS = {"3": 31, "4": 93, "5": 183, "6": 365}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/payfast/notify")
async def payfast_notify(request: Request):
    raw_form = await request.form()
    # Preserve arrival order — required for signature recomputation to match.
    post_data = OrderedDict((k, v) for k, v in raw_form.multi_items())

    signature_ok = verify_itn_signature(post_data)

    with get_session() as db:
        db.add(WebhookEvent(
            payload=json.dumps(post_data),
            signature_valid=signature_ok,
            processed=False,
        ))

    if not signature_ok:
        # Don't tell PayFast why - just don't process it. Return 200 so
        # PayFast doesn't endlessly retry a request we've already logged.
        return PlainTextResponse("invalid signature", status_code=400)

    # Second line of defense: confirm the data with PayFast's own servers
    # server-to-server before trusting it (PayFast's documented recommendation).
    if not verify_with_payfast(post_data):
        return PlainTextResponse("could not verify with payfast", status_code=400)

    # custom_str1 / custom_str2 are fields WE set when building the checkout
    # link in app.py, carrying our own user_id and target tier through the
    # round trip so we know whose subscription to update.
    user_id = post_data.get("custom_str1")
    tier = post_data.get("custom_str2", "learner")
    payment_status = post_data.get("payment_status", "")
    token = post_data.get("token")  # recurring billing token, if applicable
    frequency = post_data.get("frequency", "3")

    if not user_id:
        return PlainTextResponse("missing user reference", status_code=400)

    with get_session() as db:
        sub = db.query(Subscription).filter(
            Subscription.user_id == int(user_id)
        ).first()
        if not sub:
            return PlainTextResponse("unknown user", status_code=404)

        if payment_status == "COMPLETE":
            sub.tier = tier
            sub.status = "active"
            if token:
                sub.payfast_token = token
            days = FREQUENCY_DAYS.get(frequency, 31)
            sub.current_period_end = dt.datetime.utcnow() + dt.timedelta(days=days)
        elif payment_status in ("CANCELLED", "FAILED"):
            sub.status = "cancelled" if payment_status == "CANCELLED" else "past_due"

    return PlainTextResponse("OK", status_code=200)

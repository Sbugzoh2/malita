"""
Malita (Pty) Ltd — one-off CLI to manually confirm a tutoring session
whose PayFast payment actually went through but never got recorded,
because of the webhook bug fixed alongside this script (see
backend/tutoring.py's mark_session_paid and backend/google_calendar.py -
a network blip talking to Google during Meet-link creation could roll
back the payment confirmation that had already happened in the same
transaction).

This calls the exact same mark_session_paid() the webhook itself calls -
same validation, same Meet-link creation attempt, same learner/tutor
notifications - just triggered by request id instead of by m_payment_id,
since you know the request id (it's PayFast's own custom_str2 field on
the transaction) but not necessarily the m_payment_id off the top of your
head. Safe to run even if the session somehow already got confirmed by
other means - mark_session_paid() is idempotent either way.

Usage:
    python -m backend.confirm_stuck_tutoring_payment 13
"""

import sys

from .db import get_session, TutoringSessionRequest
from .tutoring import mark_session_paid, TutoringError


def confirm_stuck_tutoring_payment(request_id: int) -> None:
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            print(f"No tutoring session request with id {request_id}.")
            return
        if not req.m_payment_id:
            print(f"Request {request_id} has no m_payment_id on file - nothing to confirm by.")
            return
        m_payment_id, current_status = req.m_payment_id, req.status

    print(f"Request {request_id} is currently '{current_status}' (m_payment_id={m_payment_id}).")
    try:
        result = mark_session_paid(m_payment_id)
    except TutoringError as e:
        print(f"Could not confirm: {e}")
        return
    print(f"Done - request {request_id} is now '{result['status']}'.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        print("Usage: python -m backend.confirm_stuck_tutoring_payment <request_id>")
        sys.exit(1)
    confirm_stuck_tutoring_payment(int(sys.argv[1]))

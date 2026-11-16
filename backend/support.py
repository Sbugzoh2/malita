"""
Malita (Pty) Ltd — "Contact Admin" support tickets.

Neither a learner nor a tutor had any in-app way to reach Malita's admin
before this - this is a real back-and-forth thread (see SupportTicket/
SupportTicketMessage in backend/db.py), not a one-shot message: a
learner/tutor opens a ticket with a subject + first message, an admin
replies from the console, and the learner/tutor sees that reply and can
keep replying, all inside the app.

Same conventions as backend/tutoring.py's own notification pattern
(best-effort email + in-app Notification, never allowed to break the
action that triggered it) and recipient_kind ("user" covers a learner OR
an admin, both User rows - "tutor" is a TutorAccount row).
"""

import logging
import datetime as dt

from .db import get_session, User, TutorAccount, SupportTicket, SupportTicketMessage, Notification
from .email_util import send_email

logger = logging.getLogger("malita.support")

SENDER_KINDS = ("user", "tutor")
MESSAGE_SENDER_KINDS = ("user", "tutor", "admin")


class SupportError(Exception):
    pass


def create_notification(*, recipient_kind: str, recipient_id: int, title: str, body: str = "") -> None:
    """Same best-effort philosophy as backend/tutoring.py's own
    create_notification (duplicated rather than imported, to keep this
    module independent of the tutoring-marketplace domain)."""
    try:
        with get_session() as db:
            db.add(Notification(recipient_kind=recipient_kind, recipient_id=recipient_id, title=title, body=body or None))
    except Exception:
        logger.exception("Failed to create a notification (kind=%s, id=%s)", recipient_kind, recipient_id)


def _sender_name_and_email(sender_kind: str, sender_id: int) -> tuple[str, str]:
    with get_session() as db:
        if sender_kind == "user":
            row = db.query(User).get(sender_id)
        elif sender_kind == "tutor":
            row = db.query(TutorAccount).get(sender_id)
        else:
            row = None
        if not row:
            raise SupportError("Account not found.")
        return row.name, row.email


def _serialize_ticket(t: SupportTicket, *, with_messages: bool) -> dict:
    sender_name, sender_email = _sender_name_and_email(t.sender_kind, t.sender_id)
    out = {
        "id": t.id,
        "sender_kind": t.sender_kind,
        "sender_id": t.sender_id,
        "sender_name": sender_name,
        "sender_email": sender_email,
        "subject": t.subject,
        "status": t.status,
        "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
        "updated_at": t.updated_at.isoformat() + "Z" if t.updated_at else None,
    }
    if with_messages:
        out["messages"] = [
            {
                "id": m.id,
                "sender_kind": m.sender_kind,
                "sender_id": m.sender_id,
                "body": m.body,
                "created_at": m.created_at.isoformat() + "Z" if m.created_at else None,
            }
            for m in t.messages
        ]
    return out


def create_support_ticket(sender_kind: str, sender_id: int, subject: str, message: str) -> dict:
    """Opens a new ticket with its first message, and notifies every
    admin (same pattern as backend/tutoring.py's
    _notify_admins_of_custom_claim) so someone actually goes and looks,
    rather than relying on an admin checking the console on a schedule."""
    if sender_kind not in SENDER_KINDS:
        raise SupportError("Unknown sender kind.")
    subject = (subject or "").strip()
    message = (message or "").strip()
    if not subject:
        raise SupportError("Please enter a subject.")
    if not message:
        raise SupportError("Please enter a message.")

    sender_name, sender_email = _sender_name_and_email(sender_kind, sender_id)

    with get_session() as db:
        ticket = SupportTicket(sender_kind=sender_kind, sender_id=sender_id, subject=subject, status="open")
        db.add(ticket)
        db.flush()
        db.add(SupportTicketMessage(ticket_id=ticket.id, sender_kind=sender_kind, sender_id=sender_id, body=message))
        ticket_id = ticket.id

    _notify_admins_of_new_ticket(ticket_id, sender_name, sender_email, subject, message)
    return get_support_ticket(ticket_id, sender_kind, sender_id)


def list_my_support_tickets(sender_kind: str, sender_id: int) -> list[dict]:
    with get_session() as db:
        tickets = (
            db.query(SupportTicket)
            .filter(SupportTicket.sender_kind == sender_kind, SupportTicket.sender_id == sender_id)
            .order_by(SupportTicket.updated_at.desc())
            .all()
        )
        return [_serialize_ticket(t, with_messages=False) for t in tickets]


def get_support_ticket(ticket_id: int, sender_kind: str | None = None, sender_id: int | None = None) -> dict:
    """Pass sender_kind/sender_id to enforce that a learner/tutor can only
    open THEIR OWN ticket - omit both (admin callers) to fetch any ticket."""
    with get_session() as db:
        t = db.query(SupportTicket).get(ticket_id)
        if not t:
            raise SupportError("Ticket not found.")
        if sender_kind is not None and (t.sender_kind != sender_kind or t.sender_id != sender_id):
            raise SupportError("Ticket not found.")
        return _serialize_ticket(t, with_messages=True)


def reply_to_support_ticket(
    ticket_id: int, sender_kind: str, sender_id: int, body: str,
    *, owner_kind: str | None = None, owner_id: int | None = None,
) -> dict:
    """Adds one message to the thread. A learner/tutor reply must pass
    owner_kind/owner_id (itself, since only the ticket's own opener can
    reply as "user"/"tutor") to enforce ownership; an admin reply
    (sender_kind="admin") needs neither."""
    body = (body or "").strip()
    if not body:
        raise SupportError("Please enter a message.")
    if sender_kind not in MESSAGE_SENDER_KINDS:
        raise SupportError("Unknown sender kind.")

    with get_session() as db:
        t = db.query(SupportTicket).get(ticket_id)
        if not t:
            raise SupportError("Ticket not found.")
        if owner_kind is not None and (t.sender_kind != owner_kind or t.sender_id != owner_id):
            raise SupportError("Ticket not found.")
        db.add(SupportTicketMessage(ticket_id=ticket_id, sender_kind=sender_kind, sender_id=sender_id, body=body))
        t.updated_at = dt.datetime.utcnow()
        opener_kind, opener_id, subject = t.sender_kind, t.sender_id, t.subject

    if sender_kind == "admin":
        _notify_ticket_opener_of_admin_reply(opener_kind, opener_id, subject, body)
    else:
        _notify_admins_of_new_ticket_reply(ticket_id, subject, body)

    return get_support_ticket(ticket_id, owner_kind, owner_id)


def list_all_support_tickets_admin(status: str | None = None, limit: int = 100) -> list[dict]:
    with get_session() as db:
        q = db.query(SupportTicket)
        if status:
            q = q.filter(SupportTicket.status == status)
        tickets = q.order_by(SupportTicket.updated_at.desc()).limit(limit).all()
        return [_serialize_ticket(t, with_messages=False) for t in tickets]


def resolve_support_ticket(ticket_id: int) -> dict:
    with get_session() as db:
        t = db.query(SupportTicket).get(ticket_id)
        if not t:
            raise SupportError("Ticket not found.")
        t.status = "resolved"
    return get_support_ticket(ticket_id)


def reopen_support_ticket(ticket_id: int) -> dict:
    with get_session() as db:
        t = db.query(SupportTicket).get(ticket_id)
        if not t:
            raise SupportError("Ticket not found.")
        t.status = "open"
    return get_support_ticket(ticket_id)


def _notify_admins_of_new_ticket(ticket_id: int, sender_name: str, sender_email: str, subject: str, message: str) -> None:
    try:
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admins:
            return
        body = (
            f"{sender_name} ({sender_email}) opened a new support ticket - {subject}.\n\n"
            f"\"{message}\"\n\n"
            "Open the admin console's Support tab to reply."
        )
        for admin_id, email in admins:
            send_email(email, f"New support ticket: {subject}", body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id, title="New support ticket",
                body=f"{sender_name}: {subject}",
            )
    except Exception:
        logger.exception("Failed to notify admins of new support ticket %s", ticket_id)


def _notify_admins_of_new_ticket_reply(ticket_id: int, subject: str, body: str) -> None:
    try:
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admins:
            return
        email_body = f"New reply on support ticket #{ticket_id} - {subject}:\n\n\"{body}\""
        for admin_id, email in admins:
            send_email(email, f"New reply on support ticket: {subject}", email_body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id, title="New reply on a support ticket",
                body=f"{subject}: {body[:140]}",
            )
    except Exception:
        logger.exception("Failed to notify admins of a reply on support ticket %s", ticket_id)


def _notify_ticket_opener_of_admin_reply(opener_kind: str, opener_id: int, subject: str, body: str) -> None:
    try:
        name, email = _sender_name_and_email(opener_kind, opener_id)
        email_body = f"Hi {name},\n\nMalita support replied to your ticket \"{subject}\":\n\n\"{body}\"\n\n— The Malita team"
        send_email(email, f"Reply to your support ticket: {subject}", email_body)
        create_notification(
            recipient_kind=opener_kind, recipient_id=opener_id, title="Support replied to your ticket",
            body=body[:140],
        )
    except Exception:
        logger.exception("Failed to notify ticket opener (kind=%s, id=%s) of admin reply", opener_kind, opener_id)

"""
Malita (Pty) Ltd — Collaborate: a Learner/Premium Q&A board where
learners can post a question and help each other answer it, grouped by
Subject/Topic same as everywhere else in the app.

Deliberately async (no chat/real-time), and deliberately simple: no
voting, no accepted-answer marking, no notifications - just post,
reply, and (if something's wrong) report it for an admin to review.
"""

import datetime as dt
import logging
import os

from .db import get_session, CollabQuestion, CollabAnswer, CollabReport, User
from .email_util import send_email

logger = logging.getLogger("malita.collab")

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8501")

_ACTION_OUTCOME = {
    "hide": "hidden from other learners",
    "delete": "permanently deleted",
    "dismiss": "reviewed - no action was taken",
}


def create_question(user_id: int, subject: str, topic: str, title: str, body: str) -> int:
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValueError("Please add a title for your question.")
    if not body:
        raise ValueError("Please write out your question.")

    with get_session() as db:
        q = CollabQuestion(
            user_id=user_id, subject=subject, topic=(topic or None),
            title=title[:200], body=body,
        )
        db.add(q)
        db.flush()
        return q.id


def list_questions(subject: str, topic: str | None = None, limit: int = 50) -> list[dict]:
    """Newest first, hidden posts excluded - the learner-facing feed."""
    with get_session() as db:
        query = (
            db.query(CollabQuestion, User.name)
            .join(User, User.id == CollabQuestion.user_id)
            .filter(CollabQuestion.subject == subject, CollabQuestion.is_hidden.is_(False))
        )
        if topic:
            query = query.filter(CollabQuestion.topic == topic)
        rows = query.order_by(CollabQuestion.created_at.desc()).limit(limit).all()

        result = []
        for q, asker_name in rows:
            answer_count = (
                db.query(CollabAnswer)
                .filter(CollabAnswer.question_id == q.id, CollabAnswer.is_hidden.is_(False))
                .count()
            )
            result.append({
                "id": q.id, "subject": q.subject, "topic": q.topic,
                "title": q.title, "body": q.body,
                "asker_name": asker_name, "created_at": q.created_at,
                "answer_count": answer_count,
            })
        return result


def get_question(question_id: int) -> dict | None:
    """One question plus its (non-hidden) answers, newest first excluded -
    answers show oldest first, like a normal thread."""
    with get_session() as db:
        row = (
            db.query(CollabQuestion, User.name)
            .join(User, User.id == CollabQuestion.user_id)
            .filter(CollabQuestion.id == question_id, CollabQuestion.is_hidden.is_(False))
            .first()
        )
        if not row:
            return None
        q, asker_name = row

        answer_rows = (
            db.query(CollabAnswer, User.name)
            .join(User, User.id == CollabAnswer.user_id)
            .filter(CollabAnswer.question_id == question_id, CollabAnswer.is_hidden.is_(False))
            .order_by(CollabAnswer.created_at.asc())
            .all()
        )
        answers = [
            {
                "id": a.id, "body": a.body, "answerer_name": name,
                "created_at": a.created_at, "parent_id": a.parent_id,
                "user_id": a.user_id, "is_edited": bool(a.is_edited),
            }
            for a, name in answer_rows
        ]
        return {
            "id": q.id, "subject": q.subject, "topic": q.topic,
            "title": q.title, "body": q.body,
            "asker_name": asker_name, "created_at": q.created_at,
            "user_id": q.user_id, "is_edited": bool(q.is_edited),
            "answers": answers,
        }


def update_question(question_id: int, user_id: int, title: str, body: str) -> None:
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValueError("Please add a title for your question.")
    if not body:
        raise ValueError("Please write out your question.")

    with get_session() as db:
        q = db.query(CollabQuestion).filter(CollabQuestion.id == question_id).first()
        if not q:
            raise ValueError("That question no longer exists.")
        if q.user_id != user_id:
            raise ValueError("You can only edit your own question.")
        q.title = title[:200]
        q.body = body
        q.is_edited = True


def update_answer(answer_id: int, user_id: int, body: str) -> None:
    body = (body or "").strip()
    if not body:
        raise ValueError("Please write out your answer.")

    with get_session() as db:
        a = db.query(CollabAnswer).filter(CollabAnswer.id == answer_id).first()
        if not a:
            raise ValueError("That answer no longer exists.")
        if a.user_id != user_id:
            raise ValueError("You can only edit your own answer.")
        a.body = body
        a.is_edited = True


def create_answer(question_id: int, user_id: int, body: str, parent_id: int | None = None) -> int:
    body = (body or "").strip()
    if not body:
        raise ValueError("Please write out your answer.")

    with get_session() as db:
        exists = db.query(CollabQuestion).filter(
            CollabQuestion.id == question_id, CollabQuestion.is_hidden.is_(False)
        ).first()
        if not exists:
            raise ValueError("That question no longer exists.")

        if parent_id is not None:
            parent = db.query(CollabAnswer).filter(
                CollabAnswer.id == parent_id, CollabAnswer.question_id == question_id,
                CollabAnswer.is_hidden.is_(False),
            ).first()
            if not parent:
                raise ValueError("That answer no longer exists.")
            if parent.parent_id is not None:
                # Replies are capped at one level deep - redirect a
                # reply-to-a-reply onto the original top-level answer so
                # the thread never grows a third level; @mentioning the
                # actual person (see the reply-prefill UI) is how the
                # learner still makes clear who they're responding to.
                parent_id = parent.parent_id

        a = CollabAnswer(question_id=question_id, user_id=user_id, body=body, parent_id=parent_id)
        db.add(a)
        db.flush()
        return a.id


def report_content(target_type: str, target_id: int, reporter_id: int, reason: str = "") -> None:
    if target_type not in ("question", "answer"):
        raise ValueError("Unknown content type to report.")

    reason = (reason or "").strip()[:500]
    with get_session() as db:
        db.add(CollabReport(
            target_type=target_type, target_id=target_id,
            reporter_id=reporter_id, reason=reason,
        ))
        reporter = db.query(User).filter(User.id == reporter_id).first()
        reporter_name = reporter.name if reporter else "A learner"

    _notify_admins_of_report(target_type, target_id, reporter_name, reason)


def _notify_admins_of_report(target_type: str, target_id: int, reporter_name: str, reason: str) -> None:
    """Best-effort email to every admin - a report must still be recorded
    even if this fails or email isn't configured, so any error here is
    logged and swallowed rather than raised."""
    try:
        with get_session() as db:
            admin_emails = [u.email for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admin_emails:
            return
        subject = f"Malita: new report on a {target_type}"
        body = (
            f"{reporter_name} reported a {target_type} (#{target_id}) on the Collaboration Forum.\n\n"
            f"Reason given: {reason or '(no reason given)'}\n\n"
            f"Review it in the app's Moderation queue: {APP_BASE_URL}"
        )
        for email in admin_emails:
            send_email(email, subject, body)
    except Exception:
        logger.exception("Failed to notify admins of a new Collaboration Forum report")


def list_open_reports() -> list[dict]:
    """Admin moderation queue - unresolved reports, newest first, with
    enough of the reported content inlined that an admin can judge it
    without a second lookup."""
    with get_session() as db:
        reports = (
            db.query(CollabReport)
            .filter(CollabReport.resolved.is_(False))
            .order_by(CollabReport.created_at.desc())
            .all()
        )
        result = []
        for r in reports:
            if r.target_type == "question":
                target = db.query(CollabQuestion).filter(CollabQuestion.id == r.target_id).first()
                preview = f"{target.title} — {target.body}" if target else "(question no longer exists)"
                already_hidden = target.is_hidden if target else True
            else:
                target = db.query(CollabAnswer).filter(CollabAnswer.id == r.target_id).first()
                preview = target.body if target else "(answer no longer exists)"
                already_hidden = target.is_hidden if target else True

            reporter = db.query(User).filter(User.id == r.reporter_id).first()
            result.append({
                "id": r.id, "target_type": r.target_type, "target_id": r.target_id,
                "reason": r.reason, "created_at": r.created_at,
                "preview": (preview or "")[:300],
                "already_hidden": already_hidden,
                "reporter_name": reporter.name if reporter else "Unknown",
            })
        return result


def resolve_report(report_id: int, action: str, notify_reporter: bool = False, note: str = "") -> None:
    """Admin action: "hide" the reported content, "delete" it outright, or
    "dismiss" the report with no action - then mark the report resolved
    either way (dismissing a report never un-hides/restores content
    another still-open report flagged).

    Deleting a question also deletes its answers; deleting a top-level
    answer also deletes its direct replies (replies-to-replies don't
    exist - see create_answer's one-level cap).

    If notify_reporter is set, best-effort emails the reporter the
    outcome plus the optional admin note - never raises on its own, since
    the moderation action itself must still succeed either way."""
    if action not in ("hide", "delete", "dismiss"):
        raise ValueError("Unknown moderation action.")

    with get_session() as db:
        report = db.query(CollabReport).filter(CollabReport.id == report_id).first()
        if not report:
            raise ValueError("That report no longer exists.")
        target_type, target_id, reporter_id = report.target_type, report.target_id, report.reporter_id

        if action == "hide":
            if target_type == "question":
                target = db.query(CollabQuestion).filter(CollabQuestion.id == target_id).first()
            else:
                target = db.query(CollabAnswer).filter(CollabAnswer.id == target_id).first()
            if target:
                target.is_hidden = True
        elif action == "delete":
            if target_type == "question":
                db.query(CollabAnswer).filter(CollabAnswer.question_id == target_id).delete()
                db.query(CollabQuestion).filter(CollabQuestion.id == target_id).delete()
            else:
                db.query(CollabAnswer).filter(CollabAnswer.parent_id == target_id).delete()
                db.query(CollabAnswer).filter(CollabAnswer.id == target_id).delete()

        report.resolved = True

    if notify_reporter:
        _notify_reporter_of_outcome(reporter_id, target_type, action, note)


def _notify_reporter_of_outcome(reporter_id: int, target_type: str, action: str, note: str) -> None:
    try:
        with get_session() as db:
            reporter = db.query(User).filter(User.id == reporter_id).first()
            reporter_email = reporter.email if reporter else None
        if not reporter_email:
            return
        outcome = _ACTION_OUTCOME.get(action, action)
        body = (
            f"Thanks for reporting a {target_type} on the Malita Collaboration Forum. "
            f"After review, it was {outcome}."
        )
        note = (note or "").strip()
        if note:
            body += f"\n\nNote from the admin: {note}"
        send_email(reporter_email, "Update on your Collaboration Forum report", body)
    except Exception:
        logger.exception("Failed to notify reporter %s of a report outcome", reporter_id)

"""
Malita (Pty) Ltd — Collaborate: a Learner/Premium Q&A board where
learners can post a question and help each other answer it, grouped by
Subject/Topic same as everywhere else in the app.

Deliberately async (no chat/real-time), and deliberately simple: no
voting, no accepted-answer marking, no notifications - just post,
reply, and (if something's wrong) report it for an admin to review.
"""

import datetime as dt

from .db import get_session, CollabQuestion, CollabAnswer, CollabReport, User


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
            {"id": a.id, "body": a.body, "answerer_name": name, "created_at": a.created_at}
            for a, name in answer_rows
        ]
        return {
            "id": q.id, "subject": q.subject, "topic": q.topic,
            "title": q.title, "body": q.body,
            "asker_name": asker_name, "created_at": q.created_at,
            "answers": answers,
        }


def create_answer(question_id: int, user_id: int, body: str) -> int:
    body = (body or "").strip()
    if not body:
        raise ValueError("Please write out your answer.")

    with get_session() as db:
        exists = db.query(CollabQuestion).filter(
            CollabQuestion.id == question_id, CollabQuestion.is_hidden.is_(False)
        ).first()
        if not exists:
            raise ValueError("That question no longer exists.")

        a = CollabAnswer(question_id=question_id, user_id=user_id, body=body)
        db.add(a)
        db.flush()
        return a.id


def report_content(target_type: str, target_id: int, reporter_id: int, reason: str = "") -> None:
    if target_type not in ("question", "answer"):
        raise ValueError("Unknown content type to report.")

    with get_session() as db:
        db.add(CollabReport(
            target_type=target_type, target_id=target_id,
            reporter_id=reporter_id, reason=(reason or "").strip()[:500],
        ))


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


def resolve_report(report_id: int, hide_content: bool) -> None:
    """Admin action: optionally hide the reported content, then mark this
    report resolved either way (dismissing a report never un-hides
    content another still-open report flagged)."""
    with get_session() as db:
        report = db.query(CollabReport).filter(CollabReport.id == report_id).first()
        if not report:
            raise ValueError("That report no longer exists.")

        if hide_content:
            if report.target_type == "question":
                target = db.query(CollabQuestion).filter(CollabQuestion.id == report.target_id).first()
            else:
                target = db.query(CollabAnswer).filter(CollabAnswer.id == report.target_id).first()
            if target:
                target.is_hidden = True

        report.resolved = True

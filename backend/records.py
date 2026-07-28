from .db import get_session, SolvedQuestion


def get_recent_solved(user_id: int, limit: int = 25):
    """Most recent solved-question records for this user, newest first —
    used to show a learner (or admin) their own activity history."""
    with get_session() as db:
        rows = (
            db.query(SolvedQuestion)
            .filter(SolvedQuestion.user_id == user_id)
            .order_by(SolvedQuestion.solved_at.desc())
            .limit(limit)
            .all()
        )
        # Detach the plain values we need before the session closes.
        return [
            {
                "source": r.source, "paper": r.paper, "topic": r.topic,
                "question": r.question, "solved_at": r.solved_at,
            }
            for r in rows
        ]


def record_solved_question(user_id: int, source: str, paper: str = None,
                            topic: str = None, question: str = None) -> None:
    """Log one solved question for progress tracking/reporting.

    source: "ai_tutor" or "practice".
    Truncates `question` defensively — it's typically a short expression or
    LaTeX snippet, not free-form text, but nothing here should ever be able
    to blow up on an unexpectedly long value.
    """
    with get_session() as db:
        db.add(SolvedQuestion(
            user_id=user_id,
            source=source,
            paper=paper,
            topic=topic,
            question=(question or "")[:2000],
        ))

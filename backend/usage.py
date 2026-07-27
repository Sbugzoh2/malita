import datetime as dt

from .db import get_session, UsageLog
from .tiers import daily_limit


def get_today_count(user_id: int) -> int:
    today = dt.date.today()
    with get_session() as db:
        row = db.query(UsageLog).filter(
            UsageLog.user_id == user_id, UsageLog.usage_date == today
        ).first()
        return row.solve_count if row else 0


def can_solve(user_id: int, tier: str) -> tuple[bool, str]:
    """Returns (allowed, message_if_blocked)."""
    limit = daily_limit(tier)
    if limit is None:
        return True, ""
    used = get_today_count(user_id)
    if used >= limit:
        return False, (
            f"You've used all {limit} free AI Tutor solves for today. "
            "Upgrade to Learner or Premium for unlimited solves, or come back tomorrow!"
        )
    return True, ""


def record_solve(user_id: int) -> None:
    today = dt.date.today()
    with get_session() as db:
        row = db.query(UsageLog).filter(
            UsageLog.user_id == user_id, UsageLog.usage_date == today
        ).first()
        if row:
            row.solve_count += 1
        else:
            db.add(UsageLog(user_id=user_id, usage_date=today, solve_count=1))

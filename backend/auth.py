"""
Malita (Pty) Ltd — Authentication.

Simple, dependency-light email/password auth using bcrypt. No JWT/session
tokens needed since Streamlit's own session_state already keeps the logged
-in user tied to that browser session; we just need safe password storage
and lookup here.
"""

import re
import secrets
import datetime as dt
import bcrypt

from .db import get_session, User, Subscription, PasswordReset

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESET_TOKEN_VALID_MINUTES = 60


class AuthError(Exception):
    pass


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # malformed hash in DB - never crash the login flow over it
        return False


def register_user(name: str, email: str, password: str, school: str = "",
                   province: str = "", city_town: str = "") -> dict:
    name = (name or "").strip()
    email = (email or "").strip().lower()
    province = (province or "").strip()
    city_town = (city_town or "").strip()

    if not name:
        raise AuthError("Please enter your name.")
    if not EMAIL_RE.match(email):
        raise AuthError("Please enter a valid email address.")
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters long.")
    if not province:
        raise AuthError("Please select your province.")
    if not city_town:
        raise AuthError("Please enter your city or town.")

    with get_session() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise AuthError("An account with this email already exists. Try logging in instead.")

        user = User(
            name=name,
            email=email,
            password_hash=_hash_password(password),
            school=school.strip() if school else None,
            province=province,
            city_town=city_town,
        )
        db.add(user)
        db.flush()  # get user.id before commit

        # Every new signup starts on the Free tier automatically.
        sub = Subscription(user_id=user.id, tier="free", status="active")
        db.add(sub)
        db.flush()

        return {"id": user.id, "name": user.name, "email": user.email}


def login_user(email: str, password: str) -> dict:
    email = (email or "").strip().lower()

    with get_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not _verify_password(password, user.password_hash):
            raise AuthError("Incorrect email or password.")

        tier = user.subscription.tier if user.subscription else "free"
        status = user.subscription.status if user.subscription else "active"

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "tier": tier,
            "subscription_status": status,
            "is_admin": user.is_admin,
        }


def get_user_tier(user_id: int) -> str:
    """Live lookup — always call this before gating a feature, rather than
    trusting a cached tier in session_state, since a payment/cancellation
    could have changed it since login."""
    with get_session() as db:
        user = db.query(User).get(user_id)
        if not user or not user.subscription:
            return "free"
        if user.subscription.status != "active":
            return "free"
        return user.subscription.tier


def is_user_admin(user_id: int) -> bool:
    """Live lookup of the is_admin flag — checked fresh on every run (same
    reasoning as get_user_tier) so a change made via set_admin.py takes
    effect immediately without needing to log out and back in."""
    with get_session() as db:
        user = db.query(User).get(user_id)
        return bool(user and user.is_admin)


def create_password_reset(email: str):
    """Generate a one-time reset token for this email, valid for one hour.
    Returns the token, or None if no account matches — callers should show
    the SAME message either way so this can't be used to enumerate which
    emails are registered."""
    email = (email or "").strip().lower()
    with get_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None

        token = secrets.token_urlsafe(32)
        db.add(PasswordReset(
            user_id=user.id,
            token=token,
            expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=RESET_TOKEN_VALID_MINUTES),
        ))
        return token


def reset_password(token: str, new_password: str) -> None:
    """Consume a reset token and set a new password. Raises AuthError on any
    invalid/expired/already-used token, or a too-short new password."""
    if len(new_password) < 8:
        raise AuthError("Password must be at least 8 characters long.")

    with get_session() as db:
        reset = db.query(PasswordReset).filter(PasswordReset.token == token).first()
        if not reset or reset.used or reset.expires_at < dt.datetime.utcnow():
            raise AuthError("This reset link is invalid or has expired. Please request a new one.")

        user = db.query(User).get(reset.user_id)
        if not user:
            raise AuthError("This reset link is invalid or has expired. Please request a new one.")

        user.password_hash = _hash_password(new_password)
        reset.used = True

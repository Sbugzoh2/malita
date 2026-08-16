"""
Malita (Pty) Ltd — Database layer.

Uses SQLAlchemy so the SAME code works with:
  - SQLite (default, zero setup — fine for early launch / low traffic)
  - Postgres / Supabase (just change DATABASE_URL — recommended once you have
    real paying users, since SQLite files don't survive redeploys on most
    hosting platforms and don't handle concurrent writers well)

Set DATABASE_URL in your environment / .env file, e.g.:
  DATABASE_URL=sqlite:///malita.db
  DATABASE_URL=postgresql+psycopg2://user:password@host:5432/malita
"""

import os
import datetime as dt
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Date,
    ForeignKey, UniqueConstraint, LargeBinary
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///malita.db")

# check_same_thread=False is required for SQLite + Streamlit's threading model
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()

TIERS = ("free", "learner", "premium")

SA_PROVINCES = (
    "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
    "Mpumalanga", "Northern Cape", "North West", "Western Cape",
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    school = Column(String(255), nullable=True)
    province = Column(String(50), nullable=True, index=True)
    city_town = Column(String(120), nullable=True, index=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    subscription = relationship(
        "Subscription", back_populates="user", uselist=False,
        cascade="all, delete-orphan"
    )
    usage_logs = relationship(
        "UsageLog", back_populates="user", cascade="all, delete-orphan"
    )
    solved_questions = relationship(
        "SolvedQuestion", back_populates="user", cascade="all, delete-orphan"
    )
    password_resets = relationship(
        "PasswordReset", back_populates="user", cascade="all, delete-orphan"
    )
    api_tokens = relationship(
        "ApiToken", back_populates="user", cascade="all, delete-orphan"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    tier = Column(String(20), default="free", nullable=False)  # free | learner | premium
    status = Column(String(20), default="active", nullable=False)  # active | cancelled | past_due
    payfast_token = Column(String(255), nullable=True)  # recurring billing token from PayFast
    m_payment_id = Column(String(64), nullable=True)  # our own reference sent to PayFast
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    user = relationship("User", back_populates="subscription")


class UsageLog(Base):
    """Tracks daily AI Tutor solve counts, used to enforce the Free tier limit."""
    __tablename__ = "usage_logs"
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_user_date"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    usage_date = Column(Date, default=dt.date.today, nullable=False)
    solve_count = Column(Integer, default=0)

    user = relationship("User", back_populates="usage_logs")


class SolvedQuestion(Base):
    """One row per question a learner solves, from either the AI Tutor or
    Practice Questions mode — kept for progress tracking / reporting
    (e.g. which topics a learner struggles with or practises most)."""
    __tablename__ = "solved_questions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source = Column(String(20), nullable=False)  # "ai_tutor" | "practice"
    paper = Column(String(20), nullable=True)     # "Paper 1" | "Paper 2"
    topic = Column(String(60), nullable=True)
    question = Column(String, nullable=True)      # the question text/expression
    solved_at = Column(DateTime, default=dt.datetime.utcnow)

    user = relationship("User", back_populates="solved_questions")


class PasswordReset(Base):
    """One-time password-reset tokens. A row is created when a learner
    requests a reset and consumed (used=True) the first time it's redeemed;
    expires_at bounds how long a link stays valid."""
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

    user = relationship("User", back_populates="password_resets")


class ApiToken(Base):
    """Bearer tokens for the native app (React Native) and any other
    stateless HTTP client - the Streamlit app doesn't need these since it
    already keeps the logged-in user in its own server-side session_state.
    Deliberately simple (an opaque random token, no JWT/expiry logic) to
    match this codebase's existing token pattern (see PasswordReset);
    revoke by deleting the row rather than by expiry."""
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_tokens")


class PastPaper(Base):
    """A real past exam paper (PDF) stored in the DB so the Past Papers
    Library can serve them directly — separate from the AI Tutor's
    upload-and-solve PDF flow, which never persists what a learner
    uploads. file_data holds the raw PDF bytes; for this library's scale
    (tens, maybe ~100 papers) storing them in the same Postgres database
    is simpler than standing up a separate object-storage service."""
    __tablename__ = "past_papers"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)       # e.g. "November 2021"
    subject = Column(String(60), default="Mathematics", nullable=False)
    grade = Column(Integer, default=12, nullable=False)
    year = Column(Integer, nullable=False, index=True)
    month = Column(String(20), nullable=True)          # e.g. "November"
    paper_number = Column(Integer, nullable=False)      # 1 or 2
    variant = Column(String(80), default="English", nullable=False)  # e.g. "Afrikaans/English (Bilingual)"
    file_name = Column(String(255), nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime, default=dt.datetime.utcnow)


class WebhookEvent(Base):
    """Raw log of every PayFast ITN we receive — invaluable for support/disputes."""
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True)
    received_at = Column(DateTime, default=dt.datetime.utcnow)
    payload = Column(String)  # JSON-encoded raw POST body
    signature_valid = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)


def init_db():
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

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
    ForeignKey, UniqueConstraint
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

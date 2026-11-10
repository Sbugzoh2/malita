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
    ForeignKey, UniqueConstraint, LargeBinary, Float
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
    # Nullable so existing rows (predating ID-number collection) stay valid -
    # register_user() requires it for every new signup, deriving date_of_birth
    # from it so learners don't type both.
    id_number = Column(String(13), nullable=True, unique=True, index=True)
    date_of_birth = Column(Date, nullable=True)
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
    login_events = relationship(
        "LoginEvent", back_populates="user", cascade="all, delete-orphan"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    tier = Column(String(20), default="free", nullable=False)  # free | learner | premium
    status = Column(String(20), default="active", nullable=False)  # active | cancelled | past_due
    # Set when a learner downgrades to a lower tier mid-cycle - they keep
    # `tier`'s access (already paid for) until current_period_end, at
    # which point get_user_tier() applies this and clears it. See
    # backend/auth.py's schedule_downgrade().
    pending_tier = Column(String(20), nullable=True)
    # Which checkout the CURRENT tier was bought through - decides whether
    # cancellation goes through PayFast's API or has to be done in the Play
    # Store app (Google doesn't let us cancel a Play-billed subscription on
    # the user's behalf). See backend/google_play.py for the Play Billing side.
    payment_provider = Column(String(20), default="payfast", nullable=False)  # payfast | play_billing
    payfast_token = Column(String(255), nullable=True)  # recurring billing token from PayFast
    m_payment_id = Column(String(64), nullable=True)  # our own reference sent to PayFast
    google_purchase_token = Column(String(500), nullable=True)  # Play Billing purchase token
    google_product_id = Column(String(100), nullable=True)  # Play Console subscription product id
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


class LoginEvent(Base):
    """One row per successful login, for auditing/analytics (e.g. active-user
    counts, detecting unusual login patterns) — logged_at carries both the
    date and time; source distinguishes the Streamlit web app from the
    native mobile app, since both funnel through the same login_user()."""
    __tablename__ = "login_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    logged_in_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    source = Column(String(20), nullable=True)  # "web" | "api"

    user = relationship("User", back_populates="login_events")


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
    exam_series = Column(String(60), default="November (Final)", nullable=False)  # e.g. "June", "Trial", "March/April"
    document_type = Column(String(20), default="Question Paper", nullable=False)  # "Question Paper" | "Memo"
    paper_number = Column(Integer, nullable=False)      # 1 or 2
    variant = Column(String(80), default="English", nullable=False)  # e.g. "Afrikaans/English (Bilingual)"
    file_name = Column(String(255), nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime, default=dt.datetime.utcnow)


class CollabQuestion(Base):
    """A learner-posted question on the Collaborate board - Learner/Premium
    only (see can_use_collab). Kept separate from SolvedQuestion, which is
    just a private per-user progress log, not something other learners
    ever see."""
    __tablename__ = "collab_questions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String(60), nullable=False)  # "Mathematics" | "Physical Sciences"
    topic = Column(String(60), nullable=True)
    title = Column(String(200), nullable=False)
    body = Column(String, nullable=False)
    # Set by an admin after reviewing a report - hidden posts are excluded
    # from every learner-facing query but kept in the DB (not deleted) so
    # the report queue still has something to review.
    is_hidden = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class CollabAnswer(Base):
    """One reply to a CollabQuestion."""
    __tablename__ = "collab_answers"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("collab_questions.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(String, nullable=False)
    # NULL = a top-level answer to the question. Set = a reply to that
    # specific top-level answer's "sub-thread" - deliberately capped at
    # one level deep (see create_answer's parent-of-a-reply check), so a
    # reply's parent is always a top-level answer, never another reply.
    parent_id = Column(Integer, ForeignKey("collab_answers.id"), nullable=True, index=True)
    is_hidden = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class CollabReport(Base):
    """A learner's report against one question or answer, queued for
    manual admin review (see backend/collab.py) - nothing is auto-hidden,
    an admin always makes the call."""
    __tablename__ = "collab_reports"

    id = Column(Integer, primary_key=True)
    target_type = Column(String(20), nullable=False)  # "question" | "answer"
    target_id = Column(Integer, nullable=False)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    resolved = Column(Boolean, default=False)


class GooglePlayChoiceEvent(Base):
    """Logs every time a learner picks the alternative-billing option
    (PayFast) in Google's own User Choice Billing screen on Android.

    Google requires the externalTransactionToken be reported to their Play
    Developer API (externaltransactions.createexternaltransaction) within
    24 hours of the user's choice - this table just records the token so
    nothing is lost; reported_to_google flips true once that follow-up API
    call is wired up and actually made. That call is NOT implemented yet
    (see backend/google_play.py) since this code path can't even fire
    until Google approves Malita's User Choice Billing enrollment - safer
    to log now and finish the reporting call once it's possible to test
    against a real, approved enrollment than to guess at the request shape."""
    __tablename__ = "google_play_choice_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    received_at = Column(DateTime, default=dt.datetime.utcnow)
    external_transaction_token = Column(String(500), nullable=True)
    product_ids = Column(String(500), nullable=True)
    reported_to_google = Column(Boolean, default=False)


class WebhookEvent(Base):
    """Raw log of every PayFast ITN we receive — invaluable for support/disputes."""
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True)
    received_at = Column(DateTime, default=dt.datetime.utcnow)
    payload = Column(String)  # JSON-encoded raw POST body
    signature_valid = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)


class TutorAccount(Base):
    """A tutor who applied to offer paid 1-on-1 tutoring through Malita -
    entirely separate from the learner `User` table since tutors are a
    different kind of actor with their own login, vetting, and payout
    details, not a subscription/tier.

    V1 VETTING IS EXPLICITLY MANUAL, NOT AUTOMATED - a deliberate decision,
    not a placeholder waiting to be filled in by accident:
      - id_verification_note, matric_certificate_note, and
        bank_account_note are free-text fields an admin reviews BY EYE
        (e.g. a link to an ID photo / NSC certificate the tutor emailed
        or uploaded somewhere external, or bank details for a manual EFT
        payout) - there is NO file-upload storage built for this (that
        needs a real infra decision - S3 or a persistent disk - a plain
        local file write would get wiped on every redeploy) and NO
        automated verification call to any third party.
      - The self-reported matric_percentage on TutorSubject is NOT
        independently confirmed against Umalusi/SAQA (the only
        authoritative verifiers of an NSC certificate) in v1. Automating
        that was researched and deliberately deferred: SAQA's own
        2026-2028 tariff lists a R3,512 minimum per API submission, and
        Umalusi has no public self-serve API at all - not worth the cost
        before real tutor-applicant volume justifies it. When it is,
        Umalusi/SAQA are the matric-verification path, Smile ID/
        iiDENTIFii are the ID-verification path, and MIE is the
        criminal-background-check path (MIE may also bundle qualification
        verification, worth asking about in one conversation).
    An admin manually cross-checks these notes before calling
    approve_tutor() - nothing here calls out to a third party automatically."""
    __tablename__ = "tutor_accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=True)
    id_number = Column(String(13), nullable=True)
    id_verification_note = Column(String, nullable=True)
    matric_certificate_note = Column(String, nullable=True)
    # Storage paths (Supabase Storage, private bucket) for an actually
    # uploaded document, set when the applicant attaches a file - distinct
    # from the free-text *_note fields above, which still work as a
    # fallback (e.g. a link to somewhere else) if storage isn't set up or
    # the applicant didn't attach anything. See backend/storage.py.
    id_document_path = Column(String, nullable=True)
    matric_certificate_path = Column(String, nullable=True)
    bank_account_note = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    # pending_review | approved | rejected | suspended
    status = Column(String(20), default="pending_review", nullable=False)
    admin_notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    subjects = relationship(
        "TutorSubject", back_populates="tutor", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "TutoringSessionRequest", back_populates="tutor"
    )


class TutorSubject(Base):
    """One subject a tutor is approved to teach, with the matric result
    that qualifies them (Malita's stated minimum is 65%) and their asking
    rate, used as a starting point when an admin sets a session's price."""
    __tablename__ = "tutor_subjects"

    id = Column(Integer, primary_key=True)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=False)
    subject = Column(String(60), nullable=False)  # "Mathematics" | "Physical Sciences"
    matric_percentage = Column(Float, nullable=False)
    topics = Column(String, nullable=True)  # optional comma-separated topic focus
    hourly_rate_zar = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)

    tutor = relationship("TutorAccount", back_populates="subjects")


class TutoringSessionRequest(Base):
    """A learner's request for a paid 1-on-1 tutoring session - billed
    separately from the subscription, so available regardless of tier.
    v1 matching is manual (an admin picks a tutor and sets the price/time)
    rather than an automated marketplace algorithm - see backend/tutoring.py.

    status flow: requested -> matched -> awaiting_payment -> confirmed
    (the learner's payment cleared) -> completed, or cancelled at any point
    before confirmed."""
    __tablename__ = "tutoring_session_requests"

    id = Column(Integer, primary_key=True)
    learner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String(60), nullable=False)
    topic = Column(String(60), nullable=True)
    preferred_times_note = Column(String, nullable=True)
    status = Column(String(20), default="requested", nullable=False)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    price_zar = Column(Float, nullable=True)
    # Snapshot of the platform's cut % at match time, so a later change to
    # the global rate never retroactively changes an already-matched session.
    platform_cut_percent = Column(Float, nullable=True)
    m_payment_id = Column(String(64), nullable=True, unique=True)
    scheduled_at = Column(DateTime, nullable=True)
    admin_notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    matched_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    learner = relationship("User")
    tutor = relationship("TutorAccount", back_populates="sessions")
    payout = relationship(
        "TutoringPayout", back_populates="session", uselist=False,
        cascade="all, delete-orphan"
    )


class TutoringPayout(Base):
    """What's owed to a tutor for one completed, paid session - v1 payouts
    are manual EFT, so this is a tracking ledger for admins, not an
    automated transfer. One row per session."""
    __tablename__ = "tutoring_payouts"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("tutoring_session_requests.id"), unique=True, nullable=False)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=False)
    amount_zar = Column(Float, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending | paid
    payment_reference = Column(String(120), nullable=True)
    paid_by_admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

    session = relationship("TutoringSessionRequest", back_populates="payout")


def _ensure_column(table_name: str, column_name: str, ddl_type: str) -> None:
    """Add one column to an already-existing table if it's missing.

    Base.metadata.create_all() only creates tables that don't exist yet -
    it never alters a table that's already there, so a column added to a
    model after the table has been created in a live database (as
    happened with collab_answers.parent_id) is silently never applied,
    and every query touching that column then fails at runtime instead
    of at deploy time. This is a deliberately minimal self-healing check
    (not a full migration framework, which this app's scale doesn't need)
    for exactly that mistake - called once at startup, safe to call every
    time since it's a no-op once the column exists."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return  # create_all() will create the whole table, column included
    existing = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name in existing:
        return
    with engine.begin() as conn:
        conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}")


def _migrate_removed_tier(old_tier: str, new_tier: str) -> None:
    """One-time data fix for when a tier is removed/merged into another -
    e.g. Super Premium was merged into Premium. Without this, any learner
    whose stored tier/pending_tier is still the old (now-nonexistent) tier
    string would crash TIER_CONFIG[effective_tier] lookups elsewhere. Safe
    to call every startup since it's a no-op once no rows match."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if "subscriptions" not in inspector.get_table_names():
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE subscriptions SET tier = :new WHERE tier = :old"),
            {"old": old_tier, "new": new_tier},
        )
        conn.execute(
            text("UPDATE subscriptions SET pending_tier = :new WHERE pending_tier = :old"),
            {"old": old_tier, "new": new_tier},
        )


def init_db():
    Base.metadata.create_all(engine)
    _ensure_column("collab_answers", "parent_id", "INTEGER")
    _ensure_column("collab_questions", "is_edited", "BOOLEAN DEFAULT FALSE")
    _ensure_column("collab_answers", "is_edited", "BOOLEAN DEFAULT FALSE")
    _ensure_column("subscriptions", "payment_provider", "VARCHAR(20) DEFAULT 'payfast'")
    _ensure_column("subscriptions", "google_purchase_token", "VARCHAR(500)")
    _ensure_column("subscriptions", "google_product_id", "VARCHAR(100)")
    _ensure_column("subscriptions", "pending_tier", "VARCHAR(20)")
    _ensure_column("tutor_accounts", "matric_certificate_note", "VARCHAR")
    _ensure_column("tutor_accounts", "id_document_path", "VARCHAR")
    _ensure_column("tutor_accounts", "matric_certificate_path", "VARCHAR")
    _migrate_removed_tier("super_premium", "premium")


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

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

# Which population an account serves. "high_school" is the original Malita
# product (AI Tutor, past papers, OCR, subscription tiers, PLUS tutoring).
# "higher_ed" (university/college) accounts get ONLY the tutoring
# marketplace - see app.py's feature gating and backend/tutoring.py's
# higher-ed request/matching path.
ACCOUNT_TYPES = ("high_school", "higher_ed")

# A module's year level, used for the "must be at least one year ahead"
# tutoring-eligibility rule (see TutorHigherEdModule) - an integer so
# eligibility is a plain comparison, not a lookup table.
YEAR_LEVEL_LABELS = {
    1: "1st Year", 2: "2nd Year", 3: "3rd Year", 4: "4th Year / Honours",
    5: "Postgraduate (Masters/Doctoral)",
}


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
    # "high_school" (default, backward-compatible with every existing row)
    # or "higher_ed" - decided once at signup, see register_user(). Gates
    # which features the account can reach (see app.py).
    account_type = Column(String(20), default="high_school", nullable=False)
    # Only set for higher_ed accounts - which institution/qualification/
    # year the learner is studying, used both to show relevant modules
    # first and (year_of_study) for the tutor-matching eligibility rule.
    higher_ed_institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    higher_ed_qualification_id = Column(Integer, ForeignKey("qualifications.id"), nullable=True)
    # "Other" escape hatch instead of higher_ed_qualification_id, for when
    # the learner's real qualification isn't in the catalog - set means
    # higher_ed_qualification_id is NULL (custom path); NULL means
    # behavior is exactly the catalog-FK path above, unchanged.
    higher_ed_qualification_custom_name = Column(String(200), nullable=True)
    higher_ed_year_of_study = Column(Integer, nullable=True)
    student_number = Column(String(50), nullable=True)
    is_admin = Column(Boolean, default=False)
    # Rare, high-trust override (see backend/set_cross_segment_access.py) -
    # lets ONE account see both the high_school AND higher_ed experiences
    # at once, regardless of its own account_type. Deliberately not a
    # general "both" account_type: that would mean reworking every
    # account_type-gated screen's assumption that it's one or the other
    # for every learner, not just this one.
    cross_segment_access = Column(Boolean, default=False)
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


class Institution(Base):
    """A university/college/TVET college - admin-managed (see
    backend/tutoring.py's catalog functions), not pre-populated with every
    South African institution, since that list is large and changes over
    time. An admin adds institutions/qualifications/modules as real
    learners/tutors need them."""
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    qualifications = relationship(
        "Qualification", back_populates="institution", cascade="all, delete-orphan"
    )


class Qualification(Base):
    """A degree/diploma offered by one Institution, e.g. 'BSc Computer
    Science' at University of Pretoria - modules belong to one of these."""
    __tablename__ = "qualifications"
    __table_args__ = (UniqueConstraint("institution_id", "name", name="uq_qualification_institution_name"),)

    id = Column(Integer, primary_key=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    institution = relationship("Institution", back_populates="qualifications")
    modules = relationship("Module", back_populates="qualification", cascade="all, delete-orphan")


class Module(Base):
    """One module/course within a Qualification, tagged with the year it's
    taken - year_level is what enforces "a tutor must be at least one
    year ahead of the module they tutor" (see TutorHigherEdModule)."""
    __tablename__ = "modules"
    __table_args__ = (UniqueConstraint("qualification_id", "name", name="uq_module_qualification_name"),)

    id = Column(Integer, primary_key=True)
    qualification_id = Column(Integer, ForeignKey("qualifications.id"), nullable=False)
    name = Column(String(200), nullable=False)
    year_level = Column(Integer, nullable=False)  # 1-5, see YEAR_LEVEL_LABELS
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    qualification = relationship("Qualification", back_populates="modules")


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
    # A one-page CV, same optional-upload-with-free-text-fallback pattern
    # as the ID/matric certificate fields above.
    cv_note = Column(String, nullable=True)
    cv_document_path = Column(String, nullable=True)
    # Free text (e.g. "Weekdays after 16:00, Saturday mornings") - no
    # structured day/time picker in v1, since matching is already a manual
    # admin step (see backend/tutoring.py) where an admin reads this by eye.
    availability_note = Column(String, nullable=True)
    bank_account_note = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    # pending_review | approved | rejected | suspended - this is the
    # HIGH SCHOOL vetting status (kept as the original column name/meaning
    # so every pre-existing tutor and all of v1's code keeps working
    # unchanged). See higher_ed_status below for the separate, independent
    # higher-ed vetting track - a tutor applying for "Both" has two
    # statuses that can differ (e.g. approved for high school, still
    # pending_review for higher-ed).
    status = Column(String(20), default="pending_review", nullable=False)
    admin_notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)

    # Which segment(s) this tutor applied to teach - decided once at
    # application time (a tutor can later ask an admin to add the other
    # segment, but there's no self-service "add segment" flow in v1).
    wants_high_school = Column(Boolean, default=True, nullable=False)
    wants_higher_ed = Column(Boolean, default=False, nullable=False)

    # ---- Higher-ed vetting track (independent of the fields above) ----
    # NULL higher_ed_status means "never applied for this track" (distinct
    # from "pending_review", which means they applied and are waiting).
    higher_ed_status = Column(String(20), nullable=True)
    higher_ed_institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    higher_ed_qualification_id = Column(Integer, ForeignKey("qualifications.id"), nullable=True)
    # "Other" escape hatch instead of higher_ed_qualification_id, for when
    # the tutor's real qualification isn't in the catalog - set means
    # higher_ed_qualification_id is NULL and higher_ed_modules below holds
    # nothing (see TutorCustomHigherEdModule instead).
    higher_ed_qualification_custom_name = Column(String(200), nullable=True)
    # The tutor's OWN year of study (or, if higher_ed_qualification_complete,
    # the year they finished in) - gates which modules they're allowed to
    # add in TutorHigherEdModule (must be strictly ahead of the module's
    # own year_level).
    higher_ed_year_of_study = Column(Integer, nullable=True)
    higher_ed_qualification_complete = Column(Boolean, default=False, nullable=False)
    # Self-reported semester/final average (%) - Malita's stated minimum is
    # 65%, enforced at application time (see apply_as_tutor's higher-ed
    # path), same spirit as matric_percentage for high school but NOT
    # independently verified against the institution in v1 - same manual-
    # review-by-admin approach as matric_certificate_note.
    higher_ed_average = Column(Float, nullable=True)
    higher_ed_transcript_note = Column(String, nullable=True)
    # Uploaded documents, same optional-upload-with-free-text-fallback
    # pattern as id_document_path/matric_certificate_path above.
    # higher_ed_transcript_path is the academic transcript; qualification_
    # certificate_path is proof of completion, only relevant when
    # higher_ed_qualification_complete is True.
    higher_ed_transcript_path = Column(String, nullable=True)
    higher_ed_qualification_certificate_path = Column(String, nullable=True)
    higher_ed_reviewed_at = Column(DateTime, nullable=True)

    subjects = relationship(
        "TutorSubject", back_populates="tutor", cascade="all, delete-orphan"
    )
    higher_ed_modules = relationship(
        "TutorHigherEdModule", back_populates="tutor", cascade="all, delete-orphan"
    )
    higher_ed_custom_modules = relationship(
        "TutorCustomHigherEdModule", back_populates="tutor", cascade="all, delete-orphan"
    )
    # Explicit foreign_keys needed on both sides of this relationship
    # now that TutoringSessionRequest has a second FK to tutor_accounts
    # (preferred_tutor_id) - SQLAlchemy can no longer infer which column
    # this relationship is about.
    sessions = relationship(
        "TutoringSessionRequest", back_populates="tutor",
        foreign_keys="TutoringSessionRequest.tutor_id",
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


class TutorHigherEdModule(Base):
    """One catalog Module a higher-ed tutor declared/is approved to
    tutor - validated at creation time (module.year_level must be below
    the tutor's own higher_ed_year_of_study, or the tutor must have
    completed the qualification) so a first-year student can never be
    linked to a first-year module. See backend/tutoring.py's
    add_tutor_higher_ed_module."""
    __tablename__ = "tutor_higher_ed_modules"
    __table_args__ = (UniqueConstraint("tutor_id", "module_id", name="uq_tutor_module"),)

    id = Column(Integer, primary_key=True)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=False)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    is_active = Column(Boolean, default=True)

    tutor = relationship("TutorAccount", back_populates="higher_ed_modules")
    module = relationship("Module")


class TutorCustomHigherEdModule(Base):
    """A tutor's own free-text module entry when their qualification isn't
    in the catalog (see TutorAccount.higher_ed_qualification_custom_name) -
    same purpose as TutorHigherEdModule but for a module that has no
    catalog Module row to point at, so name/year_level are stored directly
    rather than as a foreign key. A request matched against one of these
    can't go through the normal tutor self-accept broadcast (see
    TutoringSessionRequest.is_custom_higher_ed) - it's admin-matched."""
    __tablename__ = "tutor_custom_higher_ed_modules"
    __table_args__ = (UniqueConstraint("tutor_id", "name", "year_level", name="uq_tutor_custom_module"),)

    id = Column(Integer, primary_key=True)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=False)
    name = Column(String(200), nullable=False)
    year_level = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    tutor = relationship("TutorAccount", back_populates="higher_ed_custom_modules")


class TutoringSessionRequest(Base):
    """A learner's request for a paid 1-on-1 tutoring session - billed
    separately from the subscription, so available regardless of tier.

    v2 matching is inDrive-style self-service: the LEARNER sets the price
    (and duration) when requesting, and ANY approved tutor who teaches
    that subject can accept it at that price - no admin has to pick a
    tutor or set a price first (an admin can still force-assign one as a
    manual override - see backend/tutoring.py's match_tutor_to_request -
    but that's no longer the primary path).

    status flow: requested (open, priced AND timed by the learner,
    visible to qualifying tutors) -> time_proposed (a tutor can't make
    the learner's exact time and proposed an alternative - see
    proposed_scheduled_at - awaiting the learner's approve/decline) ->
    back to requested if declined, or -> awaiting_payment if the learner
    approves (or a tutor accepted the original time directly) ->
    confirmed (the learner's payment cleared) -> completed (BOTH the
    learner and the tutor have independently confirmed the session
    actually happened and rated each other - see learner_confirmed_at/
    tutor_confirmed_at below; this is also when the payout row is
    created, not at payment time, so a no-show can't collect a payout).
    Two ways out besides completion: cancelled (either party withdrew a
    not-yet-accepted request, or cancelled an accepted one outside the
    24-hour cutoff - see backend/tutoring.py's withdraw_tutoring_request/
    cancel_accepted_session - cancelled_by/cancellation_reason record
    who and why), or lapsed (the learner never paid within
    PAYMENT_DEADLINE_HOURS of being matched - see
    backend/tutoring.py's _expire_lapsed_payments - a dead end requiring
    a fresh request, not reopened for other tutors automatically).

    scheduled_at is REQUIRED at request time (the learner picks an exact
    date/time, not a vague "preferred times" note) at least
    MIN_REQUEST_LEAD_HOURS ahead - see backend/tutoring.py's
    request_tutoring_session, which also enforces a minimum 60-minute
    duration and checks the learner isn't already booked within 15
    minutes of that slot. The same two checks (no double-booking,
    15-minute buffer) apply to a tutor accepting or proposing a time,
    though the lead-time minimum does NOT - a tutor's proposed
    alternative (and the learner's approval of it) counts as the
    "otherwise agreed" exception."""
    __tablename__ = "tutoring_session_requests"

    id = Column(Integer, primary_key=True)
    learner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # For a high-school request: an NSC subject name (e.g. "Mathematics").
    # For a higher-ed request (module_id set below): the module's own
    # display name, kept here too so every existing subject-string-based
    # display/notification code path keeps working unchanged.
    subject = Column(String(60), nullable=False)
    # NULL = a high-school request (matched by `subject` against
    # TutorSubject, as in v1). Set = a higher-ed request, matched by this
    # exact Module against TutorHigherEdModule instead - see
    # backend/tutoring.py's list_open_requests_for_tutor/
    # accept_tutoring_request for the branch.
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=True)
    # Set when the learner picked "Other" for their qualification/module
    # (no catalog Module row exists to self-accept-match against) - routed
    # to admin's manual force-match flow instead of the normal tutor
    # self-accept broadcast. subject still holds this module's display
    # name per the existing convention above, so every existing
    # subject-string display/notification code path keeps working
    # unchanged.
    custom_module_name = Column(String(200), nullable=True)
    is_custom_higher_ed = Column(Boolean, default=False, nullable=False)
    topic = Column(String(60), nullable=True)
    # Free-text extra context (e.g. "need help with proofs specifically")
    # - NOT where the learner's actual time goes anymore, that's the
    # required scheduled_at below. Column name kept as-is to avoid a
    # rename migration.
    preferred_times_note = Column(String, nullable=True)
    status = Column(String(20), default="requested", nullable=False)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=True)
    # Set when the learner picked a specific tutor from the directory
    # (see backend/tutoring.py's list_approved_tutors/request_tutoring_
    # session) instead of broadcasting to every qualifying tutor - while
    # set and status=="requested", only this tutor sees the request in
    # their open-requests queue. Left in place (not cleared) once
    # accepted, purely as a record of how the match happened.
    preferred_tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=True)
    # Set by the LEARNER at request time (not by an admin at match time,
    # as in v1) - this is the price a tutor accepts or doesn't.
    duration_minutes = Column(Integer, nullable=True)
    price_zar = Column(Float, nullable=True)
    # Snapshot of the platform's cut % at accept time, so a later change
    # to the global rate never retroactively changes an already-accepted
    # session's payout split.
    platform_cut_percent = Column(Float, nullable=True)
    m_payment_id = Column(String(64), nullable=True, unique=True)
    scheduled_at = Column(DateTime, nullable=True)
    # A tutor's proposed alternative to the learner's scheduled_at, set
    # by propose_new_time() while status is "time_proposed" - cleared
    # once the learner approves (scheduled_at is overwritten with this
    # value) or declines (this is cleared and the request reopens).
    proposed_scheduled_at = Column(DateTime, nullable=True)
    # The Google Meet link + Calendar event id generated once a tutor
    # accepts (see backend/google_calendar.py) - both nullable since Meet
    # creation can fail/not be configured yet, and the session itself
    # must never be blocked on that.
    meet_link = Column(String, nullable=True)
    calendar_event_id = Column(String, nullable=True)
    admin_notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    # Set the moment a tutor_id is assigned, whether via self-accept or
    # an admin's manual override - kept as "matched_at" rather than
    # renamed to "accepted_at" to avoid a DB column rename migration.
    matched_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    # Who initiated a cancellation ("learner" | "tutor" | "admin") and why
    # - distinct from admin_notes, which is admin's own free-text
    # commentary, not a party's stated reason for cancelling.
    cancelled_by = Column(String(20), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    # Set when _expire_lapsed_payments() auto-transitions an unpaid
    # awaiting_payment request to "lapsed" after PAYMENT_DEADLINE_HOURS.
    lapsed_at = Column(DateTime, nullable=True)
    # Each set the moment its one-time reminder email goes out (see
    # send_due_reminders() in backend/tutoring.py) - guards against
    # re-sending the same reminder on every polling pass.
    reminder_24h_sent_at = Column(DateTime, nullable=True)
    reminder_15m_sent_at = Column(DateTime, nullable=True)
    lapse_reminder_sent_at = Column(DateTime, nullable=True)
    # The tutor's own manually-recorded Meet link, submitted after the
    # session (see submit_session_recording in backend/tutoring.py) -
    # there's no API that can force a recording on a non-Google-Workspace
    # Meet call, so this is a tutor-submitted link, not an automated one.
    recording_link = Column(String, nullable=True)
    recording_shared_at = Column(DateTime, nullable=True)
    # Each side confirms independently that the session actually took
    # place and rates the other - completed_at/the payout only happen
    # once BOTH are set (see confirm_session_by_learner/
    # confirm_session_by_tutor in backend/tutoring.py).
    learner_confirmed_at = Column(DateTime, nullable=True)
    learner_rating = Column(Integer, nullable=True)  # 1-5, the learner's rating OF the tutor
    learner_rating_comment = Column(String, nullable=True)
    tutor_confirmed_at = Column(DateTime, nullable=True)
    tutor_rating = Column(Integer, nullable=True)  # 1-5, the tutor's rating OF the learner
    tutor_rating_comment = Column(String, nullable=True)

    learner = relationship("User")
    tutor = relationship("TutorAccount", back_populates="sessions", foreign_keys=[tutor_id])
    preferred_tutor = relationship("TutorAccount", foreign_keys=[preferred_tutor_id])
    module = relationship("Module")
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


class TutorApiToken(Base):
    """Bearer tokens for a tutor's own login to the native app - mirrors
    ApiToken, but scoped to tutor_accounts rather than users, since a
    tutor is a different kind of actor from a learner with an entirely
    separate login (see TutorAccount), not another row in the same users
    table."""
    __tablename__ = "tutor_api_tokens"

    id = Column(Integer, primary_key=True)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class TutorPasswordReset(Base):
    """One-time password-reset tokens for a tutor's own login - mirrors
    PasswordReset, but scoped to tutor_accounts since a tutor's password
    is entirely separate from any learner User row."""
    __tablename__ = "tutor_password_resets"

    id = Column(Integer, primary_key=True)
    tutor_id = Column(Integer, ForeignKey("tutor_accounts.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)


class GoogleCalendarCredentials(Base):
    """A single stored OAuth refresh token for the ONE Google account that
    "owns" every session's Calendar event/Meet link (see
    backend/google_calendar.py) - not per-tutor, not per-learner, just one
    row for the whole platform. One-time human consent (see
    /admin/google-calendar/connect) mints this; everything after that is
    silent server-side token refresh."""
    __tablename__ = "google_calendar_credentials"

    id = Column(Integer, primary_key=True)
    account_email = Column(String(255), nullable=True)
    refresh_token = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


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
    _ensure_column("tutor_accounts", "cv_note", "VARCHAR")
    _ensure_column("tutor_accounts", "cv_document_path", "VARCHAR")
    _ensure_column("tutor_accounts", "availability_note", "VARCHAR")
    _ensure_column("tutoring_session_requests", "meet_link", "VARCHAR")
    _ensure_column("tutoring_session_requests", "calendar_event_id", "VARCHAR")
    _ensure_column("tutoring_session_requests", "learner_confirmed_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "learner_rating", "INTEGER")
    _ensure_column("tutoring_session_requests", "learner_rating_comment", "VARCHAR")
    _ensure_column("tutoring_session_requests", "tutor_confirmed_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "tutor_rating", "INTEGER")
    _ensure_column("tutoring_session_requests", "tutor_rating_comment", "VARCHAR")
    _ensure_column("tutoring_session_requests", "proposed_scheduled_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "module_id", "INTEGER")
    _ensure_column("tutoring_session_requests", "preferred_tutor_id", "INTEGER")
    _ensure_column("tutoring_session_requests", "cancelled_by", "VARCHAR(20)")
    _ensure_column("tutoring_session_requests", "cancellation_reason", "VARCHAR")
    _ensure_column("tutoring_session_requests", "lapsed_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "reminder_24h_sent_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "reminder_15m_sent_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "lapse_reminder_sent_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "recording_link", "VARCHAR")
    _ensure_column("tutoring_session_requests", "recording_shared_at", "TIMESTAMP")
    _ensure_column("tutoring_session_requests", "custom_module_name", "VARCHAR(200)")
    _ensure_column("tutoring_session_requests", "is_custom_higher_ed", "BOOLEAN DEFAULT FALSE")
    _ensure_column("users", "account_type", "VARCHAR(20) DEFAULT 'high_school'")
    _ensure_column("users", "higher_ed_institution_id", "INTEGER")
    _ensure_column("users", "higher_ed_qualification_id", "INTEGER")
    _ensure_column("users", "higher_ed_qualification_custom_name", "VARCHAR(200)")
    _ensure_column("users", "higher_ed_year_of_study", "INTEGER")
    _ensure_column("users", "student_number", "VARCHAR(50)")
    _ensure_column("users", "cross_segment_access", "BOOLEAN DEFAULT FALSE")
    _ensure_column("tutor_accounts", "wants_high_school", "BOOLEAN DEFAULT TRUE")
    _ensure_column("tutor_accounts", "wants_higher_ed", "BOOLEAN DEFAULT FALSE")
    _ensure_column("tutor_accounts", "higher_ed_status", "VARCHAR(20)")
    _ensure_column("tutor_accounts", "higher_ed_institution_id", "INTEGER")
    _ensure_column("tutor_accounts", "higher_ed_qualification_id", "INTEGER")
    _ensure_column("tutor_accounts", "higher_ed_qualification_custom_name", "VARCHAR(200)")
    _ensure_column("tutor_accounts", "higher_ed_year_of_study", "INTEGER")
    _ensure_column("tutor_accounts", "higher_ed_qualification_complete", "BOOLEAN DEFAULT FALSE")
    _ensure_column("tutor_accounts", "higher_ed_average", "FLOAT")
    _ensure_column("tutor_accounts", "higher_ed_transcript_note", "VARCHAR")
    _ensure_column("tutor_accounts", "higher_ed_transcript_path", "VARCHAR")
    _ensure_column("tutor_accounts", "higher_ed_qualification_certificate_path", "VARCHAR")
    _ensure_column("tutor_accounts", "higher_ed_reviewed_at", "TIMESTAMP")
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

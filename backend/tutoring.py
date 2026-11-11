"""
Malita (Pty) Ltd — 1-on-1 Tutoring Marketplace (v1, deliberately manual).

Separate product from the subscription: a learner can request a paid
tutoring session regardless of their subscription tier, billed per-session
rather than through the recurring subscription. A tutor is a different
kind of actor from a learner (see backend.db.TutorAccount) with their own
application/vetting flow.

WHY V1 IS STILL MANUAL/SEMI-AUTOMATED IN PLACES:
  - Matching: inDrive-style self-service, not an admin-mediated step -
    the LEARNER sets the price (and duration) when requesting, and ANY
    approved tutor who actively teaches that subject can accept it at
    that price (see accept_tutoring_request). An admin can still
    force-assign a tutor as a manual override (match_tutor_to_request),
    but that's the exception path now, not the primary one.
  - Payouts: PayFast has no built-in split-payment/payout API to send a
    tutor their cut automatically. The learner's payment goes to Malita's
    own PayFast account same as a subscription payment; a TutoringPayout
    row just tracks what's owed so an admin can pay the tutor by manual
    EFT and mark it paid. Automating this needs a different payment
    processor with real marketplace/split-payout support - a decision
    deliberately deferred past v1.
  - VETTING (ID + matric certificate + background check): explicitly
    manual by design in v1, not a gap waiting to be noticed. id_verification_note,
    matric_certificate_note, and bank_account_note on TutorAccount are
    free-text fields an admin reviews by eye (e.g. a link to an ID photo
    or NSC certificate the tutor emailed or uploaded somewhere external) -
    nothing here calls out to a third party automatically. This was
    researched, not just skipped:
      - Matric certificate verification: only Umalusi (the body that
        actually issues NSC certificates) and SAQA can authoritatively
        confirm one, and neither has a cheap self-serve API - SAQA's own
        2026-2028 tariff lists a R3,512 MINIMUM per API submission, and
        Umalusi has no public API at all (contract/email only). Not
        worth the per-applicant cost before real volume.
      - ID verification: Smile ID (API-first, has a South Africa product
        checking the Home Affairs/DHA national ID database + selfie
        matching) and iiDENTIFii (a South African biometric-ID company)
        are the two candidates to get quotes from when this gets
        automated - neither publishes public pricing.
      - Criminal background checks: MIE (Managed Integrity Evaluation) is
        the established South African background-screening company,
        using SAPS' fingerprint system (AFIS), and works with companies
        as small as 2-3 people. MIE may also bundle qualification
        verification, which could cover two of these three needs through
        one vendor relationship.
    An admin manually cross-checks whatever the tutor submitted before
    calling approve_tutor() - this module never contacts Umalusi, SAQA,
    Smile ID, iiDENTIFii, or MIE on its own.

Minimum matric mark required to apply, per Malita's own stated policy -
checked here against the tutor's SELF-REPORTED number, not independently
confirmed against Umalusi/SAQA (see above).
"""

import datetime as dt
import logging
import secrets
import uuid

import sqlalchemy as sa

from .db import (
    get_session, User, TutorAccount, TutorSubject, TutoringSessionRequest,
    TutoringPayout, TutorApiToken, TutorPasswordReset,
    Institution, Qualification, Module, TutorHigherEdModule, YEAR_LEVEL_LABELS,
)
from . import storage as _storage
from . import google_calendar as _google_calendar
from .email_util import send_email

logger = logging.getLogger("malita.tutoring")

MIN_MATRIC_PERCENTAGE = 65.0
# Minimum self-reported semester/final average to apply as a higher-ed
# tutor - same bar as MIN_MATRIC_PERCENTAGE, kept as its own named
# constant since the two tracks are conceptually separate (one's a
# matric subject mark, the other a university/college average) even
# though Malita's policy happens to set them to the same number.
MIN_HIGHER_ED_AVERAGE = 65.0

# Default cut Malita takes from a session's price - snapshotted onto each
# TutoringSessionRequest at match time, so changing this later never
# retroactively alters an already-priced session.
DEFAULT_PLATFORM_CUT_PERCENT = 30.0

# Human-readable labels for the raw status strings stored in the DB -
# computed once here (list_tutor_applications/_serialize_request both
# attach a "*_label" field) so every client (web admin, mobile admin,
# anything built later) shows the same text instead of each one
# re-deriving its own Title-Case guess from the snake_case value.
TUTOR_STATUS_LABELS = {
    "pending_review": "Pending Review",
    "approved": "Approved",
    "rejected": "Rejected",
    "suspended": "Suspended",
}

SESSION_STATUS_LABELS = {
    "requested": "Waiting for a tutor to accept",
    "time_proposed": "Tutor proposed a new time — awaiting your approval",
    "admin_proposed": "An admin suggested this match — awaiting the tutor's confirmation",
    "awaiting_payment": "Accepted! Awaiting payment",
    "confirmed": "Paid — confirm once the session happens",
    "completed": "Completed",
    "cancelled": "Cancelled",
}

# A session must be at least this long, and no two of the same person's
# (learner's or tutor's) sessions may be scheduled with less than this
# many minutes between them - enforced by _check_schedule_conflict below
# at every point a time is set or proposed.
MIN_SESSION_DURATION_MINUTES = 60
SCHEDULING_BUFFER_MINUTES = 15


def _format_sast(d: dt.datetime | None) -> str:
    """Every scheduled_at/proposed_scheduled_at is stored as naive UTC -
    these emails are read by South African learners/tutors, so always
    render the SAST (fixed UTC+2) wall-clock time, not raw UTC."""
    if not d:
        return "to be confirmed"
    return (d + dt.timedelta(hours=2)).strftime("%A, %d %B %Y at %H:%M") + " SAST"


class TutoringError(Exception):
    pass


def _hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # malformed hash in DB - never crash the login flow over it
        return False


def _serialize_tutor_self(tutor: TutorAccount) -> dict:
    return {
        "id": tutor.id, "name": tutor.name, "email": tutor.email,
        "status": tutor.status,
        "status_label": TUTOR_STATUS_LABELS.get(tutor.status, tutor.status),
        "wants_high_school": tutor.wants_high_school,
        "wants_higher_ed": tutor.wants_higher_ed,
        "higher_ed_status": tutor.higher_ed_status,
        "higher_ed_status_label": (
            TUTOR_STATUS_LABELS.get(tutor.higher_ed_status, tutor.higher_ed_status)
            if tutor.higher_ed_status else None
        ),
    }


def login_tutor(email: str, password: str) -> dict:
    """A tutor's own login to the native app - entirely separate from
    learner/User auth, since TutorAccount is a different kind of actor
    (see this module's docstring). Any status can log in, not just
    approved - a still-pending or rejected applicant should still be able
    to open the app and see their own application status rather than
    being locked out until an admin acts."""
    email = (email or "").strip().lower()
    with get_session() as db:
        tutor = db.query(TutorAccount).filter(TutorAccount.email == email).first()
        if not tutor or not _verify_password(password, tutor.password_hash):
            raise TutoringError("Incorrect email or password.")
        return _serialize_tutor_self(tutor)


TUTOR_RESET_TOKEN_VALID_MINUTES = 60


def create_tutor_password_reset(email: str) -> str | None:
    """Generate a one-time reset token for a tutor's own login - mirrors
    backend/auth.py's create_password_reset() for learners. Returns the
    token, or None if no tutor account matches - callers must show the
    SAME message either way so this can't be used to enumerate which
    emails have a tutor account."""
    email = (email or "").strip().lower()
    with get_session() as db:
        tutor = db.query(TutorAccount).filter(TutorAccount.email == email).first()
        if not tutor:
            return None
        token = secrets.token_urlsafe(32)
        db.add(TutorPasswordReset(
            tutor_id=tutor.id,
            token=token,
            expires_at=dt.datetime.utcnow() + dt.timedelta(minutes=TUTOR_RESET_TOKEN_VALID_MINUTES),
        ))
        return token


def reset_tutor_password(token: str, new_password: str) -> None:
    """Consume a reset token and set a new tutor password. Raises
    TutoringError on any invalid/expired/already-used token, or a
    too-short new password."""
    if len(new_password) < 8:
        raise TutoringError("Password must be at least 8 characters long.")
    with get_session() as db:
        reset = db.query(TutorPasswordReset).filter(TutorPasswordReset.token == token).first()
        if not reset or reset.used or reset.expires_at < dt.datetime.utcnow():
            raise TutoringError("This reset link is invalid or has expired. Please request a new one.")
        tutor = db.query(TutorAccount).get(reset.tutor_id)
        if not tutor:
            raise TutoringError("This reset link is invalid or has expired. Please request a new one.")
        tutor.password_hash = _hash_password(new_password)
        reset.used = True


def create_tutor_api_token(tutor_id: int) -> str:
    """Issue a new bearer token for a tutor's own login - mirrors
    backend/auth.py's create_api_token() for learners."""
    token = secrets.token_urlsafe(32)
    with get_session() as db:
        db.add(TutorApiToken(tutor_id=tutor_id, token=token))
    return token


def get_tutor_by_token(token: str) -> dict | None:
    """Resolve a bearer token to the same shape login_tutor() returns, or
    None if unknown/revoked - the native app's tutor-auth dependency on
    every /tutor/* request."""
    with get_session() as db:
        api_token = db.query(TutorApiToken).filter(TutorApiToken.token == token).first()
        if not api_token:
            return None
        api_token.last_used_at = dt.datetime.utcnow()
        tutor = db.query(TutorAccount).get(api_token.tutor_id)
        if not tutor:
            return None
        return _serialize_tutor_self(tutor)


def revoke_tutor_api_token(token: str) -> None:
    """Log out a single device."""
    with get_session() as db:
        db.query(TutorApiToken).filter(TutorApiToken.token == token).delete()


def list_tutor_own_payouts(tutor_id: int) -> list[dict]:
    """A tutor's own payout history (pending + paid), for their own
    "My Payouts" view - distinct from list_pending_payouts(), which is
    the admin's global pending-only queue across every tutor."""
    with get_session() as db:
        payouts = (
            db.query(TutoringPayout)
            .filter(TutoringPayout.tutor_id == tutor_id)
            .order_by(TutoringPayout.created_at.desc())
            .all()
        )
        return [
            {
                "id": p.id, "session_id": p.session_id,
                "amount_zar": p.amount_zar, "status": p.status,
                "payment_reference": p.payment_reference,
                "created_at": p.created_at, "paid_at": p.paid_at,
            }
            for p in payouts
        ]


# ---------------------------------------------------------------------------
# HIGHER-ED CATALOG (Institution -> Qualification -> Module)
#
# Deliberately NOT pre-populated with every South African institution's
# real curriculum - that list is enormous, varies by institution, and goes
# stale constantly. Admin-managed instead (same "manual by design" spirit
# as tutor vetting above): an admin adds institutions/qualifications/
# modules as real learners/tutors need them, via add_institution/
# add_qualification/add_module below. There's deliberately no edit/delete
# in v1 - a typo'd entry can be superseded by adding a corrected one
# rather than needing a full admin CRUD UI for what should be rare.
# ---------------------------------------------------------------------------

def list_institutions() -> list[dict]:
    with get_session() as db:
        return [
            {"id": i.id, "name": i.name}
            for i in db.query(Institution).order_by(Institution.name.asc()).all()
        ]


def add_institution(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise TutoringError("Please enter an institution name.")
    with get_session() as db:
        existing = db.query(Institution).filter(Institution.name == name).first()
        if existing:
            raise TutoringError("That institution is already in the catalog.")
        inst = Institution(name=name)
        db.add(inst)
        db.flush()
        return {"id": inst.id, "name": inst.name}


def list_qualifications(institution_id: int | None = None) -> list[dict]:
    with get_session() as db:
        q = db.query(Qualification)
        if institution_id:
            q = q.filter(Qualification.institution_id == institution_id)
        return [
            {"id": x.id, "name": x.name, "institution_id": x.institution_id}
            for x in q.order_by(Qualification.name.asc()).all()
        ]


def add_qualification(institution_id: int, name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise TutoringError("Please enter a qualification name.")
    with get_session() as db:
        inst = db.query(Institution).get(institution_id)
        if not inst:
            raise TutoringError("Institution not found.")
        existing = db.query(Qualification).filter(
            Qualification.institution_id == institution_id, Qualification.name == name,
        ).first()
        if existing:
            raise TutoringError("That qualification is already in the catalog for this institution.")
        qual = Qualification(institution_id=institution_id, name=name)
        db.add(qual)
        db.flush()
        return {"id": qual.id, "name": qual.name, "institution_id": qual.institution_id}


def list_modules(qualification_id: int | None = None) -> list[dict]:
    with get_session() as db:
        q = db.query(Module)
        if qualification_id:
            q = q.filter(Module.qualification_id == qualification_id)
        return [
            {
                "id": m.id, "name": m.name, "year_level": m.year_level,
                "year_level_label": YEAR_LEVEL_LABELS.get(m.year_level, str(m.year_level)),
                "qualification_id": m.qualification_id,
            }
            for m in q.order_by(Module.year_level.asc(), Module.name.asc()).all()
        ]


def add_module(qualification_id: int, name: str, year_level: int) -> dict:
    name = (name or "").strip()
    if not name:
        raise TutoringError("Please enter a module name.")
    if year_level not in YEAR_LEVEL_LABELS:
        raise TutoringError("Please choose a valid year level.")
    with get_session() as db:
        qual = db.query(Qualification).get(qualification_id)
        if not qual:
            raise TutoringError("Qualification not found.")
        existing = db.query(Module).filter(
            Module.qualification_id == qualification_id, Module.name == name,
        ).first()
        if existing:
            raise TutoringError("That module is already in the catalog for this qualification.")
        mod = Module(qualification_id=qualification_id, name=name, year_level=year_level)
        db.add(mod)
        db.flush()
        return {
            "id": mod.id, "name": mod.name, "year_level": mod.year_level,
            "qualification_id": mod.qualification_id,
        }


def apply_as_tutor(
    *, name: str, email: str, password: str, phone: str = "", bio: str = "",
    id_number: str = "", id_verification_note: str = "",
    matric_certificate_note: str = "", bank_account_note: str = "",
    cv_note: str = "", availability_note: str = "",
    wants_high_school: bool = True, wants_higher_ed: bool = False,
    subjects: list[dict] | None = None,
    higher_ed_institution_id: int | None = None,
    higher_ed_qualification_id: int | None = None,
    higher_ed_year_of_study: int | None = None,
    higher_ed_qualification_complete: bool = False,
    higher_ed_average: float | None = None,
    higher_ed_transcript_note: str = "",
    higher_ed_module_ids: list[int] | None = None,
    id_document: tuple[bytes, str] | None = None,
    matric_certificate_document: tuple[bytes, str] | None = None,
    cv_document: tuple[bytes, str] | None = None,
) -> dict:
    """A prospective tutor's application, covering one or BOTH segments
    (wants_high_school / wants_higher_ed) in one submission - each has its
    own independent vetting status (status for high school, higher_ed_status
    for higher-ed - see TutorAccount), so a tutor can be approved for one
    segment while the other is still pending or gets rejected.

    HIGH SCHOOL (wants_high_school=True): `subjects` is required, a list of
    {"subject": str, "matric_percentage": float, "topics": str (optional),
    "hourly_rate_zar": float (optional)}. Every subject applied for must
    meet MIN_MATRIC_PERCENTAGE - this is Malita's own stated bar, checked
    here against the applicant's SELF-REPORTED number (not independently
    confirmed against Umalusi/SAQA - see this module's docstring), so a
    clearly-ineligible application is rejected immediately with a clear
    reason instead of sitting in the review queue.

    HIGHER-ED (wants_higher_ed=True): higher_ed_institution_id/
    qualification_id/year_of_study are required, plus higher_ed_average
    (must meet MIN_HIGHER_ED_AVERAGE, same self-reported-not-independently-
    verified spirit as matric_percentage) and at least one entry in
    higher_ed_module_ids - each validated to be at least one year behind
    the tutor's own year_of_study (or allowed unconditionally if
    higher_ed_qualification_complete), per Malita's "must be at least one
    year ahead to tutor a module" policy - a first-year student can never
    be linked to a first-year module.

    id_document / matric_certificate_document / cv_document are each an
    optional (file_bytes, content_type) tuple - if given, the file is
    uploaded to Supabase Storage (see backend/storage.py) and its path is
    stored for an admin to view later via a signed URL. Any of the three
    can be omitted, in which case id_verification_note/
    matric_certificate_note/cv_note (free text - e.g. a link to somewhere
    the tutor already uploaded it) are used instead, same as before file
    upload existed. An admin still reviews whatever was provided by eye -
    nothing here is automated. higher_ed_transcript_note follows the same
    free-text-manual-review pattern for the transcript.

    availability_note is free text (e.g. "Weekdays after 16:00, Saturday
    mornings") - no structured day/time picker in v1, since an admin
    already reads every field by eye when matching a request (see
    match_tutor_to_request)."""
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not name:
        raise TutoringError("Please enter your name.")
    if "@" not in email:
        raise TutoringError("Please enter a valid email address.")
    if len(password) < 8:
        raise TutoringError("Password must be at least 8 characters long.")
    if not wants_high_school and not wants_higher_ed:
        raise TutoringError("Please choose high school, university/college, or both.")

    if wants_high_school:
        if not subjects:
            raise TutoringError("Please apply for at least one subject.")
        for s in subjects:
            pct = s.get("matric_percentage")
            if pct is None or pct < MIN_MATRIC_PERCENTAGE:
                raise TutoringError(
                    f"A matric mark of at least {MIN_MATRIC_PERCENTAGE:.0f}% in {s.get('subject', 'that subject')} "
                    f"is required to apply to tutor it."
                )

    if wants_higher_ed:
        if not higher_ed_institution_id or not higher_ed_qualification_id:
            raise TutoringError("Please select your institution and qualification.")
        if not higher_ed_year_of_study or not (1 <= higher_ed_year_of_study <= max(YEAR_LEVEL_LABELS)):
            raise TutoringError("Please select your year of study.")
        if higher_ed_average is None or higher_ed_average < MIN_HIGHER_ED_AVERAGE:
            raise TutoringError(
                f"A semester/final average of at least {MIN_HIGHER_ED_AVERAGE:.0f}% "
                f"is required to apply to tutor university/college modules."
            )
        if not higher_ed_module_ids:
            raise TutoringError("Please select at least one module you're able to tutor.")

    with get_session() as db:
        existing = db.query(TutorAccount).filter(TutorAccount.email == email).first()
        if existing:
            raise TutoringError("A tutor application with this email already exists.")

        higher_ed_modules: list = []
        if wants_higher_ed:
            qual = db.query(Qualification).get(higher_ed_qualification_id)
            if not qual or qual.institution_id != higher_ed_institution_id:
                raise TutoringError("That qualification doesn't belong to the selected institution.")
            for module_id in higher_ed_module_ids:
                mod = db.query(Module).get(module_id)
                if not mod:
                    raise TutoringError("One of the selected modules no longer exists.")
                if not higher_ed_qualification_complete and mod.year_level >= higher_ed_year_of_study:
                    raise TutoringError(
                        f"You can't tutor \"{mod.name}\" ({YEAR_LEVEL_LABELS.get(mod.year_level)}) "
                        f"as a {YEAR_LEVEL_LABELS.get(higher_ed_year_of_study, higher_ed_year_of_study)} "
                        f"student - you must be at least one year ahead of a module to tutor it."
                    )
                higher_ed_modules.append(mod)

        id_document_path = None
        matric_certificate_path = None
        if id_document:
            file_bytes, content_type = id_document
            try:
                id_document_path = _storage.upload_tutor_document(
                    file_bytes, content_type, applicant_email=email, kind="id",
                )
            except _storage.StorageError as e:
                raise TutoringError(str(e))
        if matric_certificate_document:
            file_bytes, content_type = matric_certificate_document
            try:
                matric_certificate_path = _storage.upload_tutor_document(
                    file_bytes, content_type, applicant_email=email, kind="matric_certificate",
                )
            except _storage.StorageError as e:
                raise TutoringError(str(e))
        cv_path = None
        if cv_document:
            file_bytes, content_type = cv_document
            try:
                cv_path = _storage.upload_tutor_document(
                    file_bytes, content_type, applicant_email=email, kind="cv",
                )
            except _storage.StorageError as e:
                raise TutoringError(str(e))

        tutor = TutorAccount(
            name=name, email=email, password_hash=_hash_password(password),
            phone=phone.strip() or None, bio=bio.strip() or None,
            id_number=id_number.strip() or None,
            id_verification_note=id_verification_note.strip() or None,
            matric_certificate_note=matric_certificate_note.strip() or None,
            id_document_path=id_document_path,
            matric_certificate_path=matric_certificate_path,
            cv_note=cv_note.strip() or None,
            cv_document_path=cv_path,
            availability_note=availability_note.strip() or None,
            bank_account_note=bank_account_note.strip() or None,
            status="pending_review",
            wants_high_school=wants_high_school,
            wants_higher_ed=wants_higher_ed,
            higher_ed_status="pending_review" if wants_higher_ed else None,
            higher_ed_institution_id=higher_ed_institution_id if wants_higher_ed else None,
            higher_ed_qualification_id=higher_ed_qualification_id if wants_higher_ed else None,
            higher_ed_year_of_study=higher_ed_year_of_study if wants_higher_ed else None,
            higher_ed_qualification_complete=higher_ed_qualification_complete if wants_higher_ed else False,
            higher_ed_average=higher_ed_average if wants_higher_ed else None,
            higher_ed_transcript_note=higher_ed_transcript_note.strip() or None if wants_higher_ed else None,
        )
        db.add(tutor)
        db.flush()  # assigns tutor.id before we attach subjects/modules

        if wants_high_school:
            for s in subjects:
                db.add(TutorSubject(
                    tutor_id=tutor.id,
                    subject=s["subject"],
                    matric_percentage=float(s["matric_percentage"]),
                    topics=s.get("topics") or None,
                    hourly_rate_zar=s.get("hourly_rate_zar"),
                ))

        if wants_higher_ed:
            for mod in higher_ed_modules:
                db.add(TutorHigherEdModule(tutor_id=tutor.id, module_id=mod.id))

        return {"id": tutor.id, "status": tutor.status, "higher_ed_status": tutor.higher_ed_status}


def list_tutor_applications(status: str | None = None) -> list[dict]:
    """Admin review queue for the HIGH SCHOOL vetting track only - a tutor
    who only applied for higher-ed (wants_high_school=False) never shows
    up here, see list_tutor_higher_ed_applications for that track. Pass
    status=None for all applications, or a specific status
    ("pending_review", "approved", "rejected", "suspended")."""
    with get_session() as db:
        q = db.query(TutorAccount).filter(TutorAccount.wants_high_school.is_(True))
        if status:
            q = q.filter(TutorAccount.status == status)
        out = []
        for t in q.order_by(TutorAccount.created_at.desc()).all():
            out.append({
                "id": t.id, "name": t.name, "email": t.email, "phone": t.phone,
                "bio": t.bio, "id_number": t.id_number,
                "id_verification_note": t.id_verification_note,
                "matric_certificate_note": t.matric_certificate_note,
                "has_id_document": bool(t.id_document_path),
                "has_matric_certificate_document": bool(t.matric_certificate_path),
                "cv_note": t.cv_note,
                "has_cv_document": bool(t.cv_document_path),
                "availability_note": t.availability_note,
                "bank_account_note": t.bank_account_note,
                "status": t.status,
                "status_label": TUTOR_STATUS_LABELS.get(t.status, t.status),
                "wants_higher_ed": t.wants_higher_ed,
                "admin_notes": t.admin_notes,
                "created_at": t.created_at, "reviewed_at": t.reviewed_at,
                "subjects": [
                    {
                        "subject": s.subject, "matric_percentage": s.matric_percentage,
                        "topics": s.topics, "hourly_rate_zar": s.hourly_rate_zar,
                        "is_active": s.is_active,
                    }
                    for s in t.subjects
                ],
            })
        return out


def list_tutor_higher_ed_applications(status: str | None = None) -> list[dict]:
    """Admin review queue for the HIGHER-ED vetting track only - mirrors
    list_tutor_applications above but filtered to tutors who applied for
    university/college tutoring, with that track's own fields (institution,
    qualification, year of study, average, transcript note, and the
    specific modules they're asking to tutor)."""
    with get_session() as db:
        q = db.query(TutorAccount).filter(TutorAccount.wants_higher_ed.is_(True))
        if status:
            q = q.filter(TutorAccount.higher_ed_status == status)
        out = []
        for t in q.order_by(TutorAccount.created_at.desc()).all():
            inst = db.query(Institution).get(t.higher_ed_institution_id) if t.higher_ed_institution_id else None
            qual = db.query(Qualification).get(t.higher_ed_qualification_id) if t.higher_ed_qualification_id else None
            out.append({
                "id": t.id, "name": t.name, "email": t.email, "phone": t.phone,
                "bio": t.bio, "id_number": t.id_number,
                "id_verification_note": t.id_verification_note,
                "has_id_document": bool(t.id_document_path),
                "cv_note": t.cv_note,
                "has_cv_document": bool(t.cv_document_path),
                "availability_note": t.availability_note,
                "bank_account_note": t.bank_account_note,
                "wants_high_school": t.wants_high_school,
                "higher_ed_status": t.higher_ed_status,
                "higher_ed_status_label": TUTOR_STATUS_LABELS.get(t.higher_ed_status, t.higher_ed_status),
                "higher_ed_institution": inst.name if inst else None,
                "higher_ed_qualification": qual.name if qual else None,
                "higher_ed_year_of_study": t.higher_ed_year_of_study,
                "higher_ed_year_of_study_label": YEAR_LEVEL_LABELS.get(t.higher_ed_year_of_study),
                "higher_ed_qualification_complete": t.higher_ed_qualification_complete,
                "higher_ed_average": t.higher_ed_average,
                "higher_ed_transcript_note": t.higher_ed_transcript_note,
                "admin_notes": t.admin_notes,
                "created_at": t.created_at, "higher_ed_reviewed_at": t.higher_ed_reviewed_at,
                "modules": [
                    {
                        "id": m.module.id, "name": m.module.name,
                        "year_level": m.module.year_level,
                        "year_level_label": YEAR_LEVEL_LABELS.get(m.module.year_level),
                        "is_active": m.is_active,
                    }
                    for m in t.higher_ed_modules
                ],
            })
        return out


def get_tutor_document_url(tutor_id: int, kind: str) -> str:
    """A short-lived signed URL for an admin to view one of a tutor
    applicant's uploaded documents. `kind` is "id", "matric_certificate",
    or "cv"."""
    if kind not in ("id", "matric_certificate", "cv"):
        raise TutoringError("Unknown document kind.")
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        path = {
            "id": tutor.id_document_path,
            "matric_certificate": tutor.matric_certificate_path,
            "cv": tutor.cv_document_path,
        }[kind]
    if not path:
        raise TutoringError("No document was uploaded for this field.")
    try:
        return _storage.get_signed_url(path)
    except _storage.StorageError as e:
        raise TutoringError(str(e))


def approve_tutor(tutor_id: int) -> None:
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        tutor.status = "approved"
        tutor.reviewed_at = dt.datetime.utcnow()
        name, email = tutor.name, tutor.email
    _notify_tutor_of_decision(email, name, approved=True)


def reject_tutor(tutor_id: int, reason: str = "") -> None:
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        tutor.status = "rejected"
        tutor.admin_notes = reason.strip() or None
        tutor.reviewed_at = dt.datetime.utcnow()
        name, email = tutor.name, tutor.email
    _notify_tutor_of_decision(email, name, approved=False, reason=reason)


def approve_tutor_higher_ed(tutor_id: int) -> None:
    """Approves the HIGHER-ED track only - independent of the high-school
    `status` field, which this never touches (see TutorAccount docstring)."""
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        if not tutor.wants_higher_ed:
            raise TutoringError("This tutor didn't apply for higher-ed tutoring.")
        tutor.higher_ed_status = "approved"
        tutor.higher_ed_reviewed_at = dt.datetime.utcnow()
        name, email = tutor.name, tutor.email
    _notify_tutor_of_decision(email, name, approved=True)


def reject_tutor_higher_ed(tutor_id: int, reason: str = "") -> None:
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        if not tutor.wants_higher_ed:
            raise TutoringError("This tutor didn't apply for higher-ed tutoring.")
        tutor.higher_ed_status = "rejected"
        tutor.admin_notes = reason.strip() or None
        tutor.higher_ed_reviewed_at = dt.datetime.utcnow()
        name, email = tutor.name, tutor.email
    _notify_tutor_of_decision(email, name, approved=False, reason=reason)


def _notify_tutor_of_decision(email: str, name: str, *, approved: bool, reason: str = "") -> None:
    """Best-effort - an unconfigured or failed email send (see
    backend/email_util.py) must never break the admin's approve/reject
    action itself, same pattern as backend/collab.py's report-outcome
    notifications."""
    try:
        if approved:
            subject = "Your Malita tutor application has been approved!"
            body = (
                f"Hi {name},\n\n"
                "Good news - your application to tutor on Malita has been approved. "
                "We'll be in touch as learners request sessions in your subject(s).\n\n"
                "— The Malita team"
            )
        else:
            subject = "Update on your Malita tutor application"
            body = (
                f"Hi {name},\n\n"
                "Thanks for applying to tutor on Malita. After review, we're not able "
                "to approve your application at this time."
            )
            reason = (reason or "").strip()
            if reason:
                body += f"\n\nReason given: {reason}"
            body += "\n\n— The Malita team"
        send_email(email, subject, body)
    except Exception:
        logger.exception("Failed to notify tutor applicant %s of application decision", email)


def list_approved_tutors(subject: str | None = None) -> list[dict]:
    """Admin helper when matching a request - approved tutors, optionally
    filtered to ones who applied for a given subject. Includes each
    tutor's completed-session count, so an admin can see their track
    record at a glance before re-matching them to a new request - an
    approved tutor's record never goes away, the same way you'd keep
    recalling a reliable employee for new work rather than starting over
    with someone untested each time."""
    with get_session() as db:
        q = db.query(TutorAccount).filter(TutorAccount.status == "approved")
        out = []
        for t in q.all():
            subjects = [s for s in t.subjects if s.is_active]
            if subject and not any(s.subject == subject for s in subjects):
                continue
            sessions_completed = (
                db.query(TutoringSessionRequest)
                .filter(TutoringSessionRequest.tutor_id == t.id, TutoringSessionRequest.status == "completed")
                .count()
            )
            out.append({
                "id": t.id, "name": t.name, "email": t.email,
                "sessions_completed": sessions_completed,
                "subjects": [
                    {"subject": s.subject, "matric_percentage": s.matric_percentage,
                     "topics": s.topics, "hourly_rate_zar": s.hourly_rate_zar}
                    for s in subjects
                ],
            })
        return out


def get_tutor_profile(tutor_id: int) -> dict:
    """A tutor's full standing record - their application details,
    subjects, and every session they've ever been matched to (newest
    first) - so an admin can review a tutor's track record before
    re-matching them to a new request. An approved tutor's history
    persists here indefinitely, exactly like an employee's record,
    rather than being thrown away once a session ends."""
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor not found.")
        sessions = (
            db.query(TutoringSessionRequest)
            .filter(TutoringSessionRequest.tutor_id == tutor_id)
            .order_by(TutoringSessionRequest.created_at.desc())
            .all()
        )
        sessions_completed = sum(1 for s in sessions if s.status == "completed")
        return {
            "id": tutor.id, "name": tutor.name, "email": tutor.email,
            "phone": tutor.phone, "bio": tutor.bio,
            "status": tutor.status,
            "status_label": TUTOR_STATUS_LABELS.get(tutor.status, tutor.status),
            "availability_note": tutor.availability_note,
            "subjects": [
                {"subject": s.subject, "matric_percentage": s.matric_percentage,
                 "topics": s.topics, "hourly_rate_zar": s.hourly_rate_zar, "is_active": s.is_active}
                for s in tutor.subjects
            ],
            "sessions_completed": sessions_completed,
            "sessions": [_serialize_request(s) for s in sessions],
        }


def _check_schedule_conflict(
    db, *, kind: str, person_id: int, scheduled_at: dt.datetime, duration_minutes: int,
    exclude_request_id: int | None = None,
) -> None:
    """Raises TutoringError if `person_id` (a learner_user_id if
    kind="learner", a tutor_id if kind="tutor") already has another
    non-cancelled session whose time window - padded by
    SCHEDULING_BUFFER_MINUTES on each side - overlaps
    [scheduled_at, scheduled_at + duration_minutes). This is what
    enforces both "no double-booking" and "at least 15 minutes between
    back-to-back sessions", for both sides, at every point a time is set
    or proposed (request, accept, propose, and approving a proposal)."""
    column = TutoringSessionRequest.learner_user_id if kind == "learner" else TutoringSessionRequest.tutor_id
    q = db.query(TutoringSessionRequest).filter(
        column == person_id,
        TutoringSessionRequest.status != "cancelled",
        TutoringSessionRequest.scheduled_at.isnot(None),
    )
    if exclude_request_id is not None:
        q = q.filter(TutoringSessionRequest.id != exclude_request_id)

    new_start = scheduled_at
    new_end = scheduled_at + dt.timedelta(minutes=duration_minutes)
    buffer = dt.timedelta(minutes=SCHEDULING_BUFFER_MINUTES)

    for other in q.all():
        other_start = other.scheduled_at
        other_end = other_start + dt.timedelta(minutes=other.duration_minutes or 60)
        if new_start < (other_end + buffer) and new_end > (other_start - buffer):
            who = "You already have" if kind == "learner" else "This tutor already has"
            raise TutoringError(
                f"{who} a session scheduled around {other_start.strftime('%d %b %Y %H:%M')} - "
                f"sessions need at least {SCHEDULING_BUFFER_MINUTES} minutes' gap between them. "
                "Please choose a different time."
            )


def request_tutoring_session(
    learner_user_id: int, subject: str, price_zar: float, scheduled_at: dt.datetime,
    duration_minutes: int = 60, topic: str = "", preferred_times_note: str = "",
    module_id: int | None = None,
) -> dict:
    """A learner asking for a tutor, inDrive-style: the LEARNER sets the
    price, exact date/time, and duration right here, and the request
    then sits open for any approved tutor who teaches `subject` to
    accept at that price/time (see list_open_requests_for_tutor/
    accept_tutoring_request) - available regardless of subscription
    tier, since tutoring is billed separately.

    module_id (higher-ed requests only): a catalog Module, in which case
    `subject` is expected to already be that module's own display name
    (the caller - api_server.py - looks it up) and matching uses
    TutorHigherEdModule instead of TutorSubject (see
    list_open_requests_for_tutor). Leave None for a high-school request,
    matched by `subject` against TutorSubject as before."""
    if price_zar is None or price_zar <= 0:
        raise TutoringError("Please set a price greater than R0 for this session.")
    if not duration_minutes or duration_minutes < MIN_SESSION_DURATION_MINUTES:
        raise TutoringError(f"Sessions must be at least {MIN_SESSION_DURATION_MINUTES} minutes long.")
    if not scheduled_at:
        raise TutoringError("Please choose a date and time for this session.")
    if scheduled_at <= dt.datetime.utcnow():
        raise TutoringError("Please choose a date and time in the future.")
    with get_session() as db:
        learner = db.query(User).get(learner_user_id)
        if not learner:
            raise TutoringError("Account not found.")
        if module_id is not None and not db.query(Module).get(module_id):
            raise TutoringError("That module no longer exists.")
        _check_schedule_conflict(
            db, kind="learner", person_id=learner_user_id,
            scheduled_at=scheduled_at, duration_minutes=duration_minutes,
        )
        req = TutoringSessionRequest(
            learner_user_id=learner_user_id,
            subject=subject,
            module_id=module_id,
            topic=topic.strip() or None,
            preferred_times_note=preferred_times_note.strip() or None,
            price_zar=price_zar,
            duration_minutes=duration_minutes,
            scheduled_at=scheduled_at,
            status="requested",
        )
        db.add(req)
        db.flush()
        return {"id": req.id, "status": req.status}


def list_learner_requests(learner_user_id: int) -> list[dict]:
    with get_session() as db:
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(TutoringSessionRequest.learner_user_id == learner_user_id)
            .order_by(TutoringSessionRequest.created_at.desc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def list_open_requests() -> list[dict]:
    """Admin visibility: requests not yet accepted by any tutor. No admin
    action is required here anymore (tutors self-accept), but an admin
    can still see what's open and, if needed, force-assign a tutor via
    match_tutor_to_request below."""
    with get_session() as db:
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(TutoringSessionRequest.status == "requested")
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def list_all_tutoring_sessions(upcoming_only: bool = False, completed_only: bool = False) -> list[dict]:
    """Admin visibility into every MATCHED session (one with a tutor
    assigned) - not the still-open/unmatched requests, which
    list_open_requests already covers. Includes both sides' names/emails
    so an admin can see the full picture (subject, topic, schedule,
    duration, price, status) for upcoming sessions (awaiting_payment,
    confirmed) and completed ones alike, without digging through each
    tutor's individual profile."""
    with get_session() as db:
        q = db.query(TutoringSessionRequest).filter(TutoringSessionRequest.tutor_id.isnot(None))
        if upcoming_only:
            q = q.filter(TutoringSessionRequest.status.in_(("awaiting_payment", "confirmed")))
        elif completed_only:
            q = q.filter(TutoringSessionRequest.status == "completed")
        reqs = q.order_by(TutoringSessionRequest.scheduled_at.asc()).all()

        result = []
        for r in reqs:
            learner = db.query(User).get(r.learner_user_id)
            result.append({
                "id": r.id, "subject": r.subject, "topic": r.topic,
                "status": r.status, "status_label": SESSION_STATUS_LABELS.get(r.status, r.status),
                "learner_name": learner.name if learner else "—",
                "learner_email": learner.email if learner else "—",
                "tutor_name": r.tutor.name if r.tutor else "—",
                "tutor_email": r.tutor.email if r.tutor else "—",
                "scheduled_at": r.scheduled_at, "duration_minutes": r.duration_minutes,
                "price_zar": r.price_zar, "platform_cut_percent": r.platform_cut_percent,
                "meet_link": r.meet_link,
                "learner_rating": r.learner_rating, "tutor_rating": r.tutor_rating,
                "created_at": r.created_at, "matched_at": r.matched_at, "paid_at": r.paid_at,
            })
        return result


def _tutor_eligible_subjects_and_modules(db, tutor: TutorAccount) -> tuple[set, set]:
    """What a tutor can currently accept/propose/be matched to - a
    high-school subject set (only if their high-school `status` is
    approved) and a higher-ed module-id set (only if their independent
    `higher_ed_status` is approved) - a "Both" tutor pending on one track
    still gets the other track's requests, since the two are vetted
    independently (see TutorAccount)."""
    subjects = set()
    if tutor.status == "approved":
        subjects = {s.subject for s in tutor.subjects if s.is_active}
    module_ids = set()
    if tutor.higher_ed_status == "approved":
        module_ids = {m.module_id for m in tutor.higher_ed_modules if m.is_active}
    return subjects, module_ids


def list_open_requests_for_tutor(tutor_id: int) -> list[dict]:
    """A tutor's own "open requests" queue, covering BOTH segments in one
    list - a high-school request whose subject the tutor is approved and
    active to teach, and/or a higher-ed request for a module the tutor is
    approved to tutor - so a tutor never sees (or can accept) a request
    outside what they were vetted for on EITHER track."""
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor account not found.")
        subjects, module_ids = _tutor_eligible_subjects_and_modules(db, tutor)
        if not subjects and not module_ids:
            return []
        filters = []
        if subjects:
            filters.append(sa.and_(
                TutoringSessionRequest.module_id.is_(None),
                TutoringSessionRequest.subject.in_(subjects),
            ))
        if module_ids:
            filters.append(TutoringSessionRequest.module_id.in_(module_ids))
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(TutoringSessionRequest.status == "requested", sa.or_(*filters))
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def _serialize_request(r: TutoringSessionRequest) -> dict:
    return {
        "id": r.id, "learner_user_id": r.learner_user_id, "subject": r.subject,
        "module_id": r.module_id,
        "topic": r.topic, "preferred_times_note": r.preferred_times_note,
        "status": r.status,
        "status_label": SESSION_STATUS_LABELS.get(r.status, r.status),
        "tutor_id": r.tutor_id,
        "tutor_name": r.tutor.name if r.tutor else None,
        "duration_minutes": r.duration_minutes, "price_zar": r.price_zar,
        "platform_cut_percent": r.platform_cut_percent,
        "scheduled_at": r.scheduled_at, "proposed_scheduled_at": r.proposed_scheduled_at,
        "created_at": r.created_at,
        "matched_at": r.matched_at, "paid_at": r.paid_at,
        "meet_link": r.meet_link,
        "learner_confirmed": r.learner_confirmed_at is not None,
        "learner_rating": r.learner_rating,
        "tutor_confirmed": r.tutor_confirmed_at is not None,
        "tutor_rating": r.tutor_rating,
    }


def _assign_tutor_to_request(db, req: TutoringSessionRequest, tutor: TutorAccount) -> None:
    """Shared by accept_tutoring_request, respond_to_time_proposal (on
    approval), and match_tutor_to_request (admin override) - moves the
    request to awaiting_payment, snapshots the platform cut, and
    best-effort creates a Google Meet session using req.scheduled_at
    (the caller must already have set this to the agreed time). Caller
    has already validated the tutor is eligible; this just does the
    assignment."""
    req.tutor_id = tutor.id
    req.platform_cut_percent = DEFAULT_PLATFORM_CUT_PERCENT
    req.status = "awaiting_payment"
    req.matched_at = dt.datetime.utcnow()
    req.m_payment_id = f"tutor-session-{req.id}-{uuid.uuid4().hex[:8]}"

    learner = db.query(User).get(req.learner_user_id)
    try:
        meet = _google_calendar.create_meet_session(
            summary=f"Malita Tutoring: {req.subject}" + (f" ({req.topic})" if req.topic else ""),
            description=f"Malita tutoring session between {learner.name} and {tutor.name}.",
            start=req.scheduled_at, duration_minutes=req.duration_minutes or 60,
            attendee_emails=[learner.email, tutor.email],
        )
        req.meet_link = meet["meet_link"]
        req.calendar_event_id = meet["event_id"]
    except _google_calendar.GoogleCalendarError:
        logger.exception("Could not create a Google Meet session for request %s", req.id)


def _check_tutor_eligible_for_request(db, tutor: TutorAccount, req: TutoringSessionRequest) -> None:
    """Shared by accept_tutoring_request and propose_new_time - branches
    on whether this is a higher-ed request (module_id set, matched
    against TutorHigherEdModule + the independent higher_ed_status) or a
    high-school one (matched against TutorSubject + status, as before)."""
    if req.module_id is not None:
        if tutor.higher_ed_status != "approved":
            raise TutoringError("Your higher-ed tutor application isn't approved.")
        if not any(m.module_id == req.module_id and m.is_active for m in tutor.higher_ed_modules):
            raise TutoringError(f"You're not approved to tutor {req.subject}.")
    else:
        if tutor.status != "approved":
            raise TutoringError("Your tutor account isn't approved.")
        if not any(s.subject == req.subject and s.is_active for s in tutor.subjects):
            raise TutoringError(f"You're not approved to tutor {req.subject}.")


def accept_tutoring_request(request_id: int, tutor_id: int) -> dict:
    """A tutor accepting a learner's open, already-priced AND
    already-timed request - the primary matching path (see this module's
    docstring). Only a tutor approved and active for this exact subject
    (high school) or module (higher-ed), and who isn't already booked too
    close to that time, can accept it. If the tutor can't make this exact
    time, use propose_new_time instead."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "requested":
            raise TutoringError("Someone else already accepted this request.")
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor account not found.")
        _check_tutor_eligible_for_request(db, tutor, req)
        _check_schedule_conflict(
            db, kind="tutor", person_id=tutor_id, scheduled_at=req.scheduled_at,
            duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
        )

        _assign_tutor_to_request(db, req, tutor)

        result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
        learner = db.query(User).get(req.learner_user_id)
        learner_name, learner_email = learner.name, learner.email
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic, price_zar, duration_minutes, scheduled_at = (
            req.subject, req.topic, req.price_zar, req.duration_minutes, req.scheduled_at
        )

    _notify_match(
        learner_name=learner_name, learner_email=learner_email,
        tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=scheduled_at,
        meet_link=result["meet_link"],
    )
    return result


def propose_new_time(request_id: int, tutor_id: int, proposed_scheduled_at: dt.datetime) -> dict:
    """A tutor who can't make the learner's exact requested time proposes
    an alternative instead of accepting - reserves the request to this
    tutor (so it stops showing as open to other tutors) and moves it to
    time_proposed, awaiting the learner's approve/decline (see
    respond_to_time_proposal). The tutor's own schedule is checked
    against the PROPOSED time, same as a direct accept."""
    if not proposed_scheduled_at or proposed_scheduled_at <= dt.datetime.utcnow():
        raise TutoringError("Please propose a date and time in the future.")
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "requested":
            raise TutoringError("This request is no longer open.")
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor account not found.")
        _check_tutor_eligible_for_request(db, tutor, req)
        _check_schedule_conflict(
            db, kind="tutor", person_id=tutor_id, scheduled_at=proposed_scheduled_at,
            duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
        )

        req.tutor_id = tutor_id
        req.proposed_scheduled_at = proposed_scheduled_at
        req.status = "time_proposed"

        result = {"id": req.id, "status": req.status}
        learner = db.query(User).get(req.learner_user_id)
        learner_name, learner_email = learner.name, learner.email
        tutor_name = tutor.name
        subject, topic = req.subject, req.topic

    _notify_time_proposed(
        learner_name=learner_name, learner_email=learner_email, tutor_name=tutor_name,
        subject=subject, topic=topic, proposed_scheduled_at=proposed_scheduled_at,
    )
    return result


def respond_to_time_proposal(request_id: int, learner_user_id: int, accept: bool) -> dict:
    """The learner approving or declining a tutor's proposed alternative
    time (see propose_new_time). Approving locks in that time (same
    effect as a direct accept, including a fresh conflict recheck on
    both sides and Meet creation); declining reopens the request for any
    tutor to accept or propose again."""
    decline_notice = None
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.learner_user_id != learner_user_id:
            raise TutoringError("Request not found.")
        if req.status != "time_proposed":
            raise TutoringError(f"This request is '{req.status}', not awaiting a time response.")

        if not accept:
            tutor = db.query(TutorAccount).get(req.tutor_id)
            learner = db.query(User).get(req.learner_user_id)
            if tutor:
                decline_notice = dict(
                    tutor_name=tutor.name, tutor_email=tutor.email, learner_name=learner.name,
                    subject=req.subject, topic=req.topic, proposed_scheduled_at=req.proposed_scheduled_at,
                )

            req.tutor_id = None
            req.proposed_scheduled_at = None
            req.status = "requested"
            result = {"id": req.id, "status": req.status}
            if decline_notice:
                _notify_proposal_declined(**decline_notice)
            return result

        tutor = db.query(TutorAccount).get(req.tutor_id)
        if not tutor or tutor.status != "approved":
            raise TutoringError("That tutor is no longer approved.")
        proposed_at = req.proposed_scheduled_at
        # Re-check both sides - time has passed since the proposal, or
        # either party may have booked something else in the meantime.
        _check_schedule_conflict(
            db, kind="learner", person_id=learner_user_id, scheduled_at=proposed_at,
            duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
        )
        _check_schedule_conflict(
            db, kind="tutor", person_id=req.tutor_id, scheduled_at=proposed_at,
            duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
        )
        req.scheduled_at = proposed_at
        req.proposed_scheduled_at = None

        _assign_tutor_to_request(db, req, tutor)

        result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
        learner = db.query(User).get(req.learner_user_id)
        learner_name, learner_email = learner.name, learner.email
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic, price_zar, duration_minutes, scheduled_at = (
            req.subject, req.topic, req.price_zar, req.duration_minutes, req.scheduled_at
        )

    _notify_match(
        learner_name=learner_name, learner_email=learner_email,
        tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=scheduled_at,
        meet_link=result["meet_link"],
    )
    return result


def match_tutor_to_request(
    request_id: int, tutor_id: int, scheduled_at: dt.datetime | None = None,
) -> dict:
    """Admin override: SUGGESTS an approved tutor for an open (or
    time_proposed) request at the price the learner already set - does
    NOT finalize the match immediately. The tutor still has to confirm
    (see tutor_respond_to_admin_match) before anything is locked in,
    same as the self-service accept/propose flow, so an admin can never
    commit a tutor to a session they haven't agreed to. If the admin
    picks a different time than the learner originally asked for, the
    tutor's acceptance routes through the existing time_proposed flow so
    the LEARNER also gets to approve that change before it's final.
    Still the exception path, not the primary one - see this module's
    docstring."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status not in ("requested", "time_proposed"):
            raise TutoringError(f"This request is already '{req.status}', not awaiting a match.")
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor or tutor.status != "approved":
            raise TutoringError("That tutor is not an approved, active tutor.")

        req.tutor_id = tutor_id
        # Only set proposed_scheduled_at if the admin is suggesting a
        # DIFFERENT time to the learner's own - otherwise leave it unset
        # so the tutor's acceptance can finalize directly at the
        # learner's original time with no extra learner approval step.
        req.proposed_scheduled_at = (
            scheduled_at if scheduled_at and scheduled_at != req.scheduled_at else None
        )
        req.status = "admin_proposed"

        result = {"id": req.id, "status": req.status}
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic = req.subject, req.topic
        proposed_time = req.proposed_scheduled_at or req.scheduled_at

    _notify_admin_proposed_match(
        tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, scheduled_at=proposed_time,
    )
    return result


def tutor_respond_to_admin_match(request_id: int, tutor_id: int, accept: bool) -> dict:
    """The tutor confirming or declining an admin-suggested match (see
    match_tutor_to_request). Declining fully reopens the request, same
    as any other decline, so an admin can pick someone else. Accepting:
    if the admin kept the learner's original time, this finalizes
    exactly like a direct accept; if the admin proposed a different
    time, this instead routes into the normal time_proposed state so
    the LEARNER still gets to approve/decline that change, same as a
    tutor's own counter-proposal would."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.tutor_id != tutor_id:
            raise TutoringError("Request not found.")
        if req.status != "admin_proposed":
            raise TutoringError(f"This request is '{req.status}', not awaiting your confirmation.")
        tutor = db.query(TutorAccount).get(tutor_id)

        if not accept:
            req.tutor_id = None
            req.proposed_scheduled_at = None
            req.status = "requested"
            return {"id": req.id, "status": req.status}

        if not tutor or tutor.status != "approved":
            raise TutoringError("Your tutor account isn't approved.")

        if req.proposed_scheduled_at:
            # Admin proposed a different time than the learner's own -
            # the learner still needs to approve that change.
            req.status = "time_proposed"
            result = {"id": req.id, "status": req.status}
            learner = db.query(User).get(req.learner_user_id)
            learner_name, learner_email = learner.name, learner.email
            tutor_name = tutor.name
            subject, topic = req.subject, req.topic
            proposed_scheduled_at = req.proposed_scheduled_at

            _notify_time_proposed(
                learner_name=learner_name, learner_email=learner_email, tutor_name=tutor_name,
                subject=subject, topic=topic, proposed_scheduled_at=proposed_scheduled_at,
            )
            return result

        # No time change - finalize directly, same as a normal accept.
        _check_schedule_conflict(
            db, kind="tutor", person_id=tutor_id, scheduled_at=req.scheduled_at,
            duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
        )
        _assign_tutor_to_request(db, req, tutor)

        result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
        learner = db.query(User).get(req.learner_user_id)
        learner_name, learner_email = learner.name, learner.email
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic, price_zar, duration_minutes, final_scheduled_at = (
            req.subject, req.topic, req.price_zar, req.duration_minutes, req.scheduled_at
        )

    _notify_match(
        learner_name=learner_name, learner_email=learner_email,
        tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=final_scheduled_at,
        meet_link=result["meet_link"],
    )
    return result


def _notify_admin_proposed_match(
    *, tutor_name: str, tutor_email: str, subject: str, topic: str | None,
    scheduled_at: dt.datetime | None,
) -> None:
    """Best-effort - tells the tutor an admin suggested them for a session
    and that they need to confirm it in the app before anything is final."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        send_email(
            tutor_email,
            "An admin suggested you for a tutoring session",
            (
                f"Hi {tutor_name},\n\n"
                f"A Malita admin suggested you for a {subject}{topic_str} session, "
                f"proposed for:\n\n{when_str}\n\n"
                "Open the Malita tutor app to confirm or decline - nothing is "
                "booked until you confirm.\n\n"
                "— The Malita team"
            ),
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of an admin-suggested match", tutor_email)


def _notify_proposal_declined(
    *, tutor_name: str, tutor_email: str, learner_name: str,
    subject: str, topic: str | None, proposed_scheduled_at: dt.datetime | None,
) -> None:
    """Best-effort, same pattern as _notify_match - tells the tutor their
    proposed time was declined and the request is open again (to them or
    any other qualifying tutor)."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(proposed_scheduled_at)
        send_email(
            tutor_email,
            "Your proposed time was declined",
            (
                f"Hi {tutor_name},\n\n"
                f"{learner_name} declined your proposed time ({when_str}) for "
                f"{subject}{topic_str}.\n\n"
                "The request is open again - you (or another tutor) can accept it "
                "at the learner's original time, or propose a different one.\n\n"
                "— The Malita team"
            ),
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of a declined time proposal", tutor_email)


def _notify_time_proposed(
    *, learner_name: str, learner_email: str, tutor_name: str,
    subject: str, topic: str | None, proposed_scheduled_at: dt.datetime,
) -> None:
    """Best-effort, same pattern as _notify_match - a failed or
    unconfigured email send must never break propose_new_time itself."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(proposed_scheduled_at)
        send_email(
            learner_email,
            "Your tutor proposed a new time",
            (
                f"Hi {learner_name},\n\n"
                f"{tutor_name} can't make your requested time for {subject}{topic_str}, "
                f"but proposed instead:\n\n{when_str}\n\n"
                "Open the Malita app to approve or decline this new time.\n\n"
                "— The Malita team"
            ),
        )
    except Exception:
        logger.exception("Failed to notify learner %s of a proposed time change", learner_email)


def _notify_match(
    *, learner_name: str, learner_email: str, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None, price_zar: float, duration_minutes: int,
    scheduled_at: dt.datetime | None, meet_link: str | None = None,
) -> None:
    """Best-effort, same pattern as _notify_tutor_of_decision - a failed
    or unconfigured email send must never break the match/accept action
    itself."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        meet_line = f"\nGoogle Meet: {meet_link}\n" if meet_link else ""
        send_email(
            learner_email,
            "You've been matched with a tutor!",
            (
                f"Hi {learner_name},\n\n"
                f"Good news - you've been matched with a tutor for {subject}{topic_str}.\n\n"
                f"Tutor: {tutor_name}\n"
                f"Price: R{price_zar:.2f} ({duration_minutes} min)\n"
                f"Scheduled: {when_str}\n"
                f"{meet_line}\n"
                "Open the Malita app and pay to confirm the session.\n\n"
                "— The Malita team"
            ),
        )
        send_email(
            tutor_email,
            "You've been matched to a new tutoring session!",
            (
                f"Hi {tutor_name},\n\n"
                f"You've been matched to a new session for {subject}{topic_str}.\n\n"
                f"Learner: {learner_name}\n"
                f"Price: R{price_zar:.2f} ({duration_minutes} min)\n"
                f"Scheduled: {when_str}\n"
                f"{meet_line}\n"
                "We'll confirm the session once the learner has paid.\n\n"
                "— The Malita team"
            ),
        )
    except Exception:
        logger.exception(
            "Failed to notify learner %s / tutor %s of a new match", learner_email, tutor_email
        )


def mark_session_paid(m_payment_id: str) -> dict:
    """Called from webhook_server.py on a COMPLETE PayFast ITN for a
    tutoring session payment. Confirms the session - the payout ledger
    row is NOT created here anymore (see _maybe_finalize_session): it's
    only created once BOTH the learner and the tutor have confirmed the
    session actually happened, so a no-show can't collect a payout just
    because payment cleared."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).filter(
            TutoringSessionRequest.m_payment_id == m_payment_id
        ).first()
        if not req:
            raise TutoringError("Unknown tutoring session payment reference.")
        if req.status == "confirmed":
            return {"id": req.id, "status": req.status, "already_processed": True}

        req.status = "confirmed"
        req.paid_at = dt.datetime.utcnow()
        return {"id": req.id, "status": req.status}


def _create_payout_row(db, req: TutoringSessionRequest) -> None:
    cut = (req.platform_cut_percent or DEFAULT_PLATFORM_CUT_PERCENT) / 100.0
    tutor_amount = round((req.price_zar or 0.0) * (1.0 - cut), 2)
    db.add(TutoringPayout(
        session_id=req.id, tutor_id=req.tutor_id, amount_zar=tutor_amount,
        status="pending",
    ))


def _maybe_finalize_session(db, req: TutoringSessionRequest) -> None:
    """Once BOTH sides have confirmed the session happened, mark it
    completed and create the payout row - this is the ONLY place (besides
    complete_session's admin override) a TutoringPayout gets created,
    deliberately moved here (not payment time) so a session that was paid
    for but never actually confirmed as having happened can't generate a
    payout."""
    if req.learner_confirmed_at and req.tutor_confirmed_at and req.status != "completed":
        req.status = "completed"
        req.completed_at = dt.datetime.utcnow()
        _create_payout_row(db, req)


def _validate_rating(rating: int) -> None:
    if rating not in (1, 2, 3, 4, 5):
        raise TutoringError("Rating must be between 1 and 5.")


def confirm_session_by_learner(
    request_id: int, learner_user_id: int, rating: int, comment: str = "",
) -> dict:
    """The learner confirming a paid session actually took place, and
    rating the tutor - see _maybe_finalize_session for what happens once
    the tutor has also confirmed."""
    _validate_rating(rating)
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.learner_user_id != learner_user_id:
            raise TutoringError("Session not found.")
        if req.status not in ("confirmed", "completed"):
            raise TutoringError(f"This session is '{req.status}', not yet paid/confirmed.")
        if req.learner_confirmed_at:
            raise TutoringError("You've already confirmed this session.")
        req.learner_confirmed_at = dt.datetime.utcnow()
        req.learner_rating = rating
        req.learner_rating_comment = comment.strip() or None
        _maybe_finalize_session(db, req)
        return {"id": req.id, "status": req.status}


def confirm_session_by_tutor(
    request_id: int, tutor_id: int, rating: int, comment: str = "",
) -> dict:
    """The tutor confirming a paid session actually took place, and
    rating the learner."""
    _validate_rating(rating)
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.tutor_id != tutor_id:
            raise TutoringError("Session not found.")
        if req.status not in ("confirmed", "completed"):
            raise TutoringError(f"This session is '{req.status}', not yet paid/confirmed.")
        if req.tutor_confirmed_at:
            raise TutoringError("You've already confirmed this session.")
        req.tutor_confirmed_at = dt.datetime.utcnow()
        req.tutor_rating = rating
        req.tutor_rating_comment = comment.strip() or None
        _maybe_finalize_session(db, req)
        return {"id": req.id, "status": req.status}


def cancel_session(request_id: int, reason: str = "") -> None:
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status in ("confirmed", "completed"):
            raise TutoringError("A paid or completed session can't be cancelled this way - contact support.")
        req.status = "cancelled"
        req.cancelled_at = dt.datetime.utcnow()
        req.admin_notes = reason.strip() or req.admin_notes


def complete_session(request_id: int) -> None:
    """Admin override: marks a confirmed (paid) session as completed and
    creates its payout WITHOUT waiting for both sides to self-confirm -
    an escape hatch for when one side never gets around to confirming in
    the app but the admin has independently verified the session
    happened (e.g. the learner emailed support directly)."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "confirmed":
            raise TutoringError(f"Only a confirmed (paid) session can be marked complete, not '{req.status}'.")
        req.status = "completed"
        req.completed_at = dt.datetime.utcnow()
        _create_payout_row(db, req)


def list_pending_payouts() -> list[dict]:
    with get_session() as db:
        payouts = (
            db.query(TutoringPayout)
            .filter(TutoringPayout.status == "pending")
            .order_by(TutoringPayout.created_at.asc())
            .all()
        )
        out = []
        for p in payouts:
            tutor = db.query(TutorAccount).get(p.tutor_id)
            out.append({
                "id": p.id, "session_id": p.session_id, "tutor_id": p.tutor_id,
                "tutor_name": tutor.name if tutor else None,
                "tutor_bank_note": tutor.bank_account_note if tutor else None,
                "amount_zar": p.amount_zar, "created_at": p.created_at,
            })
        return out


def mark_payout_paid(payout_id: int, admin_user_id: int, payment_reference: str = "") -> None:
    with get_session() as db:
        payout = db.query(TutoringPayout).get(payout_id)
        if not payout:
            raise TutoringError("Payout not found.")
        payout.status = "paid"
        payout.paid_at = dt.datetime.utcnow()
        payout.paid_by_admin_user_id = admin_user_id
        payout.payment_reference = payment_reference.strip() or None

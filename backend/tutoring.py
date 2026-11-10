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

from .db import (
    get_session, User, TutorAccount, TutorSubject, TutoringSessionRequest,
    TutoringPayout, TutorApiToken,
)
from . import storage as _storage
from . import google_calendar as _google_calendar
from .email_util import send_email

logger = logging.getLogger("malita.tutoring")

MIN_MATRIC_PERCENTAGE = 65.0

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
    "awaiting_payment": "Accepted! Awaiting payment",
    "confirmed": "Paid — confirm once the session happens",
    "completed": "Completed",
    "cancelled": "Cancelled",
}


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


def apply_as_tutor(
    *, name: str, email: str, password: str, phone: str = "", bio: str = "",
    id_number: str = "", id_verification_note: str = "",
    matric_certificate_note: str = "", bank_account_note: str = "",
    cv_note: str = "", availability_note: str = "",
    subjects: list[dict],
    id_document: tuple[bytes, str] | None = None,
    matric_certificate_document: tuple[bytes, str] | None = None,
    cv_document: tuple[bytes, str] | None = None,
) -> dict:
    """A prospective tutor's application. `subjects` is a list of
    {"subject": str, "matric_percentage": float, "topics": str (optional),
    "hourly_rate_zar": float (optional)}. Every subject applied for must
    meet MIN_MATRIC_PERCENTAGE - this is Malita's own stated bar, checked
    here against the applicant's SELF-REPORTED number (not independently
    confirmed against Umalusi/SAQA - see this module's docstring), so a
    clearly-ineligible application is rejected immediately with a clear
    reason instead of sitting in the review queue.

    id_document / matric_certificate_document / cv_document are each an
    optional (file_bytes, content_type) tuple - if given, the file is
    uploaded to Supabase Storage (see backend/storage.py) and its path is
    stored for an admin to view later via a signed URL. Any of the three
    can be omitted, in which case id_verification_note/
    matric_certificate_note/cv_note (free text - e.g. a link to somewhere
    the tutor already uploaded it) are used instead, same as before file
    upload existed. An admin still reviews whatever was provided by eye -
    nothing here is automated.

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
    if not subjects:
        raise TutoringError("Please apply for at least one subject.")
    for s in subjects:
        pct = s.get("matric_percentage")
        if pct is None or pct < MIN_MATRIC_PERCENTAGE:
            raise TutoringError(
                f"A matric mark of at least {MIN_MATRIC_PERCENTAGE:.0f}% in {s.get('subject', 'that subject')} "
                f"is required to apply to tutor it."
            )

    with get_session() as db:
        existing = db.query(TutorAccount).filter(TutorAccount.email == email).first()
        if existing:
            raise TutoringError("A tutor application with this email already exists.")

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
        )
        db.add(tutor)
        db.flush()  # assigns tutor.id before we attach subjects

        for s in subjects:
            db.add(TutorSubject(
                tutor_id=tutor.id,
                subject=s["subject"],
                matric_percentage=float(s["matric_percentage"]),
                topics=s.get("topics") or None,
                hourly_rate_zar=s.get("hourly_rate_zar"),
            ))

        return {"id": tutor.id, "status": tutor.status}


def list_tutor_applications(status: str | None = None) -> list[dict]:
    """Admin review queue. Pass status=None for all applications, or a
    specific status ("pending_review", "approved", "rejected", "suspended")."""
    with get_session() as db:
        q = db.query(TutorAccount)
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


def request_tutoring_session(
    learner_user_id: int, subject: str, price_zar: float, duration_minutes: int = 60,
    topic: str = "", preferred_times_note: str = "",
) -> dict:
    """A learner asking for a tutor, inDrive-style: the LEARNER sets the
    price (and duration) right here, and the request then sits open for
    any approved tutor who teaches `subject` to accept at that price (see
    list_open_requests_for_tutor/accept_tutoring_request) - available
    regardless of subscription tier, since tutoring is billed separately."""
    if price_zar is None or price_zar <= 0:
        raise TutoringError("Please set a price greater than R0 for this session.")
    if not duration_minutes or duration_minutes <= 0:
        raise TutoringError("Please set a session duration.")
    with get_session() as db:
        learner = db.query(User).get(learner_user_id)
        if not learner:
            raise TutoringError("Account not found.")
        req = TutoringSessionRequest(
            learner_user_id=learner_user_id,
            subject=subject,
            topic=topic.strip() or None,
            preferred_times_note=preferred_times_note.strip() or None,
            price_zar=price_zar,
            duration_minutes=duration_minutes,
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


def list_open_requests_for_tutor(tutor_id: int) -> list[dict]:
    """A tutor's own "open requests" queue - only requests whose subject
    the tutor is approved and active to teach, so a tutor never sees (or
    can accept) a request outside what they were vetted for."""
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor or tutor.status != "approved":
            raise TutoringError("Tutor account not found or not approved.")
        subjects = {s.subject for s in tutor.subjects if s.is_active}
        if not subjects:
            return []
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "requested",
                TutoringSessionRequest.subject.in_(subjects),
            )
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def _serialize_request(r: TutoringSessionRequest) -> dict:
    return {
        "id": r.id, "learner_user_id": r.learner_user_id, "subject": r.subject,
        "topic": r.topic, "preferred_times_note": r.preferred_times_note,
        "status": r.status,
        "status_label": SESSION_STATUS_LABELS.get(r.status, r.status),
        "tutor_id": r.tutor_id,
        "tutor_name": r.tutor.name if r.tutor else None,
        "duration_minutes": r.duration_minutes, "price_zar": r.price_zar,
        "scheduled_at": r.scheduled_at, "created_at": r.created_at,
        "matched_at": r.matched_at, "paid_at": r.paid_at,
        "meet_link": r.meet_link,
        "learner_confirmed": r.learner_confirmed_at is not None,
        "learner_rating": r.learner_rating,
        "tutor_confirmed": r.tutor_confirmed_at is not None,
        "tutor_rating": r.tutor_rating,
    }


def _assign_tutor_to_request(
    db, req: TutoringSessionRequest, tutor: TutorAccount, *, scheduled_at: dt.datetime | None,
) -> None:
    """Shared by accept_tutoring_request (tutor self-service) and
    match_tutor_to_request (admin override) - moves the request to
    awaiting_payment, snapshots the platform cut, and best-effort creates
    a Google Meet session. Caller has already validated the tutor is
    eligible; this just does the assignment."""
    req.tutor_id = tutor.id
    req.scheduled_at = scheduled_at
    req.platform_cut_percent = DEFAULT_PLATFORM_CUT_PERCENT
    req.status = "awaiting_payment"
    req.matched_at = dt.datetime.utcnow()
    req.m_payment_id = f"tutor-session-{req.id}-{uuid.uuid4().hex[:8]}"

    if scheduled_at:
        learner = db.query(User).get(req.learner_user_id)
        try:
            meet = _google_calendar.create_meet_session(
                summary=f"Malita Tutoring: {req.subject}" + (f" ({req.topic})" if req.topic else ""),
                description=f"Malita tutoring session between {learner.name} and {tutor.name}.",
                start=scheduled_at, duration_minutes=req.duration_minutes or 60,
                attendee_emails=[learner.email, tutor.email],
            )
            req.meet_link = meet["meet_link"]
            req.calendar_event_id = meet["event_id"]
        except _google_calendar.GoogleCalendarError:
            logger.exception("Could not create a Google Meet session for request %s", req.id)


def accept_tutoring_request(
    request_id: int, tutor_id: int, scheduled_at: dt.datetime | None = None,
) -> dict:
    """A tutor accepting a learner's open, already-priced request - the
    primary matching path (see this module's docstring). Only an
    approved tutor who actively teaches the request's subject can accept
    it - enforced here, not just by what the "open requests" list shows,
    since the list is just a UI convenience."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "requested":
            raise TutoringError("Someone else already accepted this request.")
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor or tutor.status != "approved":
            raise TutoringError("Your tutor account isn't approved.")
        if not any(s.subject == req.subject and s.is_active for s in tutor.subjects):
            raise TutoringError(f"You're not approved to tutor {req.subject}.")

        _assign_tutor_to_request(db, req, tutor, scheduled_at=scheduled_at)

        result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
        learner = db.query(User).get(req.learner_user_id)
        learner_name, learner_email = learner.name, learner.email
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic, price_zar, duration_minutes = req.subject, req.topic, req.price_zar, req.duration_minutes

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
    """Admin override: force-assigns an approved tutor to an open request
    at the price/duration the learner already set - bypasses the
    subject-match check accept_tutoring_request enforces, since this is
    a manual admin decision, not self-service. Still the exception path,
    not the primary one - see this module's docstring."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "requested":
            raise TutoringError(f"This request is already '{req.status}', not awaiting a match.")
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor or tutor.status != "approved":
            raise TutoringError("That tutor is not an approved, active tutor.")

        _assign_tutor_to_request(db, req, tutor, scheduled_at=scheduled_at)

        result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
        learner = db.query(User).get(req.learner_user_id)
        learner_name, learner_email = learner.name, learner.email
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic, price_zar, duration_minutes = req.subject, req.topic, req.price_zar, req.duration_minutes

    _notify_match(
        learner_name=learner_name, learner_email=learner_email,
        tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=scheduled_at,
        meet_link=result["meet_link"],
    )
    return result


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
        when_str = scheduled_at.strftime("%A, %d %B %Y at %H:%M") if scheduled_at else "to be confirmed"
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

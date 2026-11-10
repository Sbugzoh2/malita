"""
Malita (Pty) Ltd — 1-on-1 Tutoring Marketplace (v1, deliberately manual).

Separate product from the subscription: a learner can request a paid
tutoring session regardless of their subscription tier, billed per-session
rather than through the recurring subscription. A tutor is a different
kind of actor from a learner (see backend.db.TutorAccount) with their own
application/vetting flow.

WHY V1 IS MANUAL, NOT AN AUTOMATED MARKETPLACE:
  - Matching: an admin picks which approved tutor fits a learner's request
    and sets the price/time, rather than a real-time booking/matching
    algorithm. This needs real usage data before it's worth automating.
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
import uuid

from .db import (
    get_session, User, TutorAccount, TutorSubject, TutoringSessionRequest,
    TutoringPayout,
)
from . import storage as _storage

MIN_MATRIC_PERCENTAGE = 65.0

# Default cut Malita takes from a session's price - snapshotted onto each
# TutoringSessionRequest at match time, so changing this later never
# retroactively alters an already-priced session.
DEFAULT_PLATFORM_CUT_PERCENT = 20.0


class TutoringError(Exception):
    pass


def _hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def apply_as_tutor(
    *, name: str, email: str, password: str, phone: str = "", bio: str = "",
    id_number: str = "", id_verification_note: str = "",
    matric_certificate_note: str = "", bank_account_note: str = "",
    subjects: list[dict],
    id_document: tuple[bytes, str] | None = None,
    matric_certificate_document: tuple[bytes, str] | None = None,
) -> dict:
    """A prospective tutor's application. `subjects` is a list of
    {"subject": str, "matric_percentage": float, "topics": str (optional),
    "hourly_rate_zar": float (optional)}. Every subject applied for must
    meet MIN_MATRIC_PERCENTAGE - this is Malita's own stated bar, checked
    here against the applicant's SELF-REPORTED number (not independently
    confirmed against Umalusi/SAQA - see this module's docstring), so a
    clearly-ineligible application is rejected immediately with a clear
    reason instead of sitting in the review queue.

    id_document / matric_certificate_document are each an optional
    (file_bytes, content_type) tuple - if given, the file is uploaded to
    Supabase Storage (see backend/storage.py) and its path is stored for
    an admin to view later via a signed URL. Either or both can be
    omitted, in which case id_verification_note/matric_certificate_note
    (free text - e.g. a link to somewhere the tutor already uploaded it)
    are used instead, same as before file upload existed. An admin still
    reviews whatever was provided by eye - nothing here is automated."""
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

        tutor = TutorAccount(
            name=name, email=email, password_hash=_hash_password(password),
            phone=phone.strip() or None, bio=bio.strip() or None,
            id_number=id_number.strip() or None,
            id_verification_note=id_verification_note.strip() or None,
            matric_certificate_note=matric_certificate_note.strip() or None,
            id_document_path=id_document_path,
            matric_certificate_path=matric_certificate_path,
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
                "bank_account_note": t.bank_account_note,
                "status": t.status, "admin_notes": t.admin_notes,
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
    applicant's uploaded documents. `kind` is "id" or "matric_certificate"."""
    if kind not in ("id", "matric_certificate"):
        raise TutoringError("Unknown document kind.")
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        path = tutor.id_document_path if kind == "id" else tutor.matric_certificate_path
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


def reject_tutor(tutor_id: int, reason: str = "") -> None:
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        tutor.status = "rejected"
        tutor.admin_notes = reason.strip() or None
        tutor.reviewed_at = dt.datetime.utcnow()


def list_approved_tutors(subject: str | None = None) -> list[dict]:
    """Admin helper when matching a request - approved tutors, optionally
    filtered to ones who applied for a given subject."""
    with get_session() as db:
        q = db.query(TutorAccount).filter(TutorAccount.status == "approved")
        out = []
        for t in q.all():
            subjects = [s for s in t.subjects if s.is_active]
            if subject and not any(s.subject == subject for s in subjects):
                continue
            out.append({
                "id": t.id, "name": t.name, "email": t.email,
                "subjects": [
                    {"subject": s.subject, "matric_percentage": s.matric_percentage,
                     "topics": s.topics, "hourly_rate_zar": s.hourly_rate_zar}
                    for s in subjects
                ],
            })
        return out


def request_tutoring_session(
    learner_user_id: int, subject: str, topic: str = "", preferred_times_note: str = "",
) -> dict:
    """A learner asking for a tutor - available regardless of subscription
    tier, since tutoring is billed separately."""
    with get_session() as db:
        learner = db.query(User).get(learner_user_id)
        if not learner:
            raise TutoringError("Account not found.")
        req = TutoringSessionRequest(
            learner_user_id=learner_user_id,
            subject=subject,
            topic=topic.strip() or None,
            preferred_times_note=preferred_times_note.strip() or None,
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
    """Admin queue: requests not yet matched to a tutor."""
    with get_session() as db:
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(TutoringSessionRequest.status == "requested")
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def _serialize_request(r: TutoringSessionRequest) -> dict:
    return {
        "id": r.id, "learner_user_id": r.learner_user_id, "subject": r.subject,
        "topic": r.topic, "preferred_times_note": r.preferred_times_note,
        "status": r.status, "tutor_id": r.tutor_id,
        "tutor_name": r.tutor.name if r.tutor else None,
        "duration_minutes": r.duration_minutes, "price_zar": r.price_zar,
        "scheduled_at": r.scheduled_at, "created_at": r.created_at,
        "matched_at": r.matched_at, "paid_at": r.paid_at,
    }


def match_tutor_to_request(
    request_id: int, tutor_id: int, price_zar: float, duration_minutes: int,
    scheduled_at: dt.datetime | None = None,
    platform_cut_percent: float = DEFAULT_PLATFORM_CUT_PERCENT,
) -> dict:
    """Admin action: assigns an approved tutor and a price to an open
    request, moving it to awaiting_payment. The caller (API layer) still
    needs to generate the actual PayFast checkout for the learner to pay -
    see api_server.py's /tutoring/requests/{id}/checkout-page."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "requested":
            raise TutoringError(f"This request is already '{req.status}', not awaiting a match.")
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor or tutor.status != "approved":
            raise TutoringError("That tutor is not an approved, active tutor.")

        req.tutor_id = tutor_id
        req.price_zar = price_zar
        req.duration_minutes = duration_minutes
        req.scheduled_at = scheduled_at
        req.platform_cut_percent = platform_cut_percent
        req.status = "awaiting_payment"
        req.matched_at = dt.datetime.utcnow()
        req.m_payment_id = f"tutor-session-{request_id}-{uuid.uuid4().hex[:8]}"
        return {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id}


def mark_session_paid(m_payment_id: str) -> dict:
    """Called from webhook_server.py on a COMPLETE PayFast ITN for a
    tutoring session payment. Confirms the session and creates the payout
    ledger row for the admin to pay the tutor manually."""
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

        cut = (req.platform_cut_percent or DEFAULT_PLATFORM_CUT_PERCENT) / 100.0
        tutor_amount = round((req.price_zar or 0.0) * (1.0 - cut), 2)
        db.add(TutoringPayout(
            session_id=req.id, tutor_id=req.tutor_id, amount_zar=tutor_amount,
            status="pending",
        ))
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
    """Admin marks a confirmed (paid) session as actually having taken
    place - purely a record-keeping step, doesn't affect the payout."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "confirmed":
            raise TutoringError(f"Only a confirmed (paid) session can be marked complete, not '{req.status}'.")
        req.status = "completed"
        req.completed_at = dt.datetime.utcnow()


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

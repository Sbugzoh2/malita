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

import calendar
import datetime as dt
import logging
import secrets
import uuid

import sqlalchemy as sa

from .db import (
    get_session, User, TutorAccount, TutorSubject, TutoringSessionRequest,
    TutoringPayout, TutorApiToken, TutorPasswordReset, Notification,
    Institution, Qualification, Module, TutorHigherEdModule, TutorCustomHigherEdModule, YEAR_LEVEL_LABELS,
)
from . import storage as _storage
from . import google_calendar as _google_calendar
from .email_util import send_email

logger = logging.getLogger("malita.tutoring")

MIN_MATRIC_PERCENTAGE = 75.0
# Minimum self-reported semester/final average to apply as a higher-ed
# tutor - kept as its own named constant since the two tracks are
# conceptually separate (one's a matric subject mark, the other a
# university/college average) and deliberately set lower than the
# high-school bar above (Malita's policy).
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
    "pending_admin_approval": "A tutor claimed this — awaiting admin approval",
    "awaiting_payment": "Accepted! Awaiting payment",
    "confirmed": "Paid — confirm once the session happens",
    "tutor_cancelled": "Tutor cancelled — choose what happens next",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "lapsed": "Lapsed — payment wasn't made in time",
}

# A session must be at least this long, and no two of the same person's
# (learner's or tutor's) sessions may be scheduled with less than this
# many minutes between them - enforced by _check_schedule_conflict below
# at every point a time is set or proposed.
MIN_SESSION_DURATION_MINUTES = 60
SCHEDULING_BUFFER_MINUTES = 15
# The LEARNER's own initial request must be at least this far in the
# future - enforced only in request_tutoring_session, NOT in
# propose_new_time/respond_to_time_proposal/match_tutor_to_request/
# tutor_respond_to_admin_match, since those already represent the
# learner and tutor mutually agreeing on a different time (Malita's
# stated "unless otherwise agreed" exception).
MIN_REQUEST_LEAD_HOURS = 24
# How long a learner has to pay after a tutor accepts/is matched before
# the request automatically lapses - see _expire_lapsed_payments.
PAYMENT_DEADLINE_HOURS = 24
# Neither party can cancel an already-accepted (awaiting_payment or
# confirmed) session within this many hours of when it's due to happen -
# see cancel_accepted_session.
CANCELLATION_CUTOFF_HOURS = 24
# How long before a CONFIRMED (paid) session's start time to send the
# "coming up" reminders - see send_due_reminders. Each fires once, guarded
# by its own reminder_*_sent_at column.
SESSION_REMINDER_HOURS_BEFORE = 24
SESSION_REMINDER_MINUTES_BEFORE = 15
# How long before an unpaid match's PAYMENT_DEADLINE_HOURS deadline to
# warn the learner it's about to lapse.
PAYMENT_LAPSE_REMINDER_HOURS_BEFORE = 2
# How long a tutor has to respond to an admin-suggested match (see
# match_tutor_to_request) before it automatically reopens - see
# _expire_stale_admin_proposals.
ADMIN_PROPOSAL_DEADLINE_HOURS = 12
# There's no API that can force-start a recording on a regular (non-
# Google-Workspace) Meet call - see backend/google_calendar.py's docstring
# for why this project uses a personal Gmail account, not Workspace. So
# "every session auto-recorded" is, in practice, every tutor asked to
# click Meet's own one-click "Record" button and then submit the
# resulting link afterward (see submit_session_recording) - this note is
# included in every tutor-facing match/reminder email.
RECORDING_REMINDER_NOTE = (
    "Reminder: please record this session (click \"Record meeting\" inside "
    "Google Meet once you're in the call) and share the recording link with "
    "us from the Tutor app afterward - Malita keeps a recording of every "
    "session on file."
)


def _format_sast(d: dt.datetime | None) -> str:
    """Every scheduled_at/proposed_scheduled_at is stored as naive UTC -
    these emails are read by South African learners/tutors, so always
    render the SAST (fixed UTC+2) wall-clock time, not raw UTC."""
    if not d:
        return "to be confirmed"
    return (d + dt.timedelta(hours=2)).strftime("%A, %d %B %Y at %H:%M") + " SAST"


def _iso_utc(d: dt.datetime | None) -> str | None:
    """Every datetime column here is naive (no tzinfo) but genuinely
    holds UTC - FastAPI's default JSON encoder calls plain .isoformat()
    on that with no 'Z'/offset suffix, and a timezone-less ISO string is
    parsed as LOCAL time by JavaScript's `new Date(...)` on the client,
    not UTC. On a South African phone (Africa/Johannesburg, UTC+2) that
    silently shifted every scheduled_at/proposed_scheduled_at back by
    exactly 2 hours client-side, on top of the app's own correct SAST
    display math - reproducing as "the time shows 2 hours behind what
    was selected" even though the encode/decode math on both ends was
    individually correct. Append the 'Z' explicitly on every datetime
    this module hands back to a client, here, rather than relying on
    FastAPI's default encoder to get it right."""
    return d.isoformat() + "Z" if d else None


def create_notification(*, recipient_kind: str, recipient_id: int, title: str, body: str = "") -> None:
    """Best-effort, same philosophy as every _notify_* email function
    below - a failed/unexpected error here must never break the action
    that triggered it. Called right alongside (not instead of) the
    matching send_email call in each of those functions, as a parallel
    in-app delivery channel - see the Notification model's own
    docstring. recipient_kind is "user" (covers both a learner and an
    admin - see Notification) or "tutor"."""
    try:
        with get_session() as db:
            db.add(Notification(
                recipient_kind=recipient_kind, recipient_id=recipient_id, title=title, body=body or None,
            ))
    except Exception:
        logger.exception("Failed to create a notification (kind=%s, id=%s)", recipient_kind, recipient_id)


def list_notifications(recipient_kind: str, recipient_id: int, limit: int = 50) -> list[dict]:
    with get_session() as db:
        rows = (
            db.query(Notification)
            .filter(Notification.recipient_kind == recipient_kind, Notification.recipient_id == recipient_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": n.id, "title": n.title, "body": n.body,
                "created_at": _iso_utc(n.created_at), "read": n.read_at is not None,
            }
            for n in rows
        ]


def count_unread_notifications(recipient_kind: str, recipient_id: int) -> int:
    with get_session() as db:
        return (
            db.query(Notification)
            .filter(
                Notification.recipient_kind == recipient_kind, Notification.recipient_id == recipient_id,
                Notification.read_at.is_(None),
            )
            .count()
        )


def mark_notification_read(notification_id: int, recipient_kind: str, recipient_id: int) -> None:
    with get_session() as db:
        n = db.query(Notification).get(notification_id)
        if n and n.recipient_kind == recipient_kind and n.recipient_id == recipient_id and not n.read_at:
            n.read_at = dt.datetime.utcnow()


def mark_all_notifications_read(recipient_kind: str, recipient_id: int) -> None:
    with get_session() as db:
        db.query(Notification).filter(
            Notification.recipient_kind == recipient_kind, Notification.recipient_id == recipient_id,
            Notification.read_at.is_(None),
        ).update({"read_at": dt.datetime.utcnow()})


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
                "created_at": _iso_utc(p.created_at), "paid_at": _iso_utc(p.paid_at),
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


def _module_dependent_count(db, module_ids: list[int]) -> int:
    """How many real records (a tutor's declared module, or a learner's
    tutoring request) point at any of these modules - used to block a
    delete that would otherwise orphan live data rather than just a
    catalog mistake."""
    if not module_ids:
        return 0
    return (
        db.query(TutorHigherEdModule).filter(TutorHigherEdModule.module_id.in_(module_ids)).count()
        + db.query(TutoringSessionRequest).filter(TutoringSessionRequest.module_id.in_(module_ids)).count()
    )


def delete_module(module_id: int) -> dict:
    """Removes one module - blocked if any tutor has declared it or any
    tutoring request references it (delete those first, or leave the
    module in place), so this can never silently orphan live data."""
    with get_session() as db:
        mod = db.query(Module).get(module_id)
        if not mod:
            raise TutoringError("Module not found.")
        if _module_dependent_count(db, [mod.id]):
            raise TutoringError(
                f"Can't delete \"{mod.name}\" - a tutor or tutoring request still references it."
            )
        name = mod.name
        db.delete(mod)
        return {"deleted": name}


def delete_qualification(qualification_id: int) -> dict:
    """Removes a qualification AND every module under it (cascade) -
    blocked if any of those modules has a real dependent (see
    _module_dependent_count)."""
    with get_session() as db:
        qual = db.query(Qualification).get(qualification_id)
        if not qual:
            raise TutoringError("Qualification not found.")
        module_ids = [m.id for m in qual.modules]
        if _module_dependent_count(db, module_ids):
            raise TutoringError(
                f"Can't delete \"{qual.name}\" - a tutor or tutoring request still references one of its modules."
            )
        name = qual.name
        db.delete(qual)
        return {"deleted": name}


def delete_institution(institution_id: int) -> dict:
    """Removes an institution AND every qualification/module under it
    (cascade) - blocked if any of those modules has a real dependent (see
    _module_dependent_count). This is the fix for a catalog mistake like
    a qualification name accidentally typed into the institution field -
    not meant for removing a real institution that's actually in use."""
    with get_session() as db:
        inst = db.query(Institution).get(institution_id)
        if not inst:
            raise TutoringError("Institution not found.")
        module_ids = [m.id for q in inst.qualifications for m in q.modules]
        if _module_dependent_count(db, module_ids):
            raise TutoringError(
                f"Can't delete \"{inst.name}\" - a tutor or tutoring request still references one of its modules."
            )
        name = inst.name
        db.delete(inst)
        return {"deleted": name}


# ---------------------------------------------------------------------------
# A starter higher-ed catalog, for an admin to seed in one click (see
# seed_default_higher_ed_catalog) instead of typing in dozens of
# institutions and hundreds of modules by hand. IMPORTANT - what this is
# and isn't:
#   - DEFAULT_SA_UNIVERSITIES is South Africa's actual, stable list of 26
#     public universities - high confidence, this part is factual.
#   - DEFAULT_SA_TVET_COLLEGES is a best-effort list of the public TVET
#     colleges - LOWER confidence than the universities list. TVET
#     colleges merge/rename more often and no authoritative source was
#     checked against, so a name here may be stale or slightly off - an
#     admin should treat this list as a starting point to correct (via
#     delete_institution/add_institution) rather than as verified fact,
#     the same way a mismatched name on a university's qualifications
#     would be.
#   - Every qualification/module below is a GENERIC, broadly-applicable
#     starter set, NOT each institution's real, official curriculum
#     pulled from DHET or the institution itself - no such authoritative
#     source was used. For universities: the same common first/second/
#     third-year subject names most SA science/commerce/arts/education
#     degrees share, plus a generic Honours/Master's/PhD track. For TVET
#     colleges: only the NCV's nationally-standardized FUNDAMENTAL
#     subjects (Life Orientation, Communication, Mathematics, Computer
#     Literacy) at each of its 3 levels - deliberately NOT the
#     field-specific vocational subjects (e.g. a specific engineering or
#     hospitality stream), since those vary by college/campus and this
#     module has no reliable source to generate them accurately from.
#     All of it exists so the catalog is immediately usable; an admin is
#     expected to refine/add to it over time via the normal
#     add_institution/add_qualification/add_module functions above, same
#     as any admin-entered row.
#   - Private colleges are deliberately NOT included - that list is far
#     larger and even less stable than TVET colleges, and admins can add
#     any of those the same one-at-a-time way if/when a tutor or learner
#     from one actually signs up.
# ---------------------------------------------------------------------------
DEFAULT_SA_UNIVERSITIES = [
    "University of Cape Town", "University of the Witwatersrand", "Stellenbosch University",
    "University of Pretoria", "University of KwaZulu-Natal", "Rhodes University",
    "University of Johannesburg", "University of South Africa", "University of the Western Cape",
    "North-West University", "University of the Free State", "University of Fort Hare",
    "University of Limpopo", "University of Mpumalanga", "Sefako Makgatho Health Sciences University",
    "Sol Plaatje University", "Tshwane University of Technology", "Cape Peninsula University of Technology",
    "Durban University of Technology", "Mangosuthu University of Technology", "Vaal University of Technology",
    "Central University of Technology", "University of Zululand", "University of Venda",
    "Walter Sisulu University", "Nelson Mandela University",
]

# Best-effort list of South Africa's public TVET colleges - see the big
# comment above DEFAULT_SA_UNIVERSITIES for the (lower) confidence level
# here versus the universities list.
DEFAULT_SA_TVET_COLLEGES = [
    # Eastern Cape
    "Buffalo City TVET College", "East Cape Midlands TVET College", "Ikhala TVET College",
    "Ingwe TVET College", "King Hintsa TVET College", "King Sabata Dalindyebo TVET College",
    "Lovedale TVET College", "Port Elizabeth TVET College",
    # Free State
    "Flavius Mareka TVET College", "Goldfields TVET College", "Maluti TVET College",
    "Motheo TVET College",
    # Gauteng
    "Central Johannesburg TVET College", "Ekurhuleni East TVET College",
    "Ekurhuleni West TVET College", "Sedibeng TVET College", "South West Gauteng TVET College",
    "Tshwane North TVET College", "Tshwane South TVET College", "Western TVET College",
    # KwaZulu-Natal
    "Coastal KZN TVET College", "Elangeni TVET College", "Esayidi TVET College",
    "Majuba TVET College", "Mnambithi TVET College", "Mthashana TVET College",
    "Thekwini TVET College", "Umfolozi TVET College", "Umgungundlovu TVET College",
    # Limpopo
    "Capricorn TVET College", "Lephalale TVET College", "Letaba TVET College",
    "Sekhukhune TVET College", "Vhembe TVET College",
    # Mpumalanga
    "Ehlanzeni TVET College", "Gert Sibande TVET College", "Nkangala TVET College",
    # North West
    "Orbit TVET College", "Taletso TVET College", "Vuselela TVET College",
    # Northern Cape
    "Northern Cape Rural TVET College", "Northern Cape Urban TVET College",
    # Western Cape
    "Boland TVET College", "College of Cape Town", "False Bay TVET College",
    "Northlink TVET College", "South Cape TVET College", "West Coast TVET College",
]

# Universities of Technology get a Diploma/BEngTech track (see below)
# instead of a traditional BEng, reflecting their actual institutional
# character rather than the research-university engineering model.
_UNIVERSITIES_OF_TECHNOLOGY = {
    "Tshwane University of Technology", "Cape Peninsula University of Technology",
    "Durban University of Technology", "Mangosuthu University of Technology",
    "Vaal University of Technology", "Central University of Technology",
}
# A curated subset with well-established traditional engineering faculties
# - deliberately NOT applied to all 26, to avoid implying every university
# offers a BEng.
_BENG_UNIVERSITIES = {
    "University of Cape Town", "University of the Witwatersrand", "Stellenbosch University",
    "University of Pretoria", "University of KwaZulu-Natal", "University of Johannesburg",
    "North-West University", "Nelson Mandela University", "University of the Free State",
}

# qualification name -> [(module name, year_level), ...]. Applied to every
# university in DEFAULT_SA_UNIVERSITIES unless noted otherwise above.
_COMMON_QUALIFICATION_MODULES: dict[str, list[tuple[str, int]]] = {
    "Bachelor of Science (BSc)": [
        ("Mathematics 1A", 1), ("Mathematics 1B", 1), ("Physics 1A", 1),
        ("Chemistry 1A", 1), ("Computer Science 1A", 1), ("Statistics 1A", 1),
        ("Calculus II", 2), ("Linear Algebra II", 2), ("Classical Mechanics", 2),
        ("Data Structures & Algorithms", 2), ("Organic Chemistry", 2),
        ("Real Analysis", 3), ("Abstract Algebra", 3), ("Quantum Mechanics", 3),
        ("Machine Learning", 3), ("Differential Equations", 3),
    ],
    "Bachelor of Commerce (BCom)": [
        ("Financial Accounting 1A", 1), ("Microeconomics 1A", 1), ("Macroeconomics 1A", 1),
        ("Business Management 1A", 1), ("Statistics for Commerce 1A", 1),
        ("Financial Accounting II", 2), ("Cost & Management Accounting", 2),
        ("Corporate Finance", 2), ("Business Law", 2),
        ("Financial Accounting III", 3), ("Taxation", 3), ("Auditing", 3),
        ("Strategic Management", 3),
    ],
    "Bachelor of Arts (BA)": [
        ("English 1A", 1), ("Psychology 1A", 1), ("Sociology 1A", 1),
        ("Philosophy 1A", 1), ("History 1A", 1),
        ("Psychology II", 2), ("Sociology II", 2), ("Political Studies", 2),
        ("Psychology III", 3), ("Industrial Psychology", 3), ("Media Studies", 3),
    ],
    "Bachelor of Education (BEd)": [
        ("Education Studies 1A", 1), ("Curriculum Studies 1A", 1), ("Child & Adolescent Development", 1),
        ("Education Studies II", 2), ("Subject Didactics", 2),
        ("Education Studies III", 3), ("Inclusive Education", 3),
        ("Work-Integrated Learning (Teaching Practice)", 4),
    ],
}
# Postgraduate tracks - applied to every university alongside the
# Bachelor's above, same generic-starter-set spirit (see this section's
# opening comment). year_level 4 = Honours, year_level 5 = the single
# "Postgraduate (Masters/Doctoral)" bucket this catalog's year-level
# scale tops out at (see YEAR_LEVEL_LABELS in db.py) - Master's and PhD
# are kept as separate qualification NAMES even though they share that
# one year_level, so both still show up as distinct, pickable options.
_POSTGRAD_QUALIFICATION_MODULES: dict[str, list[tuple[str, int]]] = {
    "Bachelor of Science Honours (BScHons)": [
        ("Research Methodology", 4), ("Advanced Topics in Mathematics", 4),
        ("Advanced Topics in Physics", 4), ("Honours Research Project", 4),
    ],
    "Master of Science (MSc)": [
        ("Advanced Research Methodology", 5), ("MSc Dissertation", 5), ("Advanced Seminar", 5),
    ],
    "Bachelor of Commerce Honours (BComHons)": [
        ("Research Methodology", 4), ("Advanced Financial Management", 4),
        ("Advanced Econometrics", 4), ("Honours Research Project", 4),
    ],
    "Master of Commerce (MCom)": [
        ("Advanced Research Methodology", 5), ("MCom Dissertation", 5), ("Advanced Seminar", 5),
    ],
    "Bachelor of Arts Honours (BAHons)": [
        ("Research Methodology", 4), ("Advanced Seminar in the Discipline", 4),
        ("Honours Research Essay", 4),
    ],
    "Master of Arts (MA)": [
        ("Advanced Research Methodology", 5), ("MA Dissertation", 5), ("Advanced Seminar", 5),
    ],
    "Bachelor of Education Honours (BEdHons)": [
        ("Advanced Curriculum Studies", 4), ("Research Methodology in Education", 4),
        ("Honours Research Project", 4),
    ],
    "Master of Education (MEd)": [
        ("Advanced Research Methodology", 5), ("MEd Dissertation", 5), ("Advanced Seminar in Education", 5),
    ],
    "Doctor of Philosophy (PhD)": [
        ("Doctoral Thesis Research", 5), ("Advanced Research Methodology", 5),
        ("Academic Writing & Publishing", 5),
    ],
}
_BENG_MODULES: list[tuple[str, int]] = [
    ("Engineering Mathematics 1A", 1), ("Engineering Mechanics (Statics)", 1),
    ("Introduction to Programming for Engineers", 1),
    ("Engineering Mathematics II", 2), ("Thermodynamics", 2), ("Electrical Circuits", 2),
    ("Fluid Mechanics", 3), ("Structural Analysis", 3), ("Control Systems", 3),
    ("Final Year Design Project", 4),
]
_BENGTECH_MODULES: list[tuple[str, int]] = [
    ("Engineering Mathematics I", 1), ("Engineering Science I", 1), ("Technical Communication", 1),
    ("Engineering Mathematics II", 2), ("Strength of Materials", 2),
    ("Engineering Design Project", 3), ("Industrial Practice (WIL)", 3),
]

# Every TVET college gets just this one qualification - its nationally
# standardized NCV FUNDAMENTAL subjects only (see the big comment above
# DEFAULT_SA_UNIVERSITIES for why field-specific vocational subjects
# aren't included), at each of the NCV's 3 levels (mapped onto this
# catalog's year_level 1/2/3).
_NCV_QUALIFICATION_NAME = "National Certificate (Vocational) (NCV)"
_NCV_MODULES: list[tuple[str, int]] = [
    ("Life Orientation (NCV Level 2)", 1), ("Communication in English (NCV Level 2)", 1),
    ("Mathematics (NCV Level 2)", 1),
    ("Life Orientation (NCV Level 3)", 2), ("Communication in English (NCV Level 3)", 2),
    ("Mathematics (NCV Level 3)", 2), ("Computer Literacy (NCV Level 3)", 2),
    ("Life Orientation (NCV Level 4)", 3), ("Communication in English (NCV Level 4)", 3),
    ("Mathematics (NCV Level 4)", 3), ("Computer Literacy (NCV Level 4)", 3),
]


def seed_default_higher_ed_catalog() -> dict:
    """One-click starter data for an otherwise-empty higher-ed catalog -
    see the big comment above DEFAULT_SA_UNIVERSITIES for exactly what
    this is (South Africa's 26 public universities plus its public TVET
    colleges) and isn't (each one's actual official curriculum, or a
    guaranteed-current TVET college name - see that comment's confidence
    caveat). Idempotent: safe to run more than once - anything whose name
    already exists (by the same uniqueness rule add_institution/
    add_qualification/add_module already enforce) is skipped, not
    duplicated.

    Batched into a handful of ROUND TRIPS rather than one existence-
    check-then-insert pair per row (an earlier version checked/inserted
    row by row, which is well over 1,500 sequential round trips against
    a REMOTE database - instant against a local SQLite test db, but slow
    enough against production Postgres to hit a request timeout and fail
    the whole seed with nothing visibly wrong in this function's own
    logic). This version uses SQLAlchemy's Core insert() with a list of
    rows (not one ORM .add() per object), which SQLAlchemy 2.0 batches
    into one (or a couple, for the biggest table) actual INSERT
    statements each - about 8 round trips total for the whole catalog,
    regardless of its size, versus 1,500+ before."""
    all_default_institutions = DEFAULT_SA_UNIVERSITIES + DEFAULT_SA_TVET_COLLEGES
    created = {"institutions": 0, "qualifications": 0, "modules": 0}
    skipped = {"institutions": 0, "qualifications": 0, "modules": 0}
    with get_session() as db:
        # --- institutions ---
        existing_insts = {
            i.name: i for i in
            db.query(Institution).filter(Institution.name.in_(all_default_institutions)).all()
        }
        new_inst_names = [n for n in all_default_institutions if n not in existing_insts]
        skipped["institutions"] = len(all_default_institutions) - len(new_inst_names)
        created["institutions"] = len(new_inst_names)
        if new_inst_names:
            db.execute(sa.insert(Institution), [{"name": n} for n in new_inst_names])
        # Re-fetch (existing + just-created) in one query to get every id,
        # including the ones SQLAlchemy just assigned above.
        inst_by_name = {
            i.name: i for i in
            db.query(Institution).filter(Institution.name.in_(all_default_institutions)).all()
        }

        # --- qualifications ---
        desired_quals: list[tuple] = []  # (institution, qualification_name, modules)
        for uni_name in DEFAULT_SA_UNIVERSITIES:
            inst = inst_by_name[uni_name]
            quals_for_this_uni = dict(_COMMON_QUALIFICATION_MODULES)
            quals_for_this_uni.update(_POSTGRAD_QUALIFICATION_MODULES)
            if uni_name in _BENG_UNIVERSITIES:
                quals_for_this_uni["Bachelor of Engineering (BEng)"] = _BENG_MODULES
            if uni_name in _UNIVERSITIES_OF_TECHNOLOGY:
                quals_for_this_uni["Bachelor of Engineering Technology (BEngTech)"] = _BENGTECH_MODULES
            for qual_name, modules in quals_for_this_uni.items():
                desired_quals.append((inst, qual_name, modules))
        for college_name in DEFAULT_SA_TVET_COLLEGES:
            desired_quals.append((inst_by_name[college_name], _NCV_QUALIFICATION_NAME, _NCV_MODULES))

        all_inst_ids = [i.id for i in inst_by_name.values()]
        existing_quals = {
            (q.institution_id, q.name): q for q in
            db.query(Qualification).filter(Qualification.institution_id.in_(all_inst_ids)).all()
        }
        new_qual_rows = [
            {"institution_id": inst.id, "name": qual_name}
            for inst, qual_name, _ in desired_quals
            if (inst.id, qual_name) not in existing_quals
        ]
        skipped["qualifications"] = len(desired_quals) - len(new_qual_rows)
        created["qualifications"] = len(new_qual_rows)
        if new_qual_rows:
            db.execute(sa.insert(Qualification), new_qual_rows)
        all_quals = {
            (q.institution_id, q.name): q for q in
            db.query(Qualification).filter(Qualification.institution_id.in_(all_inst_ids)).all()
        }
        qual_module_pairs = [
            (all_quals[(inst.id, qual_name)], modules) for inst, qual_name, modules in desired_quals
        ]

        # --- modules ---
        all_qual_ids = [q.id for q, _ in qual_module_pairs]
        existing_mods = {
            (m.qualification_id, m.name) for m in
            db.query(Module).filter(Module.qualification_id.in_(all_qual_ids)).all()
        }
        new_mod_rows = []
        total_desired_modules = 0
        for qual, modules in qual_module_pairs:
            for mod_name, year_level in modules:
                total_desired_modules += 1
                if (qual.id, mod_name) not in existing_mods:
                    new_mod_rows.append({"qualification_id": qual.id, "name": mod_name, "year_level": year_level})
        skipped["modules"] = total_desired_modules - len(new_mod_rows)
        created["modules"] = len(new_mod_rows)
        if new_mod_rows:
            db.execute(sa.insert(Module), new_mod_rows)
    return {"created": created, "skipped": skipped}


def apply_as_tutor(
    *, name: str, email: str, password: str, phone: str = "", bio: str = "",
    id_number: str = "", id_verification_note: str = "",
    matric_certificate_note: str = "",
    bank_account_holder: str = "", bank_name: str = "", bank_branch_code: str = "",
    bank_account_number: str = "", bank_account_type: str = "", bank_account_note: str = "",
    cv_note: str = "", availability_note: str = "",
    wants_high_school: bool = True, wants_higher_ed: bool = False,
    subjects: list[dict] | None = None,
    higher_ed_institution_id: int | None = None,
    higher_ed_qualification_id: int | None = None,
    # "Other" escape hatch instead of higher_ed_qualification_id/
    # higher_ed_module_ids, for when the applicant's real qualification
    # isn't in the catalog - higher_ed_custom_modules is a list of
    # {"name": str, "year_level": int}, stored as TutorCustomHigherEdModule
    # rows instead of catalog-FK TutorHigherEdModule rows.
    higher_ed_qualification_custom_name: str = "",
    higher_ed_custom_modules: list[dict] | None = None,
    higher_ed_year_of_study: int | None = None,
    higher_ed_qualification_complete: bool = False,
    higher_ed_average: float | None = None,
    higher_ed_transcript_note: str = "",
    higher_ed_module_ids: list[int] | None = None,
    id_document: tuple[bytes, str] | None = None,
    matric_certificate_document: tuple[bytes, str] | None = None,
    cv_document: tuple[bytes, str] | None = None,
    bank_proof_document: tuple[bytes, str] | None = None,
    higher_ed_transcript_document: tuple[bytes, str] | None = None,
    higher_ed_qualification_certificate_document: tuple[bytes, str] | None = None,
) -> dict:
    """A prospective tutor's application, covering one or BOTH segments
    (wants_high_school / wants_higher_ed) in one submission - each has its
    own independent vetting status (status for high school, higher_ed_status
    for higher-ed - see TutorAccount), so a tutor can be approved for one
    segment while the other is still pending or gets rejected.

    PARTIAL QUALIFICATION, not all-or-nothing: an applicant can pass one
    segment (or part of one) while failing another, and the application
    still goes through for whatever DOES qualify - it's never silently
    all rejected just because one subject/module/segment didn't meet the
    bar. Concretely:
      - HIGH SCHOOL: each entry in `subjects` is checked against
        MIN_MATRIC_PERCENTAGE independently - e.g. Mathematics at 60%
        (below the 65% bar) is excluded, Physical Sciences at 68% (above
        it) still goes in for review, in the SAME submission. Only if
        every submitted subject fails is the high-school segment dropped
        entirely.
      - HIGHER-ED: higher_ed_average is a single number for the whole
        qualification, so it can't be split per-module - if it's below
        MIN_HIGHER_ED_AVERAGE, the whole higher-ed segment is excluded.
        If the average passes, each module in higher_ed_module_ids is
        still checked independently against the "at least one year
        ahead" rule (or allowed unconditionally if
        higher_ed_qualification_complete) - an ineligible module is
        excluded, not fatal to the others.
      - If EVERY segment the applicant asked for ends up excluded (e.g.
        "Both" but no subject clears 65% AND the higher-ed average is
        too low), only then does this raise - there has to be something
        left to actually review.
    The return dict's excluded_subjects/excluded_higher_ed_reason/
    excluded_modules report exactly what was left out and why, so the
    caller can tell the applicant clearly instead of them wondering why
    a session they expected isn't showing up for review.

    HIGH SCHOOL (wants_high_school=True): `subjects` is required, a list of
    {"subject": str, "matric_percentage": float, "topics": str (optional),
    "hourly_rate_zar": float (optional)}. Checked against the applicant's
    SELF-REPORTED number (not independently confirmed against
    Umalusi/SAQA - see this module's docstring).

    HIGHER-ED (wants_higher_ed=True): higher_ed_institution_id/
    qualification_id/year_of_study are required, plus higher_ed_average
    (same self-reported-not-independently-verified spirit as
    matric_percentage) and at least one entry in higher_ed_module_ids.

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

    if wants_high_school and not subjects:
        raise TutoringError("Please apply for at least one subject.")
    is_custom_qualification = bool((higher_ed_qualification_custom_name or "").strip())
    if wants_higher_ed:
        if not higher_ed_institution_id or not (higher_ed_qualification_id or is_custom_qualification):
            raise TutoringError("Please select your institution and qualification.")
        if not higher_ed_year_of_study or not (1 <= higher_ed_year_of_study <= max(YEAR_LEVEL_LABELS)):
            raise TutoringError("Please select your year of study.")
        if higher_ed_average is None:
            raise TutoringError("Please enter your semester/final average.")
        if is_custom_qualification:
            if not higher_ed_custom_modules:
                raise TutoringError("Please select at least one module you're able to tutor.")
        elif not higher_ed_module_ids:
            raise TutoringError("Please select at least one module you're able to tutor.")

    # Per-subject/per-module qualification is checked independently below
    # (see this function's docstring) - a failing one is EXCLUDED, not
    # fatal to the whole application, unless literally nothing is left.
    qualifying_subjects: list[dict] = []
    excluded_subjects: list[dict] = []
    if wants_high_school:
        for s in subjects:
            pct = s.get("matric_percentage")
            if pct is None or pct < MIN_MATRIC_PERCENTAGE:
                excluded_subjects.append({
                    "subject": s.get("subject", "that subject"), "matric_percentage": pct,
                    "reason": f"A matric mark of at least {MIN_MATRIC_PERCENTAGE:.0f}% is required.",
                })
            else:
                qualifying_subjects.append(s)

    with get_session() as db:
        existing = db.query(TutorAccount).filter(TutorAccount.email == email).first()
        if existing:
            raise TutoringError("A tutor application with this email already exists.")

        qualifying_modules: list = []
        qualifying_custom_modules: list[dict] = []
        excluded_modules: list[dict] = []
        higher_ed_excluded_reason: str | None = None
        if wants_higher_ed:
            if higher_ed_average < MIN_HIGHER_ED_AVERAGE:
                higher_ed_excluded_reason = (
                    f"A semester/final average of at least {MIN_HIGHER_ED_AVERAGE:.0f}% "
                    f"is required to apply to tutor university/college modules."
                )
            if not is_custom_qualification:
                qual = db.query(Qualification).get(higher_ed_qualification_id)
                if higher_ed_excluded_reason is None and (not qual or qual.institution_id != higher_ed_institution_id):
                    higher_ed_excluded_reason = "That qualification doesn't belong to the selected institution."
            if higher_ed_excluded_reason is None and not is_custom_qualification:
                for module_id in higher_ed_module_ids:
                    mod = db.query(Module).get(module_id)
                    if not mod:
                        excluded_modules.append({
                            "name": f"module #{module_id}", "year_level": None,
                            "reason": "This module no longer exists in the catalog.",
                        })
                    elif not higher_ed_qualification_complete and mod.year_level >= higher_ed_year_of_study:
                        excluded_modules.append({
                            "name": mod.name, "year_level": mod.year_level,
                            "reason": (
                                f"You must be at least one year ahead of \"{mod.name}\" "
                                f"({YEAR_LEVEL_LABELS.get(mod.year_level)}) to tutor it."
                            ),
                        })
                    else:
                        qualifying_modules.append(mod)
                if not qualifying_modules and higher_ed_excluded_reason is None:
                    higher_ed_excluded_reason = "None of the selected modules were eligible to tutor."
            elif higher_ed_excluded_reason is None and is_custom_qualification:
                # Same "at least one year ahead" eligibility rule as the
                # catalog path above, applied to each free-text entry
                # instead of a catalog Module row.
                for entry in higher_ed_custom_modules:
                    entry_name = (entry.get("name") or "").strip()
                    entry_year = entry.get("year_level")
                    if not entry_name or entry_year is None:
                        continue
                    if not higher_ed_qualification_complete and entry_year >= higher_ed_year_of_study:
                        excluded_modules.append({
                            "name": entry_name, "year_level": entry_year,
                            "reason": (
                                f"You must be at least one year ahead of \"{entry_name}\" "
                                f"({YEAR_LEVEL_LABELS.get(entry_year)}) to tutor it."
                            ),
                        })
                    else:
                        qualifying_custom_modules.append({"name": entry_name, "year_level": entry_year})
                if not qualifying_custom_modules and higher_ed_excluded_reason is None:
                    higher_ed_excluded_reason = "None of the selected modules were eligible to tutor."

        effective_wants_high_school = wants_high_school and bool(qualifying_subjects)
        effective_wants_higher_ed = (
            wants_higher_ed and higher_ed_excluded_reason is None
            and bool(qualifying_modules or qualifying_custom_modules)
        )

        if not effective_wants_high_school and not effective_wants_higher_ed:
            reasons = []
            if wants_high_school:
                reasons.append(f"no subject met the {MIN_MATRIC_PERCENTAGE:.0f}% matric minimum")
            if wants_higher_ed:
                reasons.append(higher_ed_excluded_reason or "no module was eligible")
            raise TutoringError("Your application doesn't qualify yet: " + "; ".join(reasons) + ".")

        wants_high_school = effective_wants_high_school
        wants_higher_ed = effective_wants_higher_ed
        higher_ed_modules = qualifying_modules

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
        bank_proof_path = None
        if bank_proof_document:
            file_bytes, content_type = bank_proof_document
            try:
                bank_proof_path = _storage.upload_tutor_document(
                    file_bytes, content_type, applicant_email=email, kind="bank_proof",
                )
            except _storage.StorageError as e:
                raise TutoringError(str(e))
        higher_ed_transcript_path = None
        if higher_ed_transcript_document:
            file_bytes, content_type = higher_ed_transcript_document
            try:
                higher_ed_transcript_path = _storage.upload_tutor_document(
                    file_bytes, content_type, applicant_email=email, kind="higher_ed_transcript",
                )
            except _storage.StorageError as e:
                raise TutoringError(str(e))
        higher_ed_qualification_certificate_path = None
        if higher_ed_qualification_certificate_document:
            file_bytes, content_type = higher_ed_qualification_certificate_document
            try:
                higher_ed_qualification_certificate_path = _storage.upload_tutor_document(
                    file_bytes, content_type, applicant_email=email, kind="higher_ed_qualification_certificate",
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
            bank_account_holder=bank_account_holder.strip() or None,
            bank_name=bank_name.strip() or None,
            bank_branch_code=bank_branch_code.strip() or None,
            bank_account_number=bank_account_number.strip() or None,
            bank_account_type=bank_account_type.strip() or None,
            bank_proof_document_path=bank_proof_path,
            bank_account_note=bank_account_note.strip() or None,
            status="pending_review",
            wants_high_school=wants_high_school,
            wants_higher_ed=wants_higher_ed,
            higher_ed_status="pending_review" if wants_higher_ed else None,
            higher_ed_institution_id=higher_ed_institution_id if wants_higher_ed else None,
            higher_ed_qualification_id=(
                higher_ed_qualification_id if wants_higher_ed and not is_custom_qualification else None
            ),
            higher_ed_qualification_custom_name=(
                higher_ed_qualification_custom_name.strip() if wants_higher_ed and is_custom_qualification else None
            ),
            higher_ed_year_of_study=higher_ed_year_of_study if wants_higher_ed else None,
            higher_ed_qualification_complete=higher_ed_qualification_complete if wants_higher_ed else False,
            higher_ed_average=higher_ed_average if wants_higher_ed else None,
            higher_ed_transcript_note=higher_ed_transcript_note.strip() or None if wants_higher_ed else None,
            higher_ed_transcript_path=higher_ed_transcript_path if wants_higher_ed else None,
            higher_ed_qualification_certificate_path=(
                higher_ed_qualification_certificate_path if wants_higher_ed else None
            ),
        )
        db.add(tutor)
        db.flush()  # assigns tutor.id before we attach subjects/modules

        if wants_high_school:
            for s in qualifying_subjects:
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
            for entry in qualifying_custom_modules:
                db.add(TutorCustomHigherEdModule(
                    tutor_id=tutor.id, name=entry["name"], year_level=entry["year_level"],
                ))

        return {
            "id": tutor.id, "status": tutor.status, "higher_ed_status": tutor.higher_ed_status,
            "excluded_subjects": excluded_subjects,
            "excluded_higher_ed_reason": higher_ed_excluded_reason if wants_higher_ed is False else None,
            "excluded_modules": excluded_modules,
        }


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
                "has_bank_proof_document": bool(t.bank_proof_document_path),
                "availability_note": t.availability_note,
                "bank_account_holder": t.bank_account_holder,
                "bank_name": t.bank_name,
                "bank_branch_code": t.bank_branch_code,
                "bank_account_number": t.bank_account_number,
                "bank_account_type": t.bank_account_type,
                "bank_account_note": t.bank_account_note,
                "status": t.status,
                "status_label": TUTOR_STATUS_LABELS.get(t.status, t.status),
                "wants_higher_ed": t.wants_higher_ed,
                "admin_notes": t.admin_notes,
                "created_at": _iso_utc(t.created_at), "reviewed_at": _iso_utc(t.reviewed_at),
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
                "has_bank_proof_document": bool(t.bank_proof_document_path),
                "availability_note": t.availability_note,
                "bank_account_holder": t.bank_account_holder,
                "bank_name": t.bank_name,
                "bank_branch_code": t.bank_branch_code,
                "bank_account_number": t.bank_account_number,
                "bank_account_type": t.bank_account_type,
                "bank_account_note": t.bank_account_note,
                "wants_high_school": t.wants_high_school,
                "higher_ed_status": t.higher_ed_status,
                "higher_ed_status_label": TUTOR_STATUS_LABELS.get(t.higher_ed_status, t.higher_ed_status),
                "higher_ed_institution": inst.name if inst else None,
                "higher_ed_qualification": qual.name if qual else t.higher_ed_qualification_custom_name,
                "higher_ed_year_of_study": t.higher_ed_year_of_study,
                "higher_ed_year_of_study_label": YEAR_LEVEL_LABELS.get(t.higher_ed_year_of_study),
                "higher_ed_qualification_complete": t.higher_ed_qualification_complete,
                "higher_ed_average": t.higher_ed_average,
                "higher_ed_transcript_note": t.higher_ed_transcript_note,
                "has_higher_ed_transcript_document": bool(t.higher_ed_transcript_path),
                "has_higher_ed_qualification_certificate_document": bool(t.higher_ed_qualification_certificate_path),
                "admin_notes": t.admin_notes,
                "created_at": _iso_utc(t.created_at), "higher_ed_reviewed_at": _iso_utc(t.higher_ed_reviewed_at),
                "modules": [
                    {
                        "id": m.module.id, "name": m.module.name,
                        "year_level": m.module.year_level,
                        "year_level_label": YEAR_LEVEL_LABELS.get(m.module.year_level),
                        "is_active": m.is_active,
                    }
                    for m in t.higher_ed_modules
                ] + [
                    # "Other" entries - no catalog Module row, so id is
                    # None (can't be deactivated the same way a catalog
                    # module can - see TutorCustomHigherEdModule).
                    {
                        "id": None, "name": m.name,
                        "year_level": m.year_level,
                        "year_level_label": YEAR_LEVEL_LABELS.get(m.year_level),
                        "is_active": True,
                    }
                    for m in t.higher_ed_custom_modules
                ],
            })
        return out


def get_tutor_document_url(tutor_id: int, kind: str) -> str:
    """A short-lived signed URL for an admin to view one of a tutor
    applicant's uploaded documents. `kind` is "id", "matric_certificate",
    "cv", "bank_proof", "higher_ed_transcript", or
    "higher_ed_qualification_certificate"."""
    if kind not in (
        "id", "matric_certificate", "cv", "bank_proof",
        "higher_ed_transcript", "higher_ed_qualification_certificate",
    ):
        raise TutoringError("Unknown document kind.")
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        path = {
            "id": tutor.id_document_path,
            "matric_certificate": tutor.matric_certificate_path,
            "cv": tutor.cv_document_path,
            "bank_proof": tutor.bank_proof_document_path,
            "higher_ed_transcript": tutor.higher_ed_transcript_path,
            "higher_ed_qualification_certificate": tutor.higher_ed_qualification_certificate_path,
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
    _notify_tutor_of_decision(tutor_id, email, name, approved=True)


def reject_tutor(tutor_id: int, reason: str = "") -> None:
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor application not found.")
        tutor.status = "rejected"
        tutor.admin_notes = reason.strip() or None
        tutor.reviewed_at = dt.datetime.utcnow()
        name, email = tutor.name, tutor.email
    _notify_tutor_of_decision(tutor_id, email, name, approved=False, reason=reason)


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
    _notify_tutor_of_decision(tutor_id, email, name, approved=True)


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
    _notify_tutor_of_decision(tutor_id, email, name, approved=False, reason=reason)


def _notify_tutor_of_decision(
    tutor_id: int, email: str, name: str, *, approved: bool, reason: str = "",
) -> None:
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
            notif_title = "Application approved!"
            notif_body = "Your tutor application has been approved."
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
            notif_title = "Application update"
            notif_body = "Your tutor application wasn't approved." + (f" Reason: {reason}" if reason else "")
        send_email(email, subject, body)
        create_notification(recipient_kind="tutor", recipient_id=tutor_id, title=notif_title, body=notif_body)
    except Exception:
        logger.exception("Failed to notify tutor applicant %s of application decision", email)


def list_approved_tutors(subject: str | None = None, module_id: int | None = None) -> list[dict]:
    """Approved tutors, optionally filtered to ones who teach a given
    high-school subject or higher-ed module. Used both as an admin
    helper when matching a request, AND (see list_tutors_directory) as
    the public-facing "Browse Tutors" directory - includes each tutor's
    completed-session count, bio, availability, and asking rates, so a
    learner can pick a specific tutor directly instead of broadcasting a
    request. An approved tutor's record never goes away, the same way
    you'd keep recalling a reliable employee for new work rather than
    starting over with someone untested each time."""
    with get_session() as db:
        # A tutor can be approved on EITHER track independently (see
        # TutorAccount's own docstring) - filtering on status alone would
        # silently drop every tutor approved only for higher-ed (status
        # stays its pending_review default forever if they never applied
        # for high school too), which would have made them invisible as
        # match candidates for exactly the higher-ed requests they can
        # actually tutor.
        q = db.query(TutorAccount).filter(
            sa.or_(TutorAccount.status == "approved", TutorAccount.higher_ed_status == "approved")
        )
        out = []
        for t in q.all():
            subjects = [s for s in t.subjects if s.is_active] if t.status == "approved" else []
            if subject and not any(s.subject == subject for s in subjects):
                continue
            higher_ed_modules = (
                [m for m in t.higher_ed_modules if m.is_active]
                if t.higher_ed_status == "approved" else []
            )
            if module_id and not any(m.module_id == module_id for m in higher_ed_modules):
                continue
            sessions_completed = (
                db.query(TutoringSessionRequest)
                .filter(TutoringSessionRequest.tutor_id == t.id, TutoringSessionRequest.status == "completed")
                .count()
            )
            # The tutor's OWN declared higher-ed qualification (not the
            # per-module catalog rows below) - this, not a catalog match,
            # is what an admin actually needs to judge whether a tutor
            # suits a custom ("Other") module request, e.g. confirming a
            # Mathematics module isn't being claimed by a Psychology
            # student just because their year of study is high enough.
            higher_ed_profile = None
            if t.higher_ed_status == "approved":
                qual = db.query(Qualification).get(t.higher_ed_qualification_id) if t.higher_ed_qualification_id else None
                inst = db.query(Institution).get(t.higher_ed_institution_id) if t.higher_ed_institution_id else None
                higher_ed_profile = {
                    "institution": inst.name if inst else None,
                    "qualification": qual.name if qual else t.higher_ed_qualification_custom_name,
                    "year_of_study": t.higher_ed_year_of_study,
                    "year_of_study_label": YEAR_LEVEL_LABELS.get(t.higher_ed_year_of_study),
                    "qualification_complete": t.higher_ed_qualification_complete,
                    "custom_modules": [
                        {"name": m.name, "year_level": m.year_level, "year_level_label": YEAR_LEVEL_LABELS.get(m.year_level)}
                        for m in t.higher_ed_custom_modules
                    ],
                }
            out.append({
                "id": t.id, "name": t.name, "email": t.email,
                "bio": t.bio, "availability_note": t.availability_note,
                "sessions_completed": sessions_completed,
                "higher_ed_profile": higher_ed_profile,
                "subjects": [
                    {"subject": s.subject, "matric_percentage": s.matric_percentage,
                     "topics": s.topics, "hourly_rate_zar": s.hourly_rate_zar}
                    for s in subjects
                ],
                "higher_ed_modules": [
                    {
                        "id": m.module.id, "name": m.module.name,
                        "year_level": m.module.year_level,
                        "year_level_label": YEAR_LEVEL_LABELS.get(m.module.year_level),
                        "qualification": m.module.qualification.name if m.module.qualification else None,
                        "qualification_id": m.module.qualification_id,
                        "institution": (
                            m.module.qualification.institution.name
                            if m.module.qualification and m.module.qualification.institution else None
                        ),
                        "institution_id": (
                            m.module.qualification.institution_id
                            if m.module.qualification else None
                        ),
                    }
                    for m in higher_ed_modules
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
    _expire_lapsed_payments()
    _expire_stale_admin_proposals()
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
            # other_start is naive UTC like every scheduled_at - format it
            # in SAST (_format_sast) to match what the learner actually
            # picked on the Hour (SAST)/Minute pickers, not raw UTC (which
            # read 2 hours behind whatever time they'd just selected).
            raise TutoringError(
                f"{who} a session scheduled around {_format_sast(other_start)} - "
                f"sessions need at least {SCHEDULING_BUFFER_MINUTES} minutes' gap between them. "
                "Please choose a different time."
            )


def _validate_request_fields(
    db, *, learner_user_id: int, subject: str, price_zar: float,
    scheduled_at: dt.datetime, duration_minutes: int, module_id: int | None,
    preferred_tutor_id: int | None, exclude_request_id: int | None = None,
    is_custom_higher_ed: bool = False, topic: str = "",
    institution_id: int | None = None, grade: int | None = None,
) -> None:
    """Shared validation for request_tutoring_session (new) and
    edit_tutoring_request (in place) - raises TutoringError on any
    problem, otherwise returns None."""
    if not topic or not topic.strip():
        raise TutoringError("Please enter a topic for this session.")
    # institution_id is always set for a higher-ed request (catalog or
    # custom module alike - see TutoringSessionRequest's docstring), so
    # its absence is what marks this as a high-school request, which is
    # the only kind that carries a CAPS grade.
    if institution_id is None and grade not in (10, 11, 12):
        raise TutoringError("Please select your grade (10, 11 or 12).")
    if price_zar is None or price_zar <= 0:
        raise TutoringError("Please set a price greater than R0 for this session.")
    if not duration_minutes or duration_minutes < MIN_SESSION_DURATION_MINUTES:
        raise TutoringError(f"Sessions must be at least {MIN_SESSION_DURATION_MINUTES} minutes long.")
    if not scheduled_at:
        raise TutoringError("Please choose a date and time for this session.")
    if scheduled_at < dt.datetime.utcnow() + dt.timedelta(hours=MIN_REQUEST_LEAD_HOURS):
        raise TutoringError(f"Sessions must be requested at least {MIN_REQUEST_LEAD_HOURS} hours in advance.")
    if module_id is not None and not db.query(Module).get(module_id):
        raise TutoringError("That module no longer exists.")
    # A custom ("Other") module has no catalog Module row for any tutor to
    # match against - it can't be directed at one specific tutor via
    # preferred_tutor_id (which relies on checking that tutor's own
    # catalog subjects/modules), only broadcast for an admin to manually
    # match (see list_open_requests/match_tutor_to_request).
    if is_custom_higher_ed and preferred_tutor_id is not None:
        raise TutoringError(
            "A specific tutor can't be requested directly for a module that's not in the catalog yet - "
            "submit this request and an admin will match it to a suitable tutor."
        )
    if preferred_tutor_id is not None:
        tutor = db.query(TutorAccount).get(preferred_tutor_id)
        if not tutor:
            raise TutoringError("That tutor no longer exists.")
        subjects, module_ids = _tutor_eligible_subjects_and_modules(db, tutor)
        eligible = (module_id in module_ids) if module_id is not None else (subject in subjects)
        if not eligible:
            raise TutoringError("That tutor doesn't teach this subject/module.")
    _check_schedule_conflict(
        db, kind="learner", person_id=learner_user_id,
        scheduled_at=scheduled_at, duration_minutes=duration_minutes,
        exclude_request_id=exclude_request_id,
    )


def _notify_directed_request(
    *, tutor_id: int, tutor_name: str, tutor_email: str, learner_name: str,
    subject: str, topic: str | None, price_zar: float, duration_minutes: int,
    scheduled_at: dt.datetime | None,
) -> None:
    """Best-effort - tells a tutor a learner picked them directly from
    the Browse Tutors directory (see request_tutoring_session's
    preferred_tutor_id), same pattern as _notify_match. Broadcast
    requests (no preferred tutor) are deliberately NOT emailed to every
    eligible tutor - they just show up in each one's own Open Requests
    queue - but a directed request is aimed at exactly one tutor, who
    would otherwise have no way to know it's waiting for them."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        send_email(
            tutor_email,
            "A learner requested you directly on Malita",
            (
                f"Hi {tutor_name},\n\n"
                f"{learner_name} requested you directly for {subject}{topic_str}.\n\n"
                f"Price: R{price_zar:.2f} ({duration_minutes} min)\n"
                f"Requested time: {when_str}\n\n"
                "Open the Malita Tutor app to accept it (or propose a different time) - "
                "only you can see this request.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="A learner requested you directly",
            body=f"{learner_name} requested you for {subject}{topic_str} at R{price_zar:.2f} ({duration_minutes} min).",
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of a directed request", tutor_email)


def request_tutoring_session(
    learner_user_id: int, subject: str, price_zar: float, scheduled_at: dt.datetime,
    duration_minutes: int = 60, topic: str = "", preferred_times_note: str = "",
    module_id: int | None = None, preferred_tutor_id: int | None = None,
    custom_module_name: str | None = None, custom_module_year_level: int | None = None,
    institution_id: int | None = None, qualification_id: int | None = None,
    custom_qualification_name: str | None = None, grade: int | None = None,
) -> dict:
    """A learner asking for a tutor, inDrive-style: the LEARNER sets the
    price, exact date/time, and duration right here, and the request
    then sits open for any approved tutor who teaches `subject` to
    accept at that price/time (see list_open_requests_for_tutor/
    accept_tutoring_request) - available regardless of subscription
    tier, since tutoring is billed separately. Must be requested at
    least MIN_REQUEST_LEAD_HOURS in advance (a tutor's own counter-
    proposal isn't held to this - see propose_new_time).

    module_id (higher-ed requests only): a catalog Module, in which case
    `subject` is expected to already be that module's own display name
    (the caller - api_server.py - looks it up) and matching uses
    TutorHigherEdModule instead of TutorSubject (see
    list_open_requests_for_tutor). Leave None for a high-school request,
    matched by `subject` against TutorSubject as before.

    preferred_tutor_id: set when the learner picked a specific tutor
    from the directory (see list_approved_tutors) instead of
    broadcasting - while still "requested", only this tutor sees it in
    their open-requests queue (see list_open_requests_for_tutor), but
    every subsequent step (accept, propose, notify, Meet link) is
    otherwise identical to a broadcast request."""
    preferred_tutor_notify: tuple | None = None
    with get_session() as db:
        learner = db.query(User).get(learner_user_id)
        if not learner:
            raise TutoringError("Account not found.")
        learner_name = learner.name
        _validate_request_fields(
            db, learner_user_id=learner_user_id, subject=subject, price_zar=price_zar,
            scheduled_at=scheduled_at, duration_minutes=duration_minutes,
            module_id=module_id, preferred_tutor_id=preferred_tutor_id,
            is_custom_higher_ed=bool(custom_module_name), topic=topic,
            institution_id=institution_id, grade=grade,
        )
        req = TutoringSessionRequest(
            learner_user_id=learner_user_id,
            subject=subject,
            module_id=module_id,
            custom_module_name=custom_module_name.strip() if custom_module_name else None,
            custom_module_year_level=custom_module_year_level if custom_module_name else None,
            is_custom_higher_ed=bool(custom_module_name),
            institution_id=institution_id,
            qualification_id=qualification_id,
            custom_qualification_name=custom_qualification_name.strip() if custom_qualification_name else None,
            preferred_tutor_id=preferred_tutor_id,
            grade=grade if institution_id is None else None,
            topic=topic.strip() or None,
            preferred_times_note=preferred_times_note.strip() or None,
            price_zar=price_zar,
            duration_minutes=duration_minutes,
            scheduled_at=scheduled_at,
            status="requested",
        )
        db.add(req)
        db.flush()
        result = {"id": req.id, "status": req.status}
        if preferred_tutor_id:
            tutor = db.query(TutorAccount).get(preferred_tutor_id)
            if tutor:
                preferred_tutor_notify = (tutor.name, tutor.email)
    if preferred_tutor_notify:
        tutor_name, tutor_email = preferred_tutor_notify
        _notify_directed_request(
            tutor_id=preferred_tutor_id, tutor_name=tutor_name, tutor_email=tutor_email, learner_name=learner_name,
            subject=subject, topic=topic, price_zar=price_zar,
            duration_minutes=duration_minutes, scheduled_at=scheduled_at,
        )
    return result


def edit_tutoring_request(
    request_id: int, learner_user_id: int, *, subject: str, price_zar: float,
    scheduled_at: dt.datetime, duration_minutes: int = 60, topic: str = "",
    preferred_times_note: str = "", module_id: int | None = None,
    preferred_tutor_id: int | None = None, custom_module_name: str | None = None,
    custom_module_year_level: int | None = None, institution_id: int | None = None,
    qualification_id: int | None = None, custom_qualification_name: str | None = None,
    grade: int | None = None,
) -> dict:
    """The learner editing their own request while it's still fully open
    (status=="requested", not yet touched by any tutor) - re-runs the
    exact same validation request_tutoring_session does (lead time,
    conflict check excluding this row, preferred-tutor eligibility)
    since any of these fields could have changed to something invalid."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.learner_user_id != learner_user_id:
            raise TutoringError("Request not found.")
        if req.status != "requested":
            raise TutoringError(f"This request is '{req.status}' and can no longer be edited.")
        _validate_request_fields(
            db, learner_user_id=learner_user_id, subject=subject, price_zar=price_zar,
            scheduled_at=scheduled_at, duration_minutes=duration_minutes,
            module_id=module_id, preferred_tutor_id=preferred_tutor_id,
            exclude_request_id=req.id, is_custom_higher_ed=bool(custom_module_name), topic=topic,
            institution_id=institution_id, grade=grade,
        )
        req.subject = subject
        req.module_id = module_id
        req.custom_module_name = custom_module_name.strip() if custom_module_name else None
        req.custom_module_year_level = custom_module_year_level if custom_module_name else None
        req.is_custom_higher_ed = bool(custom_module_name)
        req.institution_id = institution_id
        req.qualification_id = qualification_id
        req.custom_qualification_name = custom_qualification_name.strip() if custom_qualification_name else None
        req.preferred_tutor_id = preferred_tutor_id
        req.grade = grade if institution_id is None else None
        req.topic = topic.strip() or None
        req.preferred_times_note = preferred_times_note.strip() or None
        req.price_zar = price_zar
        req.duration_minutes = duration_minutes
        req.scheduled_at = scheduled_at
        return {"id": req.id, "status": req.status}


def withdraw_tutoring_request(request_id: int, learner_user_id: int) -> dict:
    """The learner withdrawing their own request before a tutor has
    fully accepted it (status in "requested"/"time_proposed" - once
    awaiting_payment or beyond, use cancel_accepted_session instead,
    which enforces the 24-hour cutoff). If a tutor had proposed a time
    (time_proposed), they're notified the request was withdrawn
    entirely - distinct from respond_to_time_proposal's decline, which
    just reopens it for them or anyone else to try again."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.learner_user_id != learner_user_id:
            raise TutoringError("Request not found.")
        if req.status not in ("requested", "time_proposed"):
            raise TutoringError(
                f"This request is '{req.status}' - once a tutor has accepted it, cancel it instead."
            )
        notify_tutor = None
        if req.status == "time_proposed" and req.tutor_id:
            tutor = db.query(TutorAccount).get(req.tutor_id)
            if tutor:
                notify_tutor = (tutor.id, tutor.name, tutor.email)
        learner = db.query(User).get(learner_user_id)
        learner_name = learner.name
        subject, topic = req.subject, req.topic

        req.status = "cancelled"
        req.cancelled_at = dt.datetime.utcnow()
        req.cancelled_by = "learner"
        result = {"id": req.id, "status": req.status}

    if notify_tutor:
        _notify_request_withdrawn(
            tutor_id=notify_tutor[0], tutor_name=notify_tutor[1], tutor_email=notify_tutor[2],
            learner_name=learner_name, subject=subject, topic=topic,
        )
    return result


def _expire_lapsed_payments() -> None:
    """Lazy check (same spirit as backend/auth.py's get_user_tier lazy
    pending_tier downgrade - no cron job needed at this scale), run at
    the top of every listing function below: any request still
    "awaiting_payment" more than PAYMENT_DEADLINE_HOURS after being
    matched automatically lapses. A lapsed request is a dead end - the
    learner has to submit a fresh request, it's never silently reopened
    for other tutors. Its own self-contained transaction, so every
    caller can just call this first without threading a shared db
    session through."""
    to_notify = []
    with get_session() as db:
        cutoff = dt.datetime.utcnow() - dt.timedelta(hours=PAYMENT_DEADLINE_HOURS)
        overdue = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "awaiting_payment",
                TutoringSessionRequest.matched_at < cutoff,
            )
            .all()
        )
        for req in overdue:
            req.status = "lapsed"
            req.lapsed_at = dt.datetime.utcnow()
            learner = db.query(User).get(req.learner_user_id)
            tutor = db.query(TutorAccount).get(req.tutor_id)
            if learner and tutor:
                to_notify.append((
                    learner.id, learner.name, learner.email,
                    tutor.id, tutor.name, tutor.email, req.subject, req.topic,
                ))

    for learner_id, learner_name, learner_email, tutor_id, tutor_name, tutor_email, subject, topic in to_notify:
        _notify_payment_lapsed(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
            subject=subject, topic=topic,
        )


def _notify_payment_lapsed(
    *, learner_id: int, learner_name: str, learner_email: str,
    tutor_id: int, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None,
) -> None:
    """Best-effort - tells both sides a match lapsed because the learner
    didn't pay within PAYMENT_DEADLINE_HOURS."""
    try:
        topic_str = f" ({topic})" if topic else ""
        send_email(
            learner_email,
            "Your tutoring session request has lapsed",
            (
                f"Hi {learner_name},\n\n"
                f"Your match with {tutor_name} for {subject}{topic_str} has lapsed because "
                f"payment wasn't completed within {PAYMENT_DEADLINE_HOURS} hours. "
                "If you still need a tutor, please submit a new request.\n\n"
                "— The Malita team"
            ),
        )
        send_email(
            tutor_email,
            "A matched session has lapsed",
            (
                f"Hi {tutor_name},\n\n"
                f"Your match with {learner_name} for {subject}{topic_str} has lapsed because "
                f"they didn't complete payment within {PAYMENT_DEADLINE_HOURS} hours. "
                "No action needed on your end.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Session request lapsed",
            body=f"Your match with {tutor_name} for {subject}{topic_str} lapsed - payment wasn't completed in time.",
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="A matched session lapsed",
            body=f"Your match with {learner_name} for {subject}{topic_str} lapsed - no action needed.",
        )
    except Exception:
        logger.exception("Failed to notify learner/tutor of a lapsed payment")


def _expire_stale_admin_proposals() -> None:
    """Lazy check (same spirit/pattern as _expire_lapsed_payments above),
    run at the same call sites: any request still "admin_proposed" more
    than ADMIN_PROPOSAL_DEADLINE_HOURS after an admin suggested a tutor,
    with no response either way, automatically reopens - unlike a lapsed
    payment, this IS reopened for another tutor (or a fresh admin
    suggestion), since nothing was ever agreed to, just proposed."""
    to_notify = []
    with get_session() as db:
        cutoff = dt.datetime.utcnow() - dt.timedelta(hours=ADMIN_PROPOSAL_DEADLINE_HOURS)
        overdue = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "admin_proposed",
                TutoringSessionRequest.admin_proposed_at < cutoff,
            )
            .all()
        )
        for req in overdue:
            tutor = db.query(TutorAccount).get(req.tutor_id)
            subject, topic = req.subject, req.topic
            req.tutor_id = None
            req.proposed_scheduled_at = None
            req.admin_proposed_at = None
            req.status = "requested"
            if tutor:
                to_notify.append((tutor.id, tutor.name, tutor.email, subject, topic))

    for tutor_id, tutor_name, tutor_email, subject, topic in to_notify:
        _notify_admin_proposal_expired(
            tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email, subject=subject, topic=topic,
        )


def _notify_admin_proposal_expired(
    *, tutor_id: int, tutor_name: str, tutor_email: str, subject: str, topic: str | None,
) -> None:
    """Best-effort - tells the tutor their window to respond to an
    admin-suggested match ran out, same spirit as _notify_payment_lapsed."""
    try:
        topic_str = f" ({topic})" if topic else ""
        send_email(
            tutor_email,
            "An admin-suggested match has expired",
            (
                f"Hi {tutor_name},\n\n"
                f"The {subject}{topic_str} session an admin suggested for you wasn't confirmed within "
                f"{ADMIN_PROPOSAL_DEADLINE_HOURS} hours, so it's been reopened. No action needed on your end - "
                "if you're still interested, check your Open Requests.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="Admin-suggested match expired",
            body=f"The {subject}{topic_str} session wasn't confirmed in time, so it's been reopened.",
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of an expired admin proposal", tutor_email)


def send_due_reminders() -> None:
    """Time-triggered reminders that can't piggyback on the lazy-check
    pattern used elsewhere in this module (_expire_lapsed_payments,
    get_user_tier's pending_tier downgrade) - those only fire when
    someone happens to load a listing, but a reminder has to go out at a
    specific wall-clock moment whether or not anyone opens the app right
    then. Meant to be polled roughly once a minute by a background loop
    (see api_server.py's startup hook) rather than run lazily. Each of
    the three reminders below fires exactly once per session/request,
    guarded by its own `*_sent_at` column, so a dropped poll or a
    slightly-late one just means a reminder goes out a little later -
    never twice, and never silently skipped."""
    now = dt.datetime.utcnow()
    to_notify_upcoming = []
    to_notify_lapsing = []
    with get_session() as db:
        due_24h = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "confirmed",
                TutoringSessionRequest.scheduled_at != None,  # noqa: E711
                TutoringSessionRequest.scheduled_at > now,
                TutoringSessionRequest.scheduled_at <= now + dt.timedelta(hours=SESSION_REMINDER_HOURS_BEFORE),
                TutoringSessionRequest.reminder_24h_sent_at.is_(None),
            )
            .all()
        )
        for req in due_24h:
            req.reminder_24h_sent_at = now
            learner = db.query(User).get(req.learner_user_id)
            tutor = db.query(TutorAccount).get(req.tutor_id)
            if learner and tutor:
                to_notify_upcoming.append((
                    learner.id, learner.name, learner.email, tutor.id, tutor.name, tutor.email,
                    req.subject, req.topic, req.scheduled_at, req.meet_link, "in about 24 hours",
                ))

        due_15m = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "confirmed",
                TutoringSessionRequest.scheduled_at != None,  # noqa: E711
                TutoringSessionRequest.scheduled_at > now,
                TutoringSessionRequest.scheduled_at <= now + dt.timedelta(minutes=SESSION_REMINDER_MINUTES_BEFORE),
                TutoringSessionRequest.reminder_15m_sent_at.is_(None),
            )
            .all()
        )
        for req in due_15m:
            req.reminder_15m_sent_at = now
            learner = db.query(User).get(req.learner_user_id)
            tutor = db.query(TutorAccount).get(req.tutor_id)
            if learner and tutor:
                to_notify_upcoming.append((
                    learner.id, learner.name, learner.email, tutor.id, tutor.name, tutor.email,
                    req.subject, req.topic, req.scheduled_at, req.meet_link, "in about 15 minutes",
                ))

        lapse_cutoff = now - dt.timedelta(
            hours=PAYMENT_DEADLINE_HOURS - PAYMENT_LAPSE_REMINDER_HOURS_BEFORE
        )
        lapsing_soon = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "awaiting_payment",
                TutoringSessionRequest.matched_at != None,  # noqa: E711
                TutoringSessionRequest.matched_at <= lapse_cutoff,
                TutoringSessionRequest.lapse_reminder_sent_at.is_(None),
            )
            .all()
        )
        for req in lapsing_soon:
            req.lapse_reminder_sent_at = now
            learner = db.query(User).get(req.learner_user_id)
            tutor = db.query(TutorAccount).get(req.tutor_id)
            if learner:
                hours_left = max(
                    0,
                    round((req.matched_at + dt.timedelta(hours=PAYMENT_DEADLINE_HOURS) - now).total_seconds() / 3600),
                )
                to_notify_lapsing.append((
                    learner.id, learner.name, learner.email, tutor.name if tutor else "your tutor",
                    req.subject, req.topic, hours_left,
                ))

    for (
        learner_id, learner_name, learner_email, tutor_id, tutor_name, tutor_email,
        subject, topic, scheduled_at, meet_link, when_label,
    ) in to_notify_upcoming:
        _notify_session_upcoming(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
            subject=subject, topic=topic, scheduled_at=scheduled_at,
            meet_link=meet_link, when_label=when_label,
        )
    for learner_id, learner_name, learner_email, tutor_name, subject, topic, hours_left in to_notify_lapsing:
        _notify_payment_lapsing_soon(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_name=tutor_name,
            subject=subject, topic=topic, hours_left=hours_left,
        )


def _notify_session_upcoming(
    *, learner_id: int, learner_name: str, learner_email: str,
    tutor_id: int, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None, scheduled_at: dt.datetime | None,
    meet_link: str | None, when_label: str,
) -> None:
    """Best-effort - tells BOTH sides a confirmed session is coming up
    (fired once at SESSION_REMINDER_HOURS_BEFORE and once again at
    SESSION_REMINDER_MINUTES_BEFORE, see send_due_reminders)."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        link_note = f"\n\nJoin here: {meet_link}" if meet_link else ""
        send_email(
            learner_email,
            f"Reminder: your tutoring session is {when_label}",
            (
                f"Hi {learner_name},\n\n"
                f"Your {subject}{topic_str} session with {tutor_name} is {when_label}, "
                f"scheduled for {when_str}.{link_note}\n\n"
                "— The Malita team"
            ),
        )
        send_email(
            tutor_email,
            f"Reminder: your tutoring session is {when_label}",
            (
                f"Hi {tutor_name},\n\n"
                f"Your {subject}{topic_str} session with {learner_name} is {when_label}, "
                f"scheduled for {when_str}.{link_note}\n\n"
                f"{RECORDING_REMINDER_NOTE}\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title=f"Session {when_label}",
            body=f"Your {subject}{topic_str} session with {tutor_name} is {when_label}.",
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title=f"Session {when_label}",
            body=f"Your {subject}{topic_str} session with {learner_name} is {when_label}.",
        )
    except Exception:
        logger.exception("Failed to send an upcoming-session reminder")


def _notify_payment_lapsing_soon(
    *, learner_id: int, learner_name: str, learner_email: str, tutor_name: str,
    subject: str, topic: str | None, hours_left: int,
) -> None:
    """Best-effort - warns the LEARNER only (they're the one who owes the
    payment) that their match is about to lapse."""
    try:
        topic_str = f" ({topic})" if topic else ""
        hours_str = f"{hours_left} hour{'s' if hours_left != 1 else ''}"
        send_email(
            learner_email,
            "Your tutoring session payment is due soon",
            (
                f"Hi {learner_name},\n\n"
                f"Your match with {tutor_name} for {subject}{topic_str} will lapse in "
                f"about {hours_str} unless you complete payment before then. Once it "
                "lapses you'll need to submit a new request.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Payment due soon",
            body=f"Your match with {tutor_name} for {subject}{topic_str} lapses in about {hours_str}.",
        )
    except Exception:
        logger.exception("Failed to send a payment-lapsing-soon reminder to %s", learner_email)


def list_learner_requests(learner_user_id: int) -> list[dict]:
    _expire_lapsed_payments()
    _expire_stale_admin_proposals()
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


def list_pending_custom_claims() -> list[dict]:
    """Admin visibility: custom ("Other") module requests a tutor has
    already claimed (see accept_tutoring_request) but that aren't
    finalized yet - year-level eligibility alone can't confirm the
    module is actually in that tutor's field, so these sit here until an
    admin approves or rejects them (see respond_to_custom_module_claim).
    Separate from list_open_requests, which only covers status=="requested"
    (not yet claimed by anyone)."""
    with get_session() as db:
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(TutoringSessionRequest.status == "pending_admin_approval")
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def list_all_tutoring_sessions(
    upcoming_only: bool = False, completed_only: bool = False, lapsed_only: bool = False,
) -> list[dict]:
    """Admin visibility into every MATCHED session (one with a tutor
    assigned) - not the still-open/unmatched requests, which
    list_open_requests already covers. Includes both sides' names/emails
    so an admin can see the full picture (subject, topic, schedule,
    duration, price, status) for upcoming sessions (awaiting_payment,
    confirmed) and completed ones alike, without digging through each
    tutor's individual profile."""
    _expire_lapsed_payments()
    _expire_stale_admin_proposals()
    with get_session() as db:
        q = db.query(TutoringSessionRequest).filter(TutoringSessionRequest.tutor_id.isnot(None))
        if upcoming_only:
            q = q.filter(TutoringSessionRequest.status.in_(("awaiting_payment", "confirmed")))
        elif completed_only:
            q = q.filter(TutoringSessionRequest.status == "completed")
        elif lapsed_only:
            q = q.filter(TutoringSessionRequest.status == "lapsed")
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
                "scheduled_at": _iso_utc(r.scheduled_at), "duration_minutes": r.duration_minutes,
                "price_zar": r.price_zar, "platform_cut_percent": r.platform_cut_percent,
                "meet_link": r.meet_link,
                "recording_link": r.recording_link,
                "learner_rating": r.learner_rating, "tutor_rating": r.tutor_rating,
                "created_at": _iso_utc(r.created_at), "matched_at": _iso_utc(r.matched_at),
                "paid_at": _iso_utc(r.paid_at),
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
    _expire_lapsed_payments()
    _expire_stale_admin_proposals()
    with get_session() as db:
        tutor = db.query(TutorAccount).get(tutor_id)
        if not tutor:
            raise TutoringError("Tutor account not found.")
        subjects, module_ids = _tutor_eligible_subjects_and_modules(db, tutor)
        # A custom ("Other") module has no catalog Module row, so it can't
        # be matched by id - broadcast it to every higher-ed-approved
        # tutor who's year-eligible instead (same "at least one year
        # ahead" rule the catalog uses - see
        # _tutor_eligible_for_custom_module), same as a high-school
        # request broadcasts by subject string. Accepting one of these
        # doesn't finalize it though (see accept_tutoring_request) - year
        # level alone can't confirm the module is even in the tutor's
        # actual field, so an admin still has to sign off before the
        # learner ever sees it as accepted.
        custom_eligible = tutor.higher_ed_status == "approved"
        if not subjects and not module_ids and not custom_eligible:
            return []
        filters = []
        if subjects:
            filters.append(sa.and_(
                TutoringSessionRequest.module_id.is_(None),
                TutoringSessionRequest.is_custom_higher_ed.is_(False),
                TutoringSessionRequest.subject.in_(subjects),
            ))
        if module_ids:
            filters.append(TutoringSessionRequest.module_id.in_(module_ids))
        if custom_eligible:
            if tutor.higher_ed_qualification_complete or tutor.higher_ed_year_of_study is None:
                custom_filter = TutoringSessionRequest.is_custom_higher_ed.is_(True)
            else:
                custom_filter = sa.and_(
                    TutoringSessionRequest.is_custom_higher_ed.is_(True),
                    sa.or_(
                        TutoringSessionRequest.custom_module_year_level.is_(None),
                        TutoringSessionRequest.custom_module_year_level < tutor.higher_ed_year_of_study,
                    ),
                )
            filters.append(custom_filter)
        if not filters:
            return []
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(
                TutoringSessionRequest.status == "requested",
                sa.or_(*filters),
                # A request directed at a specific tutor (see
                # request_tutoring_session's preferred_tutor_id) is only
                # ever visible to that one tutor, not broadcast to others.
                sa.or_(
                    TutoringSessionRequest.preferred_tutor_id.is_(None),
                    TutoringSessionRequest.preferred_tutor_id == tutor_id,
                ),
            )
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


def _serialize_request(r: TutoringSessionRequest) -> dict:
    return {
        "id": r.id, "learner_user_id": r.learner_user_id, "subject": r.subject,
        "module_id": r.module_id,
        "custom_module_name": r.custom_module_name,
        "custom_module_year_level": r.custom_module_year_level,
        "custom_qualification_name": r.custom_qualification_name,
        "admin_match_note": r.admin_match_note,
        "is_custom_higher_ed": r.is_custom_higher_ed,
        # Only set for a higher-ed request - lets the mobile edit flow
        # pre-select the Institution/Qualification/Module cascade without
        # a separate reverse-lookup endpoint. Stored directly on the row
        # (see TutoringSessionRequest's own docstring) rather than
        # derived through module_id, since that derivation breaks for a
        # custom module (module_id NULL) even when the institution/
        # qualification themselves were real catalog picks.
        "institution_id": r.institution_id,
        "qualification_id": r.qualification_id,
        "module_year_level": r.module.year_level if r.module else None,
        "learner_name": r.learner.name if r.learner else None,
        "grade": r.grade,
        "topic": r.topic, "preferred_times_note": r.preferred_times_note,
        "status": r.status,
        "status_label": SESSION_STATUS_LABELS.get(r.status, r.status),
        "tutor_id": r.tutor_id,
        "tutor_name": r.tutor.name if r.tutor else None,
        "preferred_tutor_id": r.preferred_tutor_id,
        "preferred_tutor_name": r.preferred_tutor.name if r.preferred_tutor else None,
        "duration_minutes": r.duration_minutes, "price_zar": r.price_zar,
        "platform_cut_percent": r.platform_cut_percent,
        "scheduled_at": _iso_utc(r.scheduled_at), "proposed_scheduled_at": _iso_utc(r.proposed_scheduled_at),
        "created_at": _iso_utc(r.created_at),
        "matched_at": _iso_utc(r.matched_at), "paid_at": _iso_utc(r.paid_at),
        "meet_link": r.meet_link,
        "learner_confirmed": r.learner_confirmed_at is not None,
        "learner_rating": r.learner_rating,
        "tutor_confirmed": r.tutor_confirmed_at is not None,
        "tutor_rating": r.tutor_rating,
        "cancelled_by": r.cancelled_by,
        "cancellation_reason": r.cancellation_reason,
        "refund_requested_at": _iso_utc(r.refund_requested_at),
        "refund_processed_at": _iso_utc(r.refund_processed_at),
        "lapsed_at": _iso_utc(r.lapsed_at),
        "recording_link": r.recording_link,
        "recording_shared_at": _iso_utc(r.recording_shared_at),
    }


def _assign_tutor_to_request(db, req: TutoringSessionRequest, tutor: TutorAccount) -> None:
    """Shared by accept_tutoring_request, respond_to_time_proposal (on
    approval), and match_tutor_to_request (admin override) - moves the
    request to awaiting_payment and snapshots the platform cut. Caller
    has already validated the tutor is eligible; this just does the
    assignment.

    The Google Meet session is deliberately NOT created here for a
    fresh (unpaid) match - see mark_session_paid, which creates it once
    the learner has actually paid, so a session that never gets paid
    for (and lapses) never had a real Meet link sitting unused. The one
    exception: if req.paid_at is already set, this is a RE-allocation
    after a previous tutor cancelled an already-paid session (see
    reallocate_after_tutor_cancellation) - the learner doesn't pay
    twice, so this skips straight to "confirmed" (leaving the original
    m_payment_id alone) and creates the Meet link immediately, since
    there's no future payment event left to create it at."""
    req.tutor_id = tutor.id
    req.platform_cut_percent = DEFAULT_PLATFORM_CUT_PERCENT
    req.matched_at = dt.datetime.utcnow()
    if req.paid_at is not None:
        req.status = "confirmed"
        _create_meet_session_for_request(db, req, tutor)
    else:
        req.status = "awaiting_payment"
        req.m_payment_id = f"tutor-session-{req.id}-{uuid.uuid4().hex[:8]}"


def _create_meet_session_for_request(db, req: TutoringSessionRequest, tutor: TutorAccount) -> None:
    """Best-effort - shared by _assign_tutor_to_request (only for an
    already-paid re-allocation) and mark_session_paid (the normal path,
    once the learner's payment actually clears)."""
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
    on whether this is a catalog higher-ed request (module_id set,
    matched against TutorHigherEdModule + the independent
    higher_ed_status), a custom ("Other") higher-ed request (year-level
    only - see _tutor_eligible_for_custom_module), or a high-school one
    (matched against TutorSubject + status, as before)."""
    if req.module_id is not None:
        if tutor.higher_ed_status != "approved":
            raise TutoringError("Your higher-ed tutor application isn't approved.")
        if not any(m.module_id == req.module_id and m.is_active for m in tutor.higher_ed_modules):
            raise TutoringError(f"You're not approved to tutor {req.subject}.")
    elif req.is_custom_higher_ed:
        if not _tutor_eligible_for_custom_module(tutor, req.custom_module_year_level):
            raise TutoringError(f"You're not approved to tutor {req.subject}.")
    else:
        if tutor.status != "approved":
            raise TutoringError("Your tutor account isn't approved.")
        if not any(s.subject == req.subject and s.is_active for s in tutor.subjects):
            raise TutoringError(f"You're not approved to tutor {req.subject}.")


def _tutor_eligible_for_custom_module(tutor: TutorAccount, module_year_level: int | None) -> bool:
    """A custom ("Other") module has no catalog row, so the only thing
    that can be checked automatically is the SAME "at least one year
    ahead" rule the catalog uses - it can't confirm the module is even
    in the tutor's actual field (that's exactly why accept_tutoring_
    request routes a claim here to pending_admin_approval instead of
    finalizing it immediately, same reasoning as the module docstring's
    own Psychology-tutor-claiming-Mathematics example)."""
    if tutor.higher_ed_status != "approved":
        return False
    if tutor.higher_ed_qualification_complete:
        return True
    if module_year_level is None or tutor.higher_ed_year_of_study is None:
        # No year to compare against - broadcast it rather than hide it;
        # admin approval is still the backstop either way.
        return True
    return tutor.higher_ed_year_of_study > module_year_level


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

        # A custom ("Other") module claim can't finalize here like a
        # catalog match does - year-level eligibility (just checked
        # above) can't confirm the module is actually in the tutor's own
        # field, so it parks at pending_admin_approval for a human to
        # sign off (see respond_to_custom_module_claim) before the
        # learner ever sees it as accepted.
        if req.is_custom_higher_ed:
            req.tutor_id = tutor.id
            req.status = "pending_admin_approval"
            result = {"id": req.id, "status": req.status, "m_payment_id": None, "meet_link": None}
            subject, topic, scheduled_at = req.subject, req.topic, req.scheduled_at
            tutor_name, tutor_email = tutor.name, tutor.email
        else:
            _assign_tutor_to_request(db, req, tutor)
            result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
            learner = db.query(User).get(req.learner_user_id)
            learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
            tutor_name, tutor_email = tutor.name, tutor.email
            subject, topic, price_zar, duration_minutes, scheduled_at = (
                req.subject, req.topic, req.price_zar, req.duration_minutes, req.scheduled_at
            )

    if result["status"] == "pending_admin_approval":
        _notify_admins_of_custom_claim(
            request_id=request_id, tutor_name=tutor_name, tutor_email=tutor_email,
            subject=subject, topic=topic, scheduled_at=scheduled_at,
        )
    else:
        _notify_match(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
            subject=subject, topic=topic, price_zar=price_zar,
            duration_minutes=duration_minutes, scheduled_at=scheduled_at,
            meet_link=result["meet_link"], already_paid=result["status"] == "confirmed",
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
        learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
        tutor_name = tutor.name
        subject, topic = req.subject, req.topic

    _notify_time_proposed(
        learner_id=learner_id, learner_name=learner_name, learner_email=learner_email, tutor_name=tutor_name,
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
                    tutor_id=tutor.id, tutor_name=tutor.name, tutor_email=tutor.email, learner_name=learner.name,
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
        learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
        tutor_id, tutor_name, tutor_email = tutor.id, tutor.name, tutor.email
        subject, topic, price_zar, duration_minutes, scheduled_at = (
            req.subject, req.topic, req.price_zar, req.duration_minutes, req.scheduled_at
        )

    _notify_match(
        learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
        tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=scheduled_at,
        meet_link=result["meet_link"], already_paid=result["status"] == "confirmed",
    )
    return result


def match_tutor_to_request(
    request_id: int, tutor_id: int, admin_note: str = "",
) -> dict:
    """Admin override: SUGGESTS an approved tutor for an open (or
    time_proposed) request at the price/time the learner already set -
    does NOT finalize the match immediately. The tutor still has to
    confirm (see tutor_respond_to_admin_match) before anything is locked
    in, same as the self-service accept/propose flow, so an admin can
    never commit a tutor to a session they haven't agreed to.
    admin_note is optional free-text context/instructions sent to the
    tutor alongside the suggestion (e.g. why they were picked, anything
    the learner mentioned) - an admin can no longer propose a different
    time here; if the learner's own time doesn't work for a tutor, that
    tutor can still counter-propose through the normal flow once they've
    responded. Still the exception path, not the primary one - see this
    module's docstring."""
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
        req.status = "admin_proposed"
        req.admin_proposed_at = dt.datetime.utcnow()
        req.admin_match_note = admin_note.strip() or None

        result = {"id": req.id, "status": req.status}
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic = req.subject, req.topic
        scheduled_at = req.scheduled_at
        note = req.admin_match_note

    _notify_admin_proposed_match(
        tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, scheduled_at=scheduled_at, admin_note=note,
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
    declined = False
    time_changed = False
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.tutor_id != tutor_id:
            raise TutoringError("Request not found.")
        if req.status != "admin_proposed":
            raise TutoringError(f"This request is '{req.status}', not awaiting your confirmation.")
        tutor = db.query(TutorAccount).get(tutor_id)
        tutor_name = tutor.name if tutor else "A tutor"
        subject, topic = req.subject, req.topic

        if not accept:
            declined = True
            req.tutor_id = None
            req.proposed_scheduled_at = None
            req.admin_proposed_at = None
            req.status = "requested"
            result = {"id": req.id, "status": req.status}
        else:
            if not tutor or tutor.status != "approved":
                raise TutoringError("Your tutor account isn't approved.")

            if req.proposed_scheduled_at:
                # Admin proposed a different time than the learner's own -
                # the learner still needs to approve that change.
                time_changed = True
                req.status = "time_proposed"
                req.admin_proposed_at = None
                result = {"id": req.id, "status": req.status}
                learner = db.query(User).get(req.learner_user_id)
                learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
                proposed_scheduled_at = req.proposed_scheduled_at
            else:
                # No time change - finalize directly, same as a normal accept.
                _check_schedule_conflict(
                    db, kind="tutor", person_id=tutor_id, scheduled_at=req.scheduled_at,
                    duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
                )
                req.admin_proposed_at = None
                _assign_tutor_to_request(db, req, tutor)

                result = {
                    "id": req.id, "status": req.status,
                    "m_payment_id": req.m_payment_id, "meet_link": req.meet_link,
                }
                learner = db.query(User).get(req.learner_user_id)
                learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
                tutor_email = tutor.email
                price_zar, duration_minutes, final_scheduled_at = (
                    req.price_zar, req.duration_minutes, req.scheduled_at
                )

    if declined:
        _notify_admins_of_proposal_response(tutor_name=tutor_name, subject=subject, topic=topic, accepted=False)
        return result

    if time_changed:
        _notify_time_proposed(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email, tutor_name=tutor_name,
            subject=subject, topic=topic, proposed_scheduled_at=proposed_scheduled_at,
        )
        _notify_admins_of_proposal_response(tutor_name=tutor_name, subject=subject, topic=topic, accepted=True)
        return result

    _notify_match(
        learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
        tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=final_scheduled_at,
        meet_link=result["meet_link"], already_paid=result["status"] == "confirmed",
    )
    _notify_admins_of_proposal_response(tutor_name=tutor_name, subject=subject, topic=topic, accepted=True)
    return result


def _notify_admins_of_proposal_response(
    *, tutor_name: str, subject: str, topic: str | None, accepted: bool,
) -> None:
    """Best-effort email to every admin (same pattern as
    _notify_admins_of_custom_claim) - an admin who suggested a tutor
    currently has no way to know whether that tutor actually confirmed
    or declined without reopening the request themselves."""
    try:
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admins:
            return
        topic_str = f" ({topic})" if topic else ""
        verb = "accepted" if accepted else "declined"
        body = (
            f"{tutor_name} {verb} your suggested match for {subject}{topic_str}.\n\n"
            + ("Nothing further needed." if accepted else
               "It's been reopened - suggest another tutor from the Match Requests tab.")
        )
        for admin_id, email in admins:
            send_email(email, f"Tutor {verb} your suggested match: {subject}{topic_str}", body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id,
                title=f"Tutor {verb} your suggested match", body=f"{tutor_name} {verb} the {subject}{topic_str} match.",
            )
    except Exception:
        logger.exception("Failed to notify admins of a tutor's response to a suggested match")


def respond_to_custom_module_claim(request_id: int, approve: bool) -> dict:
    """Admin approving or rejecting a tutor's self-claim on a custom
    ("Other") module request (see accept_tutoring_request's
    pending_admin_approval branch and _tutor_eligible_for_custom_module's
    own docstring) - the one check a catalog match gets for free (the
    tutor's own TutorHigherEdModule membership, which actually ties them
    to that specific module) doesn't exist for a typed-in module, so a
    claim sits here until a human visually confirms the tutor's
    qualification is actually relevant. Rejecting fully reopens the
    request (same as a declined admin_proposed match) so it goes back to
    every year-eligible tutor's queue and an admin can review a different
    claim. Approving finalizes it exactly like a direct accept, including
    a fresh schedule-conflict recheck in case the tutor booked something
    else in the meantime."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.status != "pending_admin_approval":
            raise TutoringError("This request isn't awaiting approval.")
        tutor = db.query(TutorAccount).get(req.tutor_id)
        if not tutor:
            raise TutoringError("Tutor account not found.")
        tutor_name, tutor_email = tutor.name, tutor.email
        subject, topic, scheduled_at = req.subject, req.topic, req.scheduled_at

        if not approve:
            req.tutor_id = None
            req.status = "requested"
            result = {"id": req.id, "status": req.status}
            _notify_custom_claim_rejected(
                tutor_id=tutor.id, tutor_name=tutor_name, tutor_email=tutor_email, subject=subject, topic=topic,
            )
            return result

        if tutor.status != "approved" and tutor.higher_ed_status != "approved":
            raise TutoringError("That tutor is not an approved, active tutor.")
        _check_schedule_conflict(
            db, kind="tutor", person_id=tutor.id, scheduled_at=req.scheduled_at,
            duration_minutes=req.duration_minutes or 60, exclude_request_id=req.id,
        )
        _assign_tutor_to_request(db, req, tutor)

        result = {"id": req.id, "status": req.status, "m_payment_id": req.m_payment_id, "meet_link": req.meet_link}
        learner = db.query(User).get(req.learner_user_id)
        learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
        tutor_id = tutor.id
        price_zar, duration_minutes, final_scheduled_at = req.price_zar, req.duration_minutes, req.scheduled_at

    _notify_match(
        learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
        tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
        subject=subject, topic=topic, price_zar=price_zar,
        duration_minutes=duration_minutes, scheduled_at=final_scheduled_at,
        meet_link=result["meet_link"], already_paid=result["status"] == "confirmed",
    )
    return result


def _notify_custom_claim_rejected(
    *, tutor_id: int, tutor_name: str, tutor_email: str, subject: str, topic: str | None,
) -> None:
    """Best-effort - tells the tutor their claim on a custom module
    request wasn't approved, same spirit as _notify_tutor_of_decision for
    an application rejection."""
    try:
        topic_str = f" ({topic})" if topic else ""
        send_email(
            tutor_email,
            "Your claim on a tutoring request wasn't approved",
            (
                f"Hi {tutor_name},\n\n"
                f"An admin reviewed your claim on the {subject}{topic_str} request and decided it "
                "isn't a good match for your qualification - it's been reopened for another tutor.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="Claim not approved",
            body=f"Your claim on the {subject}{topic_str} request wasn't approved - it's been reopened.",
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of a rejected custom module claim", tutor_email)


def _notify_admin_proposed_match(
    *, tutor_id: int, tutor_name: str, tutor_email: str, subject: str, topic: str | None,
    scheduled_at: dt.datetime | None, admin_note: str | None = None,
) -> None:
    """Best-effort - tells the tutor an admin suggested them for a session
    and that they need to confirm it in the app before anything is final."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        note_str = f"\nNote from the admin: {admin_note}\n" if admin_note else ""
        send_email(
            tutor_email,
            "An admin suggested you for a tutoring session",
            (
                f"Hi {tutor_name},\n\n"
                f"A Malita admin suggested you for a {subject}{topic_str} session, "
                f"proposed for:\n\n{when_str}\n{note_str}\n"
                "Open the Malita tutor app to confirm or decline - nothing is "
                "booked until you confirm.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="An admin suggested you for a session",
            body=f"You've been suggested for a {subject}{topic_str} session - confirm or decline in the app.",
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of an admin-suggested match", tutor_email)


def _notify_request_withdrawn(
    *, tutor_id: int, tutor_name: str, tutor_email: str, learner_name: str,
    subject: str, topic: str | None,
) -> None:
    """Best-effort - tells a tutor whose time proposal was pending that
    the learner withdrew the request entirely (distinct from a plain
    decline, which reopens it)."""
    try:
        topic_str = f" ({topic})" if topic else ""
        send_email(
            tutor_email,
            "A tutoring request was withdrawn",
            (
                f"Hi {tutor_name},\n\n"
                f"{learner_name} withdrew their request for {subject}{topic_str} "
                "before responding to your proposed time - there's nothing further "
                "to do on this one.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="A request was withdrawn",
            body=f"{learner_name} withdrew their {subject}{topic_str} request before you responded.",
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of a withdrawn request", tutor_email)


def _notify_proposal_declined(
    *, tutor_id: int, tutor_name: str, tutor_email: str, learner_name: str,
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
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="Proposed time declined",
            body=f"{learner_name} declined your proposed time for {subject}{topic_str} - it's open again.",
        )
    except Exception:
        logger.exception("Failed to notify tutor %s of a declined time proposal", tutor_email)


def _notify_time_proposed(
    *, learner_id: int, learner_name: str, learner_email: str, tutor_name: str,
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
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Tutor proposed a new time",
            body=f"{tutor_name} proposed a new time for {subject}{topic_str} - approve or decline in the app.",
        )
    except Exception:
        logger.exception("Failed to notify learner %s of a proposed time change", learner_email)


def _notify_admins_of_custom_claim(
    *, request_id: int, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None, scheduled_at: dt.datetime | None,
) -> None:
    """Best-effort email to every admin (same pattern as
    _notify_admins_of_recording) - a tutor claiming a custom ("Other")
    module request needs a human to confirm the module is actually in
    that tutor's field before it reaches the learner at all (see
    accept_tutoring_request/respond_to_custom_module_claim), and nobody
    reviews the admin console on a fixed schedule, so this is what
    actually prompts someone to go look."""
    try:
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admins:
            return
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        body = (
            f"{tutor_name} ({tutor_email}) claimed request #{request_id} - {subject}{topic_str}, "
            f"scheduled {when_str}.\n\n"
            "This is a custom module (not in the catalog), so it needs your approval before the "
            "learner sees it as accepted - open the admin console's Tutoring tab to review and "
            "approve or reject it.\n"
        )
        for admin_id, email in admins:
            send_email(email, f"Tutor claim needs approval: {subject}{topic_str}", body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id, title="Tutor claim needs approval",
                body=f"{tutor_name} claimed request #{request_id} - {subject}{topic_str}.",
            )
    except Exception:
        logger.exception("Failed to notify admins of request %s's custom module claim", request_id)


def _notify_match(
    *, learner_id: int, learner_name: str, learner_email: str,
    tutor_id: int, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None, price_zar: float, duration_minutes: int,
    scheduled_at: dt.datetime | None, meet_link: str | None = None, already_paid: bool = False,
) -> None:
    """Best-effort, same pattern as _notify_tutor_of_decision - a failed
    or unconfigured email send must never break the match/accept action
    itself. already_paid is set when this match is a re-allocation after
    a previous tutor cancelled an already-paid session (see
    _assign_tutor_to_request) - the learner doesn't need to be told to
    pay again."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        meet_line = (
            f"\nGoogle Meet: {meet_link}\n" if meet_link else
            "\nGoogle Meet link: created once payment is confirmed.\n"
        )
        learner_action_line = (
            "This session is already paid for - no action needed."
            if already_paid else
            "Open the Malita app and pay to confirm the session."
        )
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
                f"{learner_action_line}\n\n"
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
                f"{RECORDING_REMINDER_NOTE}\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="You've been matched with a tutor!",
            body=(
                f"{tutor_name} - {subject}{topic_str} - already paid, no action needed."
                if already_paid else
                f"{tutor_name} - {subject}{topic_str} - pay in the app to confirm the session."
            ),
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="You've been matched to a new session",
            body=f"{learner_name} - {subject}{topic_str}, scheduled {when_str}.",
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
    because payment cleared.

    This is also where the Google Meet session gets created (see
    _assign_tutor_to_request's docstring) - not at match time - so both
    sides are told up front that the link only exists once payment
    clears, instead of a link existing for a session that might never
    get paid for and lapses."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).filter(
            TutoringSessionRequest.m_payment_id == m_payment_id
        ).first()
        if not req:
            raise TutoringError("Unknown tutoring session payment reference.")
        if req.status == "confirmed":
            return {"id": req.id, "status": req.status, "already_processed": True}
        if req.status == "lapsed":
            # Rare race: the learner's payment landed just after
            # _expire_lapsed_payments marked this lapsed. The money
            # already moved, so honor it rather than stranding a paying
            # learner - better a late confirmation than a silent loss.
            logger.warning("Session %s paid after lapsing - honoring the late payment.", req.id)

        req.status = "confirmed"
        req.paid_at = dt.datetime.utcnow()

        tutor = db.query(TutorAccount).get(req.tutor_id) if req.tutor_id else None
        if tutor and not req.meet_link:
            _create_meet_session_for_request(db, req, tutor)

        result = {"id": req.id, "status": req.status}
        should_notify = tutor is not None and req.meet_link is not None
        if should_notify:
            learner = db.query(User).get(req.learner_user_id)
            learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
            tutor_id, tutor_name, tutor_email = tutor.id, tutor.name, tutor.email
            subject, topic, scheduled_at, meet_link = req.subject, req.topic, req.scheduled_at, req.meet_link

    if should_notify:
        _notify_meet_link_ready(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
            subject=subject, topic=topic, scheduled_at=scheduled_at, meet_link=meet_link,
        )
    return result


def _notify_meet_link_ready(
    *, learner_id: int, learner_name: str, learner_email: str,
    tutor_id: int, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None, scheduled_at: dt.datetime | None, meet_link: str,
) -> None:
    """Best-effort - tells both sides their Google Meet link is ready
    now that payment has cleared (see mark_session_paid)."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        body = (
            f"{subject}{topic_str} session scheduled for {when_str}.\n\n"
            f"Google Meet: {meet_link}\n\n"
            "— The Malita team"
        )
        send_email(learner_email, "Payment confirmed - your Google Meet link is ready", f"Hi {learner_name},\n\n{body}")
        send_email(tutor_email, "Payment confirmed - your Google Meet link is ready", f"Hi {tutor_name},\n\n{body}")
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Your Google Meet link is ready",
            body=f"{subject}{topic_str} - payment confirmed, join via the link in the app.",
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="Your Google Meet link is ready",
            body=f"{subject}{topic_str} - payment confirmed, join via the link in the app.",
        )
    except Exception:
        logger.exception("Failed to notify learner/tutor that their Meet link is ready")


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


def submit_session_recording(request_id: int, tutor_id: int, recording_link: str) -> dict:
    """The tutor submitting the link to their own manually-recorded Meet
    session afterward (see RECORDING_REMINDER_NOTE - there's no API that
    can force a recording on a non-Workspace Meet call, so this is a
    tutor-submitted link, not an automated one). Emails every admin the
    link plus the session's full details so it's kept on file. Allowed
    any time after the session is confirmed/paid - not gated on the
    scheduled time having passed, since that's the tutor's own call."""
    recording_link = recording_link.strip()
    if not recording_link:
        raise TutoringError("Please paste in the recording link.")
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.tutor_id != tutor_id:
            raise TutoringError("Session not found.")
        if req.status not in ("confirmed", "completed"):
            raise TutoringError(f"This session is '{req.status}', not yet paid/confirmed.")
        req.recording_link = recording_link
        req.recording_shared_at = dt.datetime.utcnow()
        learner = db.query(User).get(req.learner_user_id)
        tutor = db.query(TutorAccount).get(req.tutor_id)
        details = {
            "learner_name": learner.name if learner else "—",
            "learner_email": learner.email if learner else "—",
            "tutor_name": tutor.name if tutor else "—",
            "tutor_email": tutor.email if tutor else "—",
            "subject": req.subject, "topic": req.topic,
            "scheduled_at": req.scheduled_at, "duration_minutes": req.duration_minutes,
            "price_zar": req.price_zar, "recording_link": recording_link,
        }
        result = {"id": req.id, "status": req.status}
    _notify_admins_of_recording(request_id=request_id, **details)
    return result


def _notify_admins_of_recording(
    *, request_id: int, learner_name: str, learner_email: str,
    tutor_name: str, tutor_email: str, subject: str, topic: str | None,
    scheduled_at: dt.datetime | None, duration_minutes: int | None,
    price_zar: float | None, recording_link: str,
) -> None:
    """Best-effort email to every admin - same pattern as
    backend/collab.py's _notify_admins_of_report - with the full session
    details alongside the recording link, so nothing has to be looked up
    separately to file it away."""
    try:
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admins:
            return
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        price_str = f"R{price_zar:.2f}" if price_zar is not None else "—"
        duration_str = f"{duration_minutes} min" if duration_minutes is not None else "—"
        body = (
            f"A tutor shared the recording for session #{request_id}.\n\n"
            f"Subject: {subject}{topic_str}\n"
            f"Learner: {learner_name} ({learner_email})\n"
            f"Tutor: {tutor_name} ({tutor_email})\n"
            f"Scheduled: {when_str}\n"
            f"Duration: {duration_str}\n"
            f"Price: {price_str}\n\n"
            f"Recording: {recording_link}\n"
        )
        for admin_id, email in admins:
            send_email(email, f"Session recording: {subject}{topic_str}", body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id, title="Session recording shared",
                body=f"{tutor_name} shared the recording for session #{request_id} - {subject}{topic_str}.",
            )
    except Exception:
        logger.exception("Failed to notify admins of session %s's recording", request_id)


def cancel_session(request_id: int, reason: str = "") -> None:
    """Admin override: cancels any not-yet-paid request regardless of how
    close the scheduled time is - the learner/tutor-initiated path (see
    cancel_accepted_session) is what enforces the 24-hour cutoff; this
    one exists precisely for the cases that fall outside it."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status in ("confirmed", "completed"):
            raise TutoringError("A paid or completed session can't be cancelled this way - contact support.")
        req.status = "cancelled"
        req.cancelled_at = dt.datetime.utcnow()
        req.cancelled_by = "admin"
        req.admin_notes = reason.strip() or req.admin_notes


def cancel_accepted_session(request_id: int, *, by: str, person_id: int, reason: str = "") -> dict:
    """Either party cancelling an ALREADY-ACCEPTED session (awaiting_
    payment or confirmed/paid) - not available within
    CANCELLATION_CUTOFF_HOURS of the scheduled time, so a last-minute
    cancellation always needs admin involvement (see cancel_session
    above) rather than silently leaving the other side stranded. Use
    withdraw_tutoring_request instead for a request a tutor hasn't fully
    accepted yet (no time restriction, since nothing is committed yet).
    Notifies BOTH sides. A tutor cancelling an already-PAID session
    doesn't dead-end it like a learner's own cancellation does - see
    reallocate_after_tutor_cancellation/request_refund_for_cancelled_
    session, which the learner chooses between afterwards.

    `by` is "learner" or "tutor" - `person_id` must match whichever side
    is cancelling (the learner's user id or the tutor's tutor_id)."""
    if by not in ("learner", "tutor"):
        raise TutoringError("Invalid cancellation request.")
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Session not found.")
        if by == "learner" and req.learner_user_id != person_id:
            raise TutoringError("Session not found.")
        if by == "tutor" and req.tutor_id != person_id:
            raise TutoringError("Session not found.")
        if req.status not in ("awaiting_payment", "confirmed"):
            raise TutoringError(f"This session is '{req.status}' and can't be cancelled this way.")
        if not req.scheduled_at:
            raise TutoringError("This session has no scheduled time.")
        if dt.datetime.utcnow() > req.scheduled_at - dt.timedelta(hours=CANCELLATION_CUTOFF_HOURS):
            raise TutoringError(
                f"This session is less than {CANCELLATION_CUTOFF_HOURS} hours away - "
                "contact support to cancel it."
            )
        was_paid = req.status == "confirmed"
        # A tutor backing out before the learner has even paid leaves no
        # money to refund - reopen the request (same as if it had never
        # been matched) so any approved tutor can pick it up again,
        # instead of dead-ending it and forcing the learner to submit a
        # brand-new request from scratch. A tutor backing out of an
        # already-PAID session is trickier (real money is involved), so
        # it parks at "tutor_cancelled" for the LEARNER to choose between
        # re-allocation or a refund, rather than deciding for them. Only
        # the learner's own cancellation still dead-ends straight into
        # "cancelled" here.
        reopen_for_other_tutors = by == "tutor" and not was_paid
        parks_for_learner_choice = by == "tutor" and was_paid

        learner = db.query(User).get(req.learner_user_id)
        tutor = db.query(TutorAccount).get(req.tutor_id)
        learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
        tutor_id, tutor_name, tutor_email = tutor.id, tutor.name, tutor.email
        subject, topic, scheduled_at = req.subject, req.topic, req.scheduled_at

        if reopen_for_other_tutors:
            req.status = "requested"
            req.tutor_id = None
            req.platform_cut_percent = None
            req.matched_at = None
            req.meet_link = None
            # Broadcast to every eligible tutor again, not just directed
            # back at the one who just backed out.
            req.preferred_tutor_id = None
        elif parks_for_learner_choice:
            req.status = "tutor_cancelled"
            req.tutor_id = None
            req.matched_at = None
            req.meet_link = None
            req.preferred_tutor_id = None
            # Recorded now (not only if the learner later picks refund) so
            # the reason survives regardless of which way they decide -
            # cleared again in reallocate_after_tutor_cancellation if they
            # pick re-allocation instead, since it's then no longer
            # heading toward "cancelled" at all.
            req.cancelled_by = by
            req.cancellation_reason = reason.strip() or None
        else:
            req.status = "cancelled"
            req.cancelled_at = dt.datetime.utcnow()
            req.cancelled_by = by
            req.cancellation_reason = reason.strip() or None
        result = {"id": req.id, "status": req.status}

    if reopen_for_other_tutors:
        _notify_request_reopened_after_tutor_cancel(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_name=tutor_name, subject=subject, topic=topic, scheduled_at=scheduled_at, reason=reason,
        )
    elif parks_for_learner_choice:
        _notify_paid_session_tutor_cancelled(
            request_id=request_id,
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_name=tutor_name, subject=subject, topic=topic, scheduled_at=scheduled_at, reason=reason,
        )
    else:
        _notify_session_cancelled(
            learner_id=learner_id, learner_name=learner_name, learner_email=learner_email,
            tutor_id=tutor_id, tutor_name=tutor_name, tutor_email=tutor_email,
            subject=subject, topic=topic, scheduled_at=scheduled_at,
            cancelled_by=by, reason=reason, was_paid=was_paid,
        )
    return result


def _notify_session_cancelled(
    *, learner_id: int, learner_name: str, learner_email: str,
    tutor_id: int, tutor_name: str, tutor_email: str,
    subject: str, topic: str | None, scheduled_at: dt.datetime | None,
    cancelled_by: str, reason: str, was_paid: bool,
) -> None:
    """Best-effort - tells BOTH sides a session was cancelled, who
    cancelled it, and (for an already-paid session) that a refund will
    be arranged manually."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        who = "the learner" if cancelled_by == "learner" else "the tutor"
        reason_str = f"\n\nReason given: {reason.strip()}" if reason.strip() else ""
        refund_note = (
            "\n\nSince this session was already paid for, Malita will arrange your "
            "refund manually - we'll be in touch."
            if was_paid else ""
        )
        send_email(
            learner_email,
            "Your tutoring session was cancelled",
            (
                f"Hi {learner_name},\n\n"
                f"Your {subject}{topic_str} session scheduled for {when_str} was "
                f"cancelled by {who}.{reason_str}{refund_note}\n\n"
                "— The Malita team"
            ),
        )
        send_email(
            tutor_email,
            "A tutoring session was cancelled",
            (
                f"Hi {tutor_name},\n\n"
                f"Your {subject}{topic_str} session with {learner_name} scheduled for "
                f"{when_str} was cancelled by {who}.{reason_str}\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Your tutoring session was cancelled",
            body=f"{subject}{topic_str} session scheduled for {when_str} was cancelled by {who}.",
        )
        create_notification(
            recipient_kind="tutor", recipient_id=tutor_id, title="A tutoring session was cancelled",
            body=f"{subject}{topic_str} session with {learner_name} scheduled for {when_str} was cancelled by {who}.",
        )
    except Exception:
        logger.exception("Failed to notify learner/tutor of a cancelled session")


def _notify_request_reopened_after_tutor_cancel(
    *, learner_id: int, learner_name: str, learner_email: str, tutor_name: str,
    subject: str, topic: str | None, scheduled_at: dt.datetime | None, reason: str,
) -> None:
    """Best-effort - tells the LEARNER their tutor backed out and the
    request is open again for another tutor to accept, rather than the
    "your session was cancelled" wording used for a real dead-end
    cancellation. The tutor who backed out isn't notified here - they
    already know, since they're the one who did it."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        reason_str = f"\n\nReason given: {reason.strip()}" if reason.strip() else ""
        send_email(
            learner_email,
            "Your tutor cancelled - your request is open again",
            (
                f"Hi {learner_name},\n\n"
                f"{tutor_name} cancelled your {subject}{topic_str} session scheduled for "
                f"{when_str}.{reason_str}\n\n"
                "No need to submit a new request - it's open again for any other qualifying "
                "tutor to accept.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Your tutor cancelled - request reopened",
            body=(
                f"{tutor_name} cancelled your {subject}{topic_str} session scheduled for {when_str}. "
                "It's open again for another tutor to accept."
            ),
        )
    except Exception:
        logger.exception("Failed to notify learner that their request reopened after a tutor cancellation")


def _notify_paid_session_tutor_cancelled(
    *, request_id: int, learner_id: int, learner_name: str, learner_email: str, tutor_name: str,
    subject: str, topic: str | None, scheduled_at: dt.datetime | None, reason: str,
) -> None:
    """Best-effort - tells the LEARNER their tutor cancelled an
    already-paid session and they need to choose between re-allocation
    and a refund (see reallocate_after_tutor_cancellation/
    request_refund_for_cancelled_session), and tells every admin the
    same, since real money is on the line and nobody reviews the admin
    console on a fixed schedule."""
    try:
        topic_str = f" ({topic})" if topic else ""
        when_str = _format_sast(scheduled_at)
        reason_str = f"\n\nReason given: {reason.strip()}" if reason.strip() else ""
        send_email(
            learner_email,
            "Your tutor cancelled - choose what happens next",
            (
                f"Hi {learner_name},\n\n"
                f"{tutor_name} cancelled your {subject}{topic_str} session scheduled for "
                f"{when_str}, which you've already paid for.{reason_str}\n\n"
                "Open the Malita app to choose: we can find you another tutor for the same "
                "price and time, or arrange a refund - whichever you'd prefer.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Your tutor cancelled - choose what happens next",
            body=(
                f"{tutor_name} cancelled your {subject}{topic_str} session scheduled for {when_str}. "
                "Choose: find another tutor, or request a refund."
            ),
        )
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        admin_body = (
            f"{tutor_name} cancelled an already-paid session (request #{request_id} - "
            f"{subject}{topic_str}, scheduled {when_str}) for learner {learner_name}.{reason_str}\n\n"
            "The learner has been asked to choose between re-allocation and a refund - open the "
            "admin console's Tutoring tab to track it, suggest a refund, or step in directly.\n"
        )
        for admin_id, email in admins:
            send_email(email, f"Paid session cancelled by tutor: {subject}{topic_str}", admin_body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id, title="Paid session cancelled by tutor",
                body=f"Request #{request_id} - {subject}{topic_str} for {learner_name}, awaiting their choice.",
            )
    except Exception:
        logger.exception("Failed to notify learner/admins of request %s's paid-session tutor cancellation", request_id)


def reallocate_after_tutor_cancellation(request_id: int, learner_user_id: int) -> dict:
    """The learner choosing re-allocation after a tutor cancelled their
    already-paid session (status "tutor_cancelled" - see
    cancel_accepted_session) - reopens the request for any eligible
    tutor to accept, same as a brand-new broadcast request, except
    paid_at stays set so _assign_tutor_to_request skips straight to
    "confirmed" instead of "awaiting_payment" once a new tutor
    accepts - the learner doesn't pay twice."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.learner_user_id != learner_user_id:
            raise TutoringError("Request not found.")
        if req.status != "tutor_cancelled":
            raise TutoringError(f"This request is '{req.status}', not awaiting a re-allocation/refund choice.")
        req.status = "requested"
        req.cancelled_by = None
        req.cancellation_reason = None
        return {"id": req.id, "status": req.status}


def request_refund_for_cancelled_session(request_id: int, learner_user_id: int) -> dict:
    """The learner choosing a refund instead of re-allocation after a
    tutor cancelled their already-paid session (status
    "tutor_cancelled" - see cancel_accepted_session) - ends the request
    as "cancelled" and flags refund_requested_at for an admin to action
    (see mark_refund_processed; no automated PayFast refund in v1)."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req or req.learner_user_id != learner_user_id:
            raise TutoringError("Request not found.")
        if req.status != "tutor_cancelled":
            raise TutoringError(f"This request is '{req.status}', not awaiting a re-allocation/refund choice.")
        req.status = "cancelled"
        req.cancelled_at = dt.datetime.utcnow()
        req.refund_requested_at = dt.datetime.utcnow()
        result = {"id": req.id, "status": req.status}
        price_zar, subject, topic = req.price_zar, req.subject, req.topic

    _notify_admins_of_refund_request(request_id=request_id, price_zar=price_zar, subject=subject, topic=topic)
    return result


def _notify_admins_of_refund_request(
    *, request_id: int, price_zar: float | None, subject: str, topic: str | None,
) -> None:
    """Best-effort email to every admin - same "nobody checks the
    console on a schedule" reasoning as _notify_admins_of_custom_claim."""
    try:
        with get_session() as db:
            admins = [(u.id, u.email) for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        if not admins:
            return
        topic_str = f" ({topic})" if topic else ""
        price_str = f"R{price_zar:.2f}" if price_zar is not None else "an unknown amount"
        body = (
            f"The learner on request #{request_id} - {subject}{topic_str} - chose a refund "
            f"({price_str}) after their tutor cancelled the paid session.\n\n"
            "Open the admin console's Tutoring tab to arrange the refund and mark it processed.\n"
        )
        for admin_id, email in admins:
            send_email(email, f"Refund requested: {subject}{topic_str}", body)
            create_notification(
                recipient_kind="user", recipient_id=admin_id, title="Refund requested",
                body=f"Request #{request_id} - {subject}{topic_str}, {price_str}.",
            )
    except Exception:
        logger.exception("Failed to notify admins of request %s's refund request", request_id)


def admin_suggest_refund(request_id: int) -> dict:
    """Admin nudging the learner toward a refund instead of waiting on
    re-allocation (status "tutor_cancelled") - just a notification, not
    a decision made for them; the learner still has to click their own
    Request Refund button (see request_refund_for_cancelled_session) to
    actually act on it."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.status != "tutor_cancelled":
            raise TutoringError(f"This request is '{req.status}', not awaiting a re-allocation/refund choice.")
        learner = db.query(User).get(req.learner_user_id)
        learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
        subject, topic, price_zar = req.subject, req.topic, req.price_zar

    try:
        topic_str = f" ({topic})" if topic else ""
        price_str = f"R{price_zar:.2f}" if price_zar is not None else ""
        send_email(
            learner_email,
            "Malita suggests a refund for your cancelled session",
            (
                f"Hi {learner_name},\n\n"
                f"We noticed your {subject}{topic_str} session hasn't been re-allocated yet. "
                f"If you'd rather not wait, you can request a refund ({price_str}) in the app "
                "instead of continuing to look for another tutor.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Malita suggests a refund",
            body=f"We suggest a refund for your {subject}{topic_str} session - your choice either way.",
        )
    except Exception:
        logger.exception("Failed to notify learner of request %s's suggested refund", request_id)
    return {"id": request_id, "status": "tutor_cancelled"}


def mark_refund_processed(request_id: int) -> dict:
    """Admin confirming they've actually arranged the refund outside the
    app (bank transfer/PayFast console) - clears it from the admin
    console's pending-refunds list. No automated payment-gateway refund
    in v1, same deliberately-manual spirit as payouts."""
    with get_session() as db:
        req = db.query(TutoringSessionRequest).get(request_id)
        if not req:
            raise TutoringError("Request not found.")
        if req.refund_requested_at is None:
            raise TutoringError("No refund was requested for this request.")
        if req.refund_processed_at is not None:
            raise TutoringError("This refund has already been marked processed.")
        req.refund_processed_at = dt.datetime.utcnow()
        learner = db.query(User).get(req.learner_user_id)
        learner_id, learner_name, learner_email = learner.id, learner.name, learner.email
        subject, topic, price_zar = req.subject, req.topic, req.price_zar
        result = {"id": req.id, "status": req.status}

    try:
        topic_str = f" ({topic})" if topic else ""
        price_str = f"R{price_zar:.2f}" if price_zar is not None else ""
        send_email(
            learner_email,
            "Your refund has been processed",
            (
                f"Hi {learner_name},\n\n"
                f"Your refund ({price_str}) for the {subject}{topic_str} session has been processed.\n\n"
                "— The Malita team"
            ),
        )
        create_notification(
            recipient_kind="user", recipient_id=learner_id, title="Your refund has been processed",
            body=f"Your refund ({price_str}) for {subject}{topic_str} has been processed.",
        )
    except Exception:
        logger.exception("Failed to notify learner that request %s's refund was processed", request_id)
    return result


def list_requests_needing_attention() -> list[dict]:
    """Admin console feed: paid sessions a tutor just cancelled (status
    "tutor_cancelled", awaiting the learner's re-allocation/refund
    choice) plus refunds the learner has requested but no admin has yet
    marked processed - the two situations real money is sitting in
    limbo on, which is exactly what nobody reviewing the console on a
    fixed schedule would otherwise notice."""
    with get_session() as db:
        reqs = (
            db.query(TutoringSessionRequest)
            .filter(
                sa.or_(
                    TutoringSessionRequest.status == "tutor_cancelled",
                    sa.and_(
                        TutoringSessionRequest.refund_requested_at.isnot(None),
                        TutoringSessionRequest.refund_processed_at.is_(None),
                    ),
                )
            )
            .order_by(TutoringSessionRequest.created_at.asc())
            .all()
        )
        return [_serialize_request(r) for r in reqs]


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
                "tutor_bank_account_holder": tutor.bank_account_holder if tutor else None,
                "tutor_bank_name": tutor.bank_name if tutor else None,
                "tutor_bank_branch_code": tutor.bank_branch_code if tutor else None,
                "tutor_bank_account_number": tutor.bank_account_number if tutor else None,
                "tutor_bank_account_type": tutor.bank_account_type if tutor else None,
                "tutor_bank_note": tutor.bank_account_note if tutor else None,
                "amount_zar": p.amount_zar, "created_at": _iso_utc(p.created_at),
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


def _next_pay_day(from_date: dt.date | None = None) -> dt.date:
    """Malita's payout cycle, mirrored from the mobile app's own copy
    (TutorHomeScreen.tsx's nextPayDay): a session completed the 16th
    through the end of a month is paid the 15th of the FOLLOWING month;
    one completed the 1st through the 15th is paid at the end of THAT
    SAME month. A plain civil-calendar rule, not tied to any instant."""
    d = from_date or dt.date.today()
    if d.day <= 15:
        last_day = calendar.monthrange(d.year, d.month)[1]
        return dt.date(d.year, d.month, last_day)
    if d.month == 12:
        return dt.date(d.year + 1, 1, 15)
    return dt.date(d.year, d.month + 1, 15)


def summarize_pending_payouts() -> dict:
    """What admin owes right now, overall and split by tutor - both the
    net amount (what a tutor actually receives, after Malita's cut) and
    the gross session price behind it, plus the next payday those
    amounts are due. Session gross comes from the underlying
    TutoringSessionRequest rather than being backed out of the snapshotted
    cut percent, since that's the exact figure the learner paid."""
    with get_session() as db:
        payouts = db.query(TutoringPayout).filter(TutoringPayout.status == "pending").all()
        by_tutor: dict[int, dict] = {}
        overall_gross = 0.0
        overall_net = 0.0
        for p in payouts:
            req = db.query(TutoringSessionRequest).get(p.session_id)
            gross = req.price_zar if req and req.price_zar is not None else p.amount_zar
            overall_gross += gross
            overall_net += p.amount_zar
            row = by_tutor.setdefault(p.tutor_id, None)
            if row is None:
                tutor = db.query(TutorAccount).get(p.tutor_id)
                row = {
                    "tutor_id": p.tutor_id, "tutor_name": tutor.name if tutor else None,
                    "gross_zar": 0.0, "net_zar": 0.0, "count": 0,
                }
                by_tutor[p.tutor_id] = row
            row["gross_zar"] += gross
            row["net_zar"] += p.amount_zar
            row["count"] += 1
        by_tutor_list = sorted(
            ({**r, "gross_zar": round(r["gross_zar"], 2), "net_zar": round(r["net_zar"], 2)} for r in by_tutor.values()),
            key=lambda r: r["net_zar"], reverse=True,
        )
        return {
            "overall": {
                "gross_zar": round(overall_gross, 2), "net_zar": round(overall_net, 2), "count": len(payouts),
            },
            "by_tutor": by_tutor_list,
            "next_pay_day": _next_pay_day().isoformat(),
        }


def _notify_payout_settled(
    tutor_id: int, email: str, name: str, *, net_zar: float, count: int, payment_reference: str,
) -> None:
    """Best-effort - mirrors _notify_tutor_of_decision's try/except
    pattern, so a failed email/notification send never breaks the
    admin's bulk-settle action itself."""
    try:
        plural = "s" if count != 1 else ""
        subject = "Your Malita payout has been paid"
        body = (
            f"Hi {name},\n\n"
            f"Your payout of R{net_zar:.2f} for {count} session{plural} has been paid out."
            + (f"\nReference: {payment_reference}" if payment_reference else "")
            + "\n\n— The Malita team"
        )
        notif_title = "Payout paid"
        notif_body = f"R{net_zar:.2f} for {count} session{plural} has been paid."
        send_email(email, subject, body)
        create_notification(recipient_kind="tutor", recipient_id=tutor_id, title=notif_title, body=notif_body)
    except Exception:
        logger.exception("Failed to notify tutor %s of settled payout", tutor_id)


def settle_all_pending_payouts(admin_user_id: int, payment_reference: str = "") -> dict:
    """The 'this payday is settled' bulk action - marks EVERY currently
    pending payout as paid in one go (instead of admin clicking 'Mark as
    Paid' once per session), so admin's pending total and each tutor's
    own pending total both reset to zero at once; the now-paid rows show
    up as 'Paid' in the tutor's own payout history automatically, since
    that view reads the same TutoringPayout rows by status."""
    ref = payment_reference.strip() or None
    now = dt.datetime.utcnow()
    per_tutor_net: dict[int, float] = {}
    per_tutor_count: dict[int, int] = {}
    tutor_contacts: dict[int, tuple[str, str]] = {}
    with get_session() as db:
        payouts = db.query(TutoringPayout).filter(TutoringPayout.status == "pending").all()
        for p in payouts:
            p.status = "paid"
            p.paid_at = now
            p.paid_by_admin_user_id = admin_user_id
            p.payment_reference = ref
            per_tutor_net[p.tutor_id] = per_tutor_net.get(p.tutor_id, 0.0) + p.amount_zar
            per_tutor_count[p.tutor_id] = per_tutor_count.get(p.tutor_id, 0) + 1
        count = len(payouts)
        for tutor_id in per_tutor_net:
            tutor = db.query(TutorAccount).get(tutor_id)
            if tutor:
                tutor_contacts[tutor_id] = (tutor.email, tutor.name)

    for tutor_id, (email, name) in tutor_contacts.items():
        _notify_payout_settled(
            tutor_id, email, name,
            net_zar=per_tutor_net[tutor_id], count=per_tutor_count[tutor_id],
            payment_reference=ref or "",
        )

    return {"settled_count": count, "settled_net_zar": round(sum(per_tutor_net.values()), 2)}

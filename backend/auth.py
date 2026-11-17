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

from .db import (
    get_session, User, Subscription, PasswordReset, ApiToken, LoginEvent,
    Institution, Qualification, ACCOUNT_TYPES, YEAR_LEVEL_LABELS,
    ACCOUNT_STANDING_LABELS,
)
from .payfast import cancel_payfast_subscription
from .tiers import TIER_ORDER

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESET_TOKEN_VALID_MINUTES = 60
# A bearer token (ApiToken/TutorApiToken) is otherwise permanent - this is
# the one thing that eventually logs someone out: 30 days with the app
# never opened (last_used_at only moves on an actual authenticated
# request, not a background timer - see get_user_by_token/
# get_tutor_by_token below and in tutoring.py). 30 days rather than a
# short idle timer since this isn't a banking app and most of what it
# guards (study tools, tutoring bookings) doesn't need session hygiene
# tighter than "a genuinely abandoned/lost device eventually stops
# working".
INACTIVE_TOKEN_LOGOUT_DAYS = 30


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


def parse_sa_id_number(id_number: str) -> dt.date:
    """Validate a 13-digit South African ID number (date-of-birth prefix +
    Luhn checksum digit) and return the date of birth encoded in its first
    6 digits (YYMMDD) - so a learner only has to type the ID number once
    instead of typing their birth date separately too.

    Century disambiguation: YY alone is ambiguous between 19XX and 20XX.
    The standard heuristic is used - a YY greater than the current two-digit
    year is assumed 19XX (a future birth year is never valid), otherwise 20XX."""
    id_number = (id_number or "").strip()
    if not re.fullmatch(r"\d{13}", id_number):
        raise AuthError("ID number must be exactly 13 digits.")

    digits = [int(c) for c in id_number]
    total = 0
    for i, d in enumerate(digits[:-1]):
        if i % 2 == 0:
            total += d
        else:
            doubled = d * 2
            total += doubled - 9 if doubled > 9 else doubled
    check_digit = (10 - total % 10) % 10
    if check_digit != digits[-1]:
        raise AuthError("That doesn't look like a valid ID number - please check the digits.")

    yy, mm, dd = int(id_number[0:2]), int(id_number[2:4]), int(id_number[4:6])
    current_yy = dt.date.today().year % 100
    century = 1900 if yy > current_yy else 2000
    try:
        return dt.date(century + yy, mm, dd)
    except ValueError:
        raise AuthError("ID number contains an invalid birth date.")


def register_user(
    name: str, email: str, password: str, school: str = "",
    province: str = "", city_town: str = "", id_number: str = "",
    account_type: str = "high_school",
    higher_ed_institution_id: int | None = None,
    higher_ed_qualification_id: int | None = None,
    # "Other" escape hatch instead of higher_ed_qualification_id, for when
    # the learner's real qualification isn't in the catalog.
    higher_ed_qualification_custom_name: str = "",
    higher_ed_year_of_study: int | None = None,
    student_number: str = "",
) -> dict:
    """account_type decides what the account can reach afterward (see
    app.py's feature gating) - "high_school" (default, the original
    product) gets everything built so far; "higher_ed" (university/
    college) gets ONLY the tutoring marketplace, so it needs the higher_ed_*
    fields instead of (or in addition to) school."""
    name = (name or "").strip()
    email = (email or "").strip().lower()
    province = (province or "").strip()
    city_town = (city_town or "").strip()
    id_number = (id_number or "").strip()
    account_type = (account_type or "high_school").strip()
    student_number = (student_number or "").strip()
    higher_ed_qualification_custom_name = (higher_ed_qualification_custom_name or "").strip()

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
    if not id_number:
        raise AuthError("Please enter your ID number.")
    if account_type not in ACCOUNT_TYPES:
        raise AuthError("Please choose whether you're a high school learner or a university/college student.")
    date_of_birth = parse_sa_id_number(id_number)

    if account_type == "higher_ed":
        if not higher_ed_institution_id or not (higher_ed_qualification_id or higher_ed_qualification_custom_name):
            raise AuthError("Please select your institution and qualification.")
        if not higher_ed_year_of_study or not (1 <= higher_ed_year_of_study <= max(YEAR_LEVEL_LABELS)):
            raise AuthError("Please select your year of study.")
        if not student_number:
            raise AuthError("Please enter your student number.")

    with get_session() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise AuthError("An account with this email already exists. Try logging in instead.")
        existing_id = db.query(User).filter(User.id_number == id_number).first()
        if existing_id:
            raise AuthError("An account with this ID number already exists. Try logging in instead.")

        if account_type == "higher_ed" and higher_ed_qualification_id:
            qual = db.query(Qualification).get(higher_ed_qualification_id)
            if not qual or qual.institution_id != higher_ed_institution_id:
                raise AuthError("That qualification doesn't belong to the selected institution.")

        user = User(
            name=name,
            email=email,
            password_hash=_hash_password(password),
            school=school.strip() if school else None,
            province=province,
            city_town=city_town,
            id_number=id_number,
            date_of_birth=date_of_birth,
            account_type=account_type,
            higher_ed_institution_id=higher_ed_institution_id if account_type == "higher_ed" else None,
            higher_ed_qualification_id=(
                higher_ed_qualification_id if account_type == "higher_ed" and not higher_ed_qualification_custom_name else None
            ),
            higher_ed_qualification_custom_name=(
                higher_ed_qualification_custom_name if account_type == "higher_ed" else None
            ) or None,
            higher_ed_year_of_study=higher_ed_year_of_study if account_type == "higher_ed" else None,
            student_number=student_number if account_type == "higher_ed" else None,
        )
        db.add(user)
        db.flush()  # get user.id before commit

        # Every new signup starts on the Free tier automatically - harmless
        # for a higher_ed account even though it never surfaces tier UI
        # (see app.py), since every other function that reads
        # user.subscription.tier still has a row to read.
        sub = Subscription(user_id=user.id, tier="free", status="active")
        db.add(sub)
        db.flush()

        return {"id": user.id, "name": user.name, "email": user.email, "account_type": user.account_type}


def update_study_details(
    user_id: int, *,
    institution_id: int | None,
    qualification_id: int | None,
    qualification_custom_name: str = "",
    year_of_study: int | None,
    student_number: str = "",
) -> None:
    """Lets a higher-ed learner fill in/correct their own institution,
    qualification, year of study and student number after registration
    - these are REQUIRED at signup (see register_user above), but an
    account created some other way (e.g. seeded directly, or switched to
    higher_ed by an admin) can end up with them blank, with no way for
    the learner to fix that themselves until now. Same validation as
    register_user's higher-ed block, just applied to an existing row
    instead of a new one."""
    qualification_custom_name = (qualification_custom_name or "").strip()
    student_number = (student_number or "").strip()

    if not institution_id or not (qualification_id or qualification_custom_name):
        raise AuthError("Please select your institution and qualification.")
    if not year_of_study or not (1 <= year_of_study <= max(YEAR_LEVEL_LABELS)):
        raise AuthError("Please select your year of study.")
    if not student_number:
        raise AuthError("Please enter your student number.")

    with get_session() as db:
        user = db.query(User).get(user_id)
        if not user:
            raise AuthError("Account not found.")
        if user.account_type != "higher_ed":
            raise AuthError("Only a university/college account has study details.")

        if qualification_id and not qualification_custom_name:
            qual = db.query(Qualification).get(qualification_id)
            if not qual or qual.institution_id != institution_id:
                raise AuthError("That qualification doesn't belong to the selected institution.")

        user.higher_ed_institution_id = institution_id
        user.higher_ed_qualification_id = qualification_id if not qualification_custom_name else None
        user.higher_ed_qualification_custom_name = qualification_custom_name or None
        user.higher_ed_year_of_study = year_of_study
        user.student_number = student_number


def update_personal_info(
    user_id: int, *,
    province: str,
    city_town: str,
    school: str = "",
    grade: int | None = None,
) -> None:
    """Lets a learner edit their own personal info from the Account
    screen - province and city/town for everyone, school and grade for
    a high-school account only (silently ignored for a higher_ed
    account, which tracks the equivalent via update_study_details
    instead). Deliberately NOT editable here: name/email (identity,
    not a casual edit) and id_number (tied to date_of_birth and a
    uniqueness constraint - changing it post-registration is a bigger
    deal than a profile edit, same reasoning as a tutor's bank details
    staying out of their own self-service edit)."""
    province = (province or "").strip()
    city_town = (city_town or "").strip()
    school = (school or "").strip()

    if not province:
        raise AuthError("Please select your province.")
    if not city_town:
        raise AuthError("Please enter your city or town.")
    if grade is not None and grade not in (10, 11, 12):
        raise AuthError("Grade must be 10, 11, or 12.")

    with get_session() as db:
        user = db.query(User).get(user_id)
        if not user:
            raise AuthError("Account not found.")
        user.province = province
        user.city_town = city_town
        if user.account_type == "high_school":
            user.school = school or None
            user.grade = grade


def login_user(email: str, password: str, source: str = None) -> dict:
    email = (email or "").strip().lower()

    with get_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not _verify_password(password, user.password_hash):
            raise AuthError("Incorrect email or password.")

        db.add(LoginEvent(user_id=user.id, source=source))

        tier = user.subscription.tier if user.subscription else "free"
        status = user.subscription.status if user.subscription else "active"

        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "tier": tier,
            "subscription_status": status,
            "is_admin": user.is_admin,
            "account_type": user.account_type,
            "cross_segment_access": user.cross_segment_access,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "account_status": user.account_status,
            "account_status_reason": user.account_status_reason,
            "school": user.school,
            "grade": user.grade,
            "province": user.province,
            "city_town": user.city_town,
            "id_number": user.id_number,
            "higher_ed_institution_id": user.higher_ed_institution_id,
            "higher_ed_qualification_id": user.higher_ed_qualification_id,
            "higher_ed_qualification_custom_name": user.higher_ed_qualification_custom_name,
            "higher_ed_year_of_study": user.higher_ed_year_of_study,
            "student_number": user.student_number,
        }


def get_user_tier(user_id: int) -> str:
    """Live lookup — always call this before gating a feature, rather than
    trusting a cached tier in session_state, since a payment/cancellation
    could have changed it since login.

    Also the one place a scheduled downgrade (see schedule_downgrade())
    actually takes effect: if pending_tier is set and current_period_end
    has passed, this flips tier -> pending_tier right here, lazily, on
    whichever request happens to notice it first - no cron job needed
    for a service at this scale."""
    with get_session() as db:
        user = db.query(User).get(user_id)
        if not user or not user.subscription:
            return "free"
        sub = user.subscription
        if sub.pending_tier and sub.current_period_end and dt.datetime.utcnow() >= sub.current_period_end:
            sub.tier = sub.pending_tier
            sub.pending_tier = None
            if sub.tier == "free":
                sub.status = "cancelled"
        if sub.status != "active":
            return "free"
        return sub.tier


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


def cancel_subscription(user_id: int) -> dict:
    """Cancel a user's paid subscription. Always downgrades access in our
    own system immediately (status -> 'cancelled', which get_user_tier()
    already treats as free). What happens next depends on which checkout
    the subscription was bought through:
      - payfast: best-effort tells PayFast to stop the recurring billing.
      - play_billing: Google doesn't let a developer cancel a Play-billed
        subscription via the API on the user's behalf - Play's own policy
        requires the learner to manage/cancel it from the Play Store app
        (Subscriptions screen) instead, so we only downgrade our own
        records here and tell the UI to point them there.
    Returns a dict the UI uses to tell the learner exactly what happened:
      had_subscription: was there anything to cancel at all
      provider: "payfast" | "play_billing" | None
      payfast_notified: did PayFast confirm the recurring billing stopped
        (None when the provider is play_billing - not applicable)
    If payfast_notified is False, the learner should be told to also check
    directly with PayFast — we never want someone to believe they've
    stopped paying when the recurring charge might still be active."""
    with get_session() as db:
        sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
        if not sub or sub.tier == "free" or sub.status != "active":
            return {"had_subscription": False, "provider": None, "payfast_notified": False}

        if sub.payment_provider == "play_billing":
            sub.status = "cancelled"
            return {"had_subscription": True, "provider": "play_billing", "payfast_notified": None}

        payfast_notified = cancel_payfast_subscription(sub.payfast_token)
        sub.status = "cancelled"
        return {"had_subscription": True, "provider": "payfast", "payfast_notified": payfast_notified}


def delete_account(user_id: int) -> dict:
    """Permanently delete a learner's account and all associated data, for
    the in-app "Delete My Account" flow (Play Store account-deletion
    requirement). Best-effort cancels any active PayFast recurring billing
    first, same as cancel_subscription - Play-billed subscriptions can't be
    cancelled on the user's behalf via the API, so for those we only warn
    the caller to point the learner at the Play Store Subscriptions screen.
    Deleting the User row cascades to Subscription, UsageLog,
    SolvedQuestion, PasswordReset, ApiToken, and LoginEvent via the
    relationships already defined on the User model (cascade="all,
    delete-orphan"). Forum content (CollabQuestion/CollabAnswer/
    CollabReport) is left in place, attributed to the now-deleted user id,
    matching how most forums handle a departed member's posts rather than
    silently breaking other learners' threads that reference them.
    Returns a dict the caller uses to tell the learner what happened."""
    with get_session() as db:
        user = db.query(User).get(user_id)
        if not user:
            raise AuthError("Account not found.")

        sub = user.subscription
        provider = sub.payment_provider if sub and sub.status == "active" else None
        payfast_notified = None
        if sub and sub.status == "active" and sub.payment_provider == "payfast":
            payfast_notified = cancel_payfast_subscription(sub.payfast_token)

        db.delete(user)
        return {"deleted": True, "had_active_subscription": provider is not None, "provider": provider, "payfast_notified": payfast_notified}


def schedule_downgrade(user_id: int, new_tier: str) -> dict:
    """Move to a LOWER tier at the end of the currently-paid period,
    rather than immediately - the learner keeps their current tier's
    access (already paid for, not refunded) until current_period_end,
    matching how the Play Store/App Store/most subscription apps handle
    a downgrade. get_user_tier() is where pending_tier actually takes
    effect, once that date arrives.

    Only valid for moving to a tier STRICTLY LOWER than the one currently
    active - an upgrade should go through the normal checkout flow
    instead (billing_checkout_page / billing_google_verify), which still
    applies immediately, same as before.

    PayFast has no "change this recurring agreement's amount later" API
    - it's cancel-and-recreate only - so for a PayFast-billed
    subscription this cancels the current recurring billing right away
    (so it won't renew at the old, higher price) while leaving tier/
    status untouched until current_period_end. The learner needs to
    actively check out again for the new lower tier once that date
    arrives if they still want paid access at that tier rather than
    drop to Free - callers must make that tradeoff clear in the UI.

    For a Play-billed subscription, this should be called right after
    the native deferred-replacement purchase has already been requested
    via expo-iap (Play Billing handles the actual billing-time swap
    itself); this call just mirrors "keep current tier until period end"
    in our own records too, since we won't hear from Google again until
    the swap has already happened on their side."""
    with get_session() as db:
        sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
        if not sub or sub.tier == "free" or sub.status != "active":
            return {"scheduled": False, "effective_date": None}
        if TIER_ORDER.index(new_tier) >= TIER_ORDER.index(sub.tier):
            return {"scheduled": False, "effective_date": None}  # not actually a downgrade

        payfast_notified = None
        if sub.payment_provider == "payfast":
            payfast_notified = cancel_payfast_subscription(sub.payfast_token)
        sub.pending_tier = new_tier
        return {
            "scheduled": True,
            "effective_date": sub.current_period_end,
            "new_tier": new_tier,
            "payfast_notified": payfast_notified,
        }


def create_api_token(user_id: int) -> str:
    """Issue a new bearer token for the native app (see ApiToken docstring
    in db.py for why this exists separately from Streamlit's session).
    A user can hold multiple tokens at once (one per device) - logging in
    from a new phone doesn't invalidate other devices' tokens."""
    token = secrets.token_urlsafe(32)
    with get_session() as db:
        db.add(ApiToken(user_id=user_id, token=token))
    return token


def get_user_by_token(token: str):
    """Resolve a bearer token to the same user dict shape login_user()
    returns, or None if the token is unknown/revoked. Used as the native
    app's auth dependency on every API request."""
    with get_session() as db:
        api_token = db.query(ApiToken).filter(ApiToken.token == token).first()
        if not api_token:
            return None
        last_activity = api_token.last_used_at or api_token.created_at
        if last_activity and dt.datetime.utcnow() - last_activity > dt.timedelta(days=INACTIVE_TOKEN_LOGOUT_DAYS):
            db.delete(api_token)
            return None
        api_token.last_used_at = dt.datetime.utcnow()

        user = db.query(User).get(api_token.user_id)
        if not user:
            return None
        tier = user.subscription.tier if user.subscription else "free"
        status = user.subscription.status if user.subscription else "active"
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "tier": tier,
            "subscription_status": status,
            "is_admin": user.is_admin,
            "account_type": user.account_type,
            "cross_segment_access": user.cross_segment_access,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "account_status": user.account_status,
            "account_status_reason": user.account_status_reason,
            "school": user.school,
            "grade": user.grade,
            "province": user.province,
            "city_town": user.city_town,
            "id_number": user.id_number,
            "higher_ed_institution_id": user.higher_ed_institution_id,
            "higher_ed_qualification_id": user.higher_ed_qualification_id,
            "higher_ed_qualification_custom_name": user.higher_ed_qualification_custom_name,
            "higher_ed_year_of_study": user.higher_ed_year_of_study,
            "student_number": user.student_number,
        }


def revoke_api_token(token: str) -> None:
    """Log out a single device (used by the native app's logout button)."""
    with get_session() as db:
        db.query(ApiToken).filter(ApiToken.token == token).delete()


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


def _set_account_standing(user_id: int, new_status: str, reason: str = "") -> dict:
    """Shared by suspend_user/block_user/reinstate_user - an admin can
    never be suspended/blocked through this (a deliberate safety check,
    same spirit as backend/set_admin.py being a server-shell-only
    action): an admin locking out their OWN account, or another admin's,
    this way would have no in-app way back. Returns the info the caller
    (api_server.py) needs to email/notify the account - this module
    doesn't send email/notifications itself, same as every other
    function here (see reset_password/create_password_reset)."""
    with get_session() as db:
        user = db.query(User).get(user_id)
        if not user:
            raise AuthError("Account not found.")
        if user.is_admin:
            raise AuthError("An admin account can't be suspended or blocked this way.")
        user.account_status = new_status
        user.account_status_reason = (reason or "").strip() or None
        user.account_status_changed_at = dt.datetime.utcnow()
        return {"id": user.id, "name": user.name, "email": user.email}


def suspend_user(user_id: int, reason: str = "") -> dict:
    """Temporarily disables a learner account - e.g. while an investigation
    is ongoing. They can still log in (see login_user/get_user_by_token
    returning account_status) and see why, but every feature screen is
    gated behind it client-side. See reinstate_user to lift this."""
    return _set_account_standing(user_id, "suspended", reason)


def block_user(user_id: int, reason: str = "") -> dict:
    """Permanently disables a learner account, same gating as
    suspend_user but meant as a final decision rather than a holding
    pattern. See reinstate_user to lift this."""
    return _set_account_standing(user_id, "blocked", reason)


def reinstate_user(user_id: int) -> dict:
    """Lifts a suspension or a block - the same action either way, since
    both just mean "back to normal." The admin console labels the button
    "Unsuspend" or "Unblock" depending on which one applies."""
    return _set_account_standing(user_id, "active", "")


def list_users_for_admin(search: str = "", limit: int = 50) -> list[dict]:
    """A plain, searchable list of learner accounts for the admin console's
    new Accounts tab - nothing like this existed before (the only admin
    account-management view was tutor-specific), since suspending/blocking
    a learner needs a way to actually find the account first. `search`
    matches name or email, case-insensitively; empty search returns the
    most recently created accounts first."""
    search = (search or "").strip().lower()
    with get_session() as db:
        q = db.query(User)
        if search:
            like = f"%{search}%"
            q = q.filter((User.name.ilike(like)) | (User.email.ilike(like)))
        users = q.order_by(User.created_at.desc()).limit(limit).all()
        return [
            {
                "id": u.id, "name": u.name, "email": u.email,
                "account_type": u.account_type, "is_admin": u.is_admin,
                "account_status": u.account_status,
                "account_status_label": ACCOUNT_STANDING_LABELS.get(u.account_status, u.account_status),
                "account_status_reason": u.account_status_reason,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]

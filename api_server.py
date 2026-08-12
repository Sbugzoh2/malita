"""
Malita (Pty) Ltd — REST API for the native app (React Native).

WHY THIS IS A SEPARATE SERVICE FROM app.py:
Same reasoning as webhook_server.py - Streamlit is a self-contained
frontend framework, not a general HTTP API server. The native app can't
talk to Streamlit's WebSocket-driven UI at all, so it needs a real,
stateless REST API. This file exposes the same backend/ logic (auth,
usage limits, solving) that app.py already uses, as JSON endpoints.

All 10 AI Tutor topics, OCR (camera/gallery photo -> recognised
expression), and PDF past-paper text extraction are now ported - see
README.md section 8 for what's still Streamlit-only (Practice
Questions, Learner Profile, Formula Sheet, subscriptions).

RUN IT WITH:
    uvicorn api_server:app --host 0.0.0.0 --port 8002
"""

import datetime as dt
import os
import uuid

from dotenv import load_dotenv
load_dotenv()

from io import BytesIO

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from PIL import Image

LEGAL_DIR = Path(__file__).resolve().parent / "static" / "legal"

from backend.db import init_db, SA_PROVINCES
from backend.auth import (
    register_user, login_user, AuthError, is_user_admin,
    create_api_token, get_user_by_token, revoke_api_token,
    create_password_reset, reset_password, cancel_subscription,
)
from backend.tiers import TIER_CONFIG, TIER_ORDER, daily_limit, can_use_ocr, can_use_pdf, can_use_past_papers
from backend.usage import can_solve, record_solve, get_today_count
from backend.records import record_solved_question
from backend.auth import get_user_tier
from backend.solver import (
    solve_algebra, solve_sequences, solve_financial_mathematics, solve_calculus,
    solve_functions_graphs, solve_analytical_geometry, solve_trigonometry,
    solve_statistics, solve_probability, solve_euclidean_geometry_topic,
)
from backend.ocr import preprocess_image, ocr_with_exponents, clean_for_sympy
from backend.pdf_extract import extract_pdf_text
from backend.payfast import build_checkout_payload, build_checkout_url
from backend.practice import practice_data, check_practice_answer

# Same env vars app.py reads - the mobile checkout link has to round-trip
# through the same webhook, so both apps' PayFast configuration must agree.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8501")
APP_WEBHOOK_URL = os.environ.get("APP_WEBHOOK_URL", "http://localhost:8001/payfast/notify")

app = FastAPI(title="Malita API")
init_db()

# The native app is the primary client and (being a real iOS/Android app,
# not a browser) is never subject to CORS at all - but Expo's web preview
# and any future browser-based client (Expo web build, admin tooling)
# would be blocked by the browser's own CORS preflight without this. Auth
# is via bearer token, not cookies, so a permissive origin list here
# doesn't expose session-riding/CSRF risk the way it would for a
# cookie-authenticated API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# All 10 AI Tutor topics are now ported - see README.md section 8 for
# what's still Streamlit-only (OCR, PDF past papers, Practice Questions,
# Learner Profile, Formula Sheet, subscriptions).
SUPPORTED_SOLVE_TOPICS = {
    "Algebra": solve_algebra,
    "Sequences": solve_sequences,
    "Financial Mathematics": solve_financial_mathematics,
    "Calculus": solve_calculus,
    "Functions & Graphs": solve_functions_graphs,
    "Analytical Geometry": solve_analytical_geometry,
    "Trigonometry": solve_trigonometry,
    "Statistics": solve_statistics,
    "Probability": solve_probability,
    "Euclidean Geometry": solve_euclidean_geometry_topic,
}


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    province: str
    city_town: str
    school: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class SolveRequest(BaseModel):
    paper: str
    topic: str
    question: str


class PracticeCheckRequest(BaseModel):
    answer: str
    expected_latex: str


class PracticeRecordRequest(BaseModel):
    paper: str
    topic: str
    question: str


class CheckoutRequest(BaseModel):
    tier: str


def _auth_user(authorization: str | None):
    """FastAPI dependency-style helper: parse 'Bearer <token>' and resolve
    it to a user dict, or raise 401. Not using FastAPI's OAuth2 machinery
    since we don't need scopes/OpenAPI security schemes - just a bearer
    token lookup against ApiToken, same as Streamlit's session_state but
    for a stateless HTTP client."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization[len("Bearer "):]
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return user


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/meta/provinces")
def provinces():
    return {"provinces": list(SA_PROVINCES)}


@app.post("/auth/register")
def register(body: RegisterRequest):
    try:
        user = register_user(
            body.name, body.email, body.password, body.school,
            province=body.province, city_town=body.city_town,
        )
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Auto-login right after registering — a native app shouldn't force a
    # second "now log in" screen right after sign-up.
    token = create_api_token(user["id"])
    return {"token": token, "user": login_user(body.email, body.password)}


@app.post("/auth/login")
def login(body: LoginRequest):
    try:
        user = login_user(body.email, body.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    token = create_api_token(user["id"])
    return {"token": token, "user": user}


@app.post("/auth/logout")
def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        revoke_api_token(authorization[len("Bearer "):])
    return {"ok": True}


@app.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    # Deliberately the same response either way — never reveal whether an
    # email is registered (see create_password_reset's own docstring).
    create_password_reset(body.email)
    return {"message": "If an account exists for that email, a reset link has been generated."}


@app.post("/auth/reset-password")
def do_reset_password(body: ResetPasswordRequest):
    try:
        reset_password(body.token, body.new_password)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@app.get("/me")
def me(authorization: str = Header(None)):
    user = _auth_user(authorization)
    is_admin = is_user_admin(user["id"])
    effective_tier = "premium" if is_admin else get_user_tier(user["id"])
    limit = daily_limit(effective_tier)
    used_today = get_today_count(user["id"]) if limit is not None else 0
    return {
        "user": user,
        "is_admin": is_admin,
        "effective_tier": effective_tier,
        "tier_label": TIER_CONFIG[effective_tier]["label"],
        "daily_limit": limit,
        "used_today": used_today,
    }


@app.post("/solve")
def solve(body: SolveRequest, authorization: str = Header(None)):
    user = _auth_user(authorization)
    is_admin = is_user_admin(user["id"])
    effective_tier = "premium" if is_admin else get_user_tier(user["id"])

    allowed, limit_message = can_solve(user["id"], effective_tier)
    if not allowed:
        raise HTTPException(status_code=429, detail=limit_message)

    solver = SUPPORTED_SOLVE_TOPICS.get(body.topic)
    if solver is None:
        raise HTTPException(
            status_code=501,
            detail=(
                f"'{body.topic}' isn't available in the app yet — it currently "
                "only works in the web version. Try Algebra here for now."
            ),
        )

    record_solve(user["id"])
    record_solved_question(user["id"], "ai_tutor", paper=body.paper, topic=body.topic, question=body.question)
    steps = solver(body.question)
    return {"steps": steps}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...), authorization: str = Header(None)):
    """Accepts a photo (camera capture or gallery upload from the native
    app - either path lands here as the same multipart file) and returns
    the recognised expression, cleaned up for the AI Tutor solver. Mirrors
    app.py's OCR Question mode exactly (same backend.ocr functions)."""
    user = _auth_user(authorization)
    is_admin = is_user_admin(user["id"])
    effective_tier = "premium" if is_admin else get_user_tier(user["id"])
    if not can_use_ocr(effective_tier):
        raise HTTPException(
            status_code=403,
            detail="Photo upload & OCR is a Learner/Premium feature. Upgrade to unlock it.",
        )

    image_bytes = await file.read()
    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read that image file.")

    raw = ocr_with_exponents(preprocess_image(img))
    cleaned = clean_for_sympy(raw)
    return {"text": cleaned}


@app.post("/pdf-extract")
async def pdf_extract(file: UploadFile = File(...), authorization: str = Header(None)):
    """Accepts a past-paper PDF and returns its raw extracted text, the
    same way app.py's Past Papers (PDF) mode does (same
    backend.pdf_extract function) - the native app can then let the
    learner edit/select from it before sending a question to /solve."""
    user = _auth_user(authorization)
    is_admin = is_user_admin(user["id"])
    effective_tier = "premium" if is_admin else get_user_tier(user["id"])
    if not can_use_pdf(effective_tier):
        raise HTTPException(
            status_code=403,
            detail="Past paper PDF extraction is a Learner/Premium feature. Upgrade to unlock it.",
        )

    pdf_bytes = await file.read()
    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read that PDF file.")
    return {"text": text}


@app.get("/billing/tiers")
def billing_tiers():
    """Plan list for the mobile Subscription screen - same TIER_CONFIG
    app.py's sidebar reads from, just as JSON."""
    return {
        "tiers": [
            {"key": key, **TIER_CONFIG[key]}
            for key in TIER_ORDER
        ]
    }


@app.post("/billing/checkout")
def billing_checkout(body: CheckoutRequest, authorization: str = Header(None)):
    """Builds a PayFast checkout link exactly like app.py's sidebar
    Upgrade button does, and hands the URL back so the native app can
    open it in the phone's browser (Linking.openURL) - no payment UI is
    reimplemented natively, this just reuses the same tested flow."""
    user = _auth_user(authorization)
    cfg = TIER_CONFIG.get(body.tier)
    if cfg is None or cfg["price_zar"] == 0:
        raise HTTPException(status_code=400, detail="Not a paid plan.")

    payload = build_checkout_payload(
        m_payment_id=f"{user['id']}-{uuid.uuid4().hex[:8]}",
        amount=cfg["price_zar"],
        item_name=f"Malita {cfg['label']} Subscription",
        name_first=user["name"].split(" ")[0],
        email_address=user["email"],
        return_url=f"{APP_BASE_URL}/?upgraded=1",
        cancel_url=f"{APP_BASE_URL}/?cancelled=1",
        notify_url=APP_WEBHOOK_URL,
        recurring=True,
        recurring_amount=cfg["price_zar"],
        frequency=3,  # monthly
        cycles=0,     # bill indefinitely until cancelled
        custom_fields={"custom_str1": str(user["id"]), "custom_str2": body.tier},
    )
    return {"checkout_url": build_checkout_url(payload)}


@app.post("/billing/cancel")
def billing_cancel(authorization: str = Header(None)):
    user = _auth_user(authorization)
    result = cancel_subscription(user["id"])
    return result


@app.get("/practice/topics")
def practice_topics(authorization: str = Header(None)):
    """Available paper/topic combinations - same practice_data app.py's
    Practice Questions mode reads from, just as JSON."""
    _auth_user(authorization)
    return {
        paper: list(topics.keys())
        for paper, topics in practice_data.items()
    }


@app.get("/practice/questions")
def practice_questions(paper: str, topic: str, authorization: str = Header(None)):
    """Every question for one paper/topic, including hint/solution_steps/
    final_answer - the mobile client decides when to reveal those client
    side, exactly like app.py's "Show Solution" button does."""
    _auth_user(authorization)
    topics = practice_data.get(paper)
    if topics is None or topic not in topics:
        raise HTTPException(status_code=404, detail="Unknown paper/topic.")
    return {"questions": topics[topic]}


@app.post("/practice/check")
def practice_check(body: PracticeCheckRequest, authorization: str = Header(None)):
    """Best-effort numeric grading - same check_practice_answer() app.py
    uses. `correct` is null when the expected answer has no numbers to
    compare against (the client should just let the learner reveal the
    solution instead of claiming right/wrong)."""
    _auth_user(authorization)
    verdict = check_practice_answer(body.answer, body.expected_latex)
    return {"correct": verdict}


@app.post("/practice/record")
def practice_record(body: PracticeRecordRequest, authorization: str = Header(None)):
    """Logs one practice question as solved for progress tracking - call
    this when the learner reveals a solution, mirroring app.py's
    solved_set bookkeeping (mobile has no server session to dedupe
    against, so the client should only call this once per question)."""
    user = _auth_user(authorization)
    record_solved_question(user["id"], "practice", paper=body.paper, topic=body.topic, question=body.question)
    return {"ok": True}


@app.get("/past-papers")
def past_papers_list(authorization: str = Header(None)):
    """Placeholder for the curated Past Papers Library - not populated
    yet, see the conversation with the user about how papers will be
    sourced. Returns an empty, tier-gated list so the mobile screen has
    a real endpoint to call once papers exist."""
    user = _auth_user(authorization)
    is_admin = is_user_admin(user["id"])
    effective_tier = "premium" if is_admin else get_user_tier(user["id"])
    if not can_use_past_papers(effective_tier):
        raise HTTPException(
            status_code=403,
            detail="The Past Papers Library is a Premium feature. Upgrade to unlock it.",
        )
    return {"papers": []}


@app.get("/terms", response_class=HTMLResponse)
def terms():
    """Public, unauthenticated - both app.py and the mobile app link out
    here rather than each carrying their own copy, so there is exactly
    one canonical Terms & Conditions (also what app store review expects:
    a working public URL, not in-app-only text)."""
    return (LEGAL_DIR / "terms.html").read_text(encoding="utf-8")


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    """Public, unauthenticated - same hosting pattern as /terms, one
    canonical Privacy Policy both app.py and the mobile app link out to."""
    return (LEGAL_DIR / "privacy.html").read_text(encoding="utf-8")

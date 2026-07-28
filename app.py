import os
from dotenv import load_dotenv
load_dotenv()

import re
import sympy as sp
import streamlit as st
from PIL import Image
import numpy as np
import cv2
import pytesseract
import matplotlib.pyplot as plt
import fitz  # PyMuPDF
#import PyMuPDF
from sympy.solvers.inequalities import solve_univariate_inequality
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)
import base64
import uuid
import random

#from frontend import *

from backend.db import init_db, SA_PROVINCES
from backend.auth import (
    register_user, login_user, get_user_tier, is_user_admin, AuthError,
    create_password_reset, reset_password, cancel_subscription,
)
from backend.email_util import send_email
from backend.tiers import TIER_CONFIG, TIER_ORDER, can_use_ocr, can_use_pdf, daily_limit
from backend.usage import can_solve, record_solve, get_today_count, reset_today_usage
from backend.records import record_solved_question, get_recent_solved
from backend.payfast import build_checkout_payload, build_checkout_url

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8501")
APP_WEBHOOK_URL = os.environ.get("APP_WEBHOOK_URL", "http://localhost:8001/payfast/notify")

init_db()

# -------------------------------------------------
# HELPER: Convert SVG to Base64
# -------------------------------------------------
def svg_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# -------------------------------------------------
# LOAD LOGO ONCE (GLOBAL SCOPE)
# -------------------------------------------------
# Put your logo at assets/icon.png. Falls back to no logo (rather than
# crashing the whole app) if it hasn't been added yet.
try:
    logo_svg = svg_to_base64("assets/icon.png")
except FileNotFoundError:
    logo_svg = None



# =====================================================
# CONFIG
# =====================================================
#pytesseract.pytesseract.tesseract_cmd = r"C:\Users\10119145\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# Only set path locally, and only if it actually exists on this machine.
# On servers / Linux hosting, Tesseract must be installed via the OS package
# manager (e.g. apt-get install tesseract-ocr) and will already be on PATH,
# so pytesseract can find it without us setting tesseract_cmd at all.
if os.name == "nt":
    _local_tesseract_path = r"C:\Users\10119145\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_local_tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = _local_tesseract_path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

st.set_page_config("Matric Math Master", layout="wide", page_icon="🎓")

# =====================================================
# AUTHENTICATION GATE
# =====================================================
# Nothing below this point renders until someone is logged in. auth_user
# lives only in this browser tab's session_state (Streamlit has no
# server-side session concept beyond that), which is fine — the actual
# account + subscription tier live safely in the database either way.
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if st.session_state.auth_user is None:
    st.title("🎓 Malita — Matric Maths Master")
    st.caption("AI-powered Grade 12 Mathematics tutoring, built for South African learners 🇿🇦")

    reset_token = st.query_params.get("reset_token")

    if reset_token:
        st.subheader("Set a new password")
        with st.form("reset_password_form"):
            new_password = st.text_input("New password", type="password")
            new_password_confirm = st.text_input("Confirm new password", type="password")
            submitted_reset = st.form_submit_button("Update Password")
            if submitted_reset:
                if new_password != new_password_confirm:
                    st.error("Passwords don't match.")
                else:
                    try:
                        reset_password(reset_token, new_password)
                        st.query_params.clear()
                        st.success("Password updated! You can now log in with your new password.")
                    except AuthError as e:
                        st.error(str(e))
        st.stop()

    login_tab, register_tab = st.tabs(["Log In", "Create Account"])

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input("Email")
            login_password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In")
            if submitted:
                try:
                    user = login_user(login_email, login_password)
                    st.session_state.auth_user = user
                    st.rerun()
                except AuthError as e:
                    st.error(str(e))

        with st.expander("Forgot your password?"):
            with st.form("forgot_password_form"):
                forgot_email = st.text_input("Email", key="forgot_email")
                submitted_forgot = st.form_submit_button("Send reset link")
                if submitted_forgot:
                    token = create_password_reset(forgot_email)
                    if token:
                        reset_url = f"{APP_BASE_URL}/?reset_token={token}"
                        sent = send_email(
                            forgot_email,
                            "Reset your Malita password",
                            f"Click the link below to set a new password (valid for 1 hour):\n\n{reset_url}",
                        )
                        if sent:
                            st.success("Check your email for a password reset link (valid for 1 hour).")
                        else:
                            st.info(
                                "Email sending isn't configured yet, so here's your reset link directly "
                                "(valid for 1 hour) — click it to set a new password:"
                            )
                            st.code(reset_url, language=None)
                    else:
                        st.success("If an account exists for that email, a reset link has been generated.")

    with register_tab:
        with st.form("register_form"):
            reg_name = st.text_input("Full name")
            reg_email = st.text_input("Email", key="reg_email")
            reg_school = st.text_input("School (optional)")
            reg_province = st.selectbox("Province", SA_PROVINCES)
            reg_city = st.text_input("City / Town")
            reg_password = st.text_input("Password", type="password", key="reg_pw")
            reg_password_confirm = st.text_input("Confirm password", type="password")
            submitted_reg = st.form_submit_button("Create Free Account")
            if submitted_reg:
                if reg_password != reg_password_confirm:
                    st.error("Passwords don't match.")
                else:
                    try:
                        user = register_user(
                            reg_name, reg_email, reg_password, reg_school,
                            province=reg_province, city_town=reg_city,
                        )
                        st.success("Account created! Please log in on the 'Log In' tab.")
                    except AuthError as e:
                        st.error(str(e))

    st.stop()

auth_user = st.session_state.auth_user

# =====================================================
# SAFE MATH EXPRESSION PARSING
# =====================================================
# We NEVER call sp.sympify()/eval() directly on raw user text. sp.sympify()
# ultimately runs Python's eval() on the string, so a malicious user could
# type something that isn't math at all and have it executed on the server.
# Instead we use sympy's parse_expr() with:
#   - global_dict locked down (no builtins, no arbitrary names)
#   - local_dict containing ONLY the math symbols/functions we explicitly allow
FUNCTION_NAMES = {
    "sin", "cos", "tan", "sinh", "cosh", "tanh",
    "asin", "acos", "atan", "asinh", "acosh", "atanh",
    "exp", "log", "ln", "sqrt", "pi", "abs",
}

SAFE_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

# parse_expr's internal transformations (auto_symbol, auto_number, etc.)
# need names like Integer/Symbol/Rational to resolve at eval time, so we
# can't hand it a totally empty global_dict. We give it sympy's own names
# (safe - just math) but explicitly strip Python's real builtins so nothing
# like __import__/open/exec/eval is reachable from user input.
_SAFE_GLOBAL_DICT = {}
exec("from sympy import *", _SAFE_GLOBAL_DICT)
_SAFE_GLOBAL_DICT["__builtins__"] = {}

def _fmt_num(v):
    """Display a number as an integer when it is one (e.g. 4 not 4.0),
    otherwise as a short decimal — used throughout the AI Tutor to keep
    step-by-step working readable."""
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:.4g}"

# A validated 8-hue categorical palette (fixed order, not cycled — see the
# dataviz skill) used to give each topic its own identity throughout the
# app, subject-tile-grid style, instead of a single flat blue everywhere.
# 10 topics share these 8 slots; the last two intentionally reuse a slot
# since axis/badge text labels — never color alone — always carry identity.
TOPIC_COLORS = {
    "Algebra": "#2a78d6",
    "Sequences": "#eb6834",
    "Financial Mathematics": "#1baf7a",
    "Calculus": "#eda100",
    "Functions & Graphs": "#e87ba4",
    "Analytical Geometry": "#008300",
    "Trigonometry": "#4a3aa7",
    "Statistics": "#e34948",
    "Statistics & Probability": "#e34948",
    "Probability": "#2a78d6",
    "Euclidean Geometry": "#eb6834",
}
_DEFAULT_TOPIC_COLOR = "#2a78d6"

def topic_badge(topic):
    """Render a small coloured pill naming the current topic — used next
    to topic pickers so each subject reads with a consistent identity."""
    color = TOPIC_COLORS.get(topic, _DEFAULT_TOPIC_COLOR)
    st.markdown(
        f'<span class="topic-badge" style="background:{color};">{topic}</span>',
        unsafe_allow_html=True,
    )

def detect_variables(expr_str):
    """Find the single-letter variable candidates in a string, ignoring
    known function names like sin/cos/exp/pi/log/etc. Works for ANY letter
    the user chooses (x, a, t, k, ...), not just x."""
    tokens = re.findall(r"[a-zA-Z]+", expr_str)
    letters = set()
    for tok in tokens:
        if tok.lower() in FUNCTION_NAMES:
            continue
        for ch in tok:
            letters.add(ch)
    return sorted(letters)

def build_safe_locals(extra_symbols=None):
    """Base set of allowed function/constant names for parsing, plus any
    user-detected variable symbols."""
    locals_dict = {
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
        "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
        "exp": sp.exp, "log": sp.log, "ln": sp.log,
        "sqrt": sp.sqrt, "pi": sp.pi, "E": sp.E, "Abs": sp.Abs,
    }
    if extra_symbols:
        locals_dict.update(extra_symbols)
    return locals_dict

def safe_parse(expr_str, symbols_dict=None):
    """Safely parse a user-entered math expression into a SymPy object
    WITHOUT ever invoking arbitrary Python eval() on untrusted input."""
    local_dict = build_safe_locals(symbols_dict)
    return parse_expr(
        expr_str,
        local_dict=local_dict,
        global_dict=_SAFE_GLOBAL_DICT,  # sympy names only, builtins stripped
        transformations=SAFE_TRANSFORMATIONS,
    )
# ====================================================================================================
# TOP BANNER
# A plain static strip instead of a scrolling marquee — reads as a normal
# product header rather than a dated auto-scrolling ticker.

st.markdown("""
<div class="top-banner">
    Algebra · Functions · Finance · Trigonometry · Statistics — worked out step by step
</div>
<style>
.top-banner {
    background: white;
    border-radius: 18px;
    padding: 16px 24px;
    margin-bottom: 24px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.08);
    font-size: 1.05rem;
    font-weight: 600;
    color: #1e293b;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)



# =============================================================================================
#---------------------------------STYLING------------------------------------------------------------------------------
# =============================================================================================



st.markdown("""
<style>

/* ---------- GLOBAL ---------- */
html, body, [class*="css"]  {
    font-family: 'Segoe UI', sans-serif;
}

/* ---------- PAGE BACKGROUND ---------- */
/* Setting `color` here too (not just background) matters on mobile: if a
   phone is in dark mode, Streamlit's default text color switches to white
   to match — without this, that white text becomes invisible against the
   light background below. `.streamlit/config.toml` locks the theme itself,
   this is a belt-and-braces fallback for anything that doesn't pick that up.
   The sidebar's own text-color rule further below still wins inside the
   sidebar since it's more specific. */
.stApp {
    background: #f9f9f7;
    color: #0b0b0b;
}

/* Ensure content never causes horizontal scrolling on narrow phone screens */
.stApp, .main .block-container {
    overflow-x: hidden;
}
img {
    max-width: 100%;
    height: auto;
}

/* ---------- HEADINGS ---------- */
h1, h2, h3 {
    color: #0b0b0b;
    font-weight: 700;
}

/* ---------- CARDS ---------- */
.card {
    background: white;
    padding: 1.5rem;
    border-radius: 20px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.06);
    margin-bottom: 1.5rem;
}

/* Colourful subject-tile cards used on the Home dashboard, one accent
   colour per tile (set inline via style="--tile-color:#..") so they read
   like a subject/topic picker rather than a single flat-blue app. */
.subject-tile {
    background: var(--tile-color, #2a78d6);
    border-radius: 20px;
    padding: 1.4rem 1.2rem;
    color: white;
    box-shadow: 0 10px 22px rgba(0,0,0,0.12);
    margin-bottom: 0.6rem;
}
.subject-tile .tile-icon { font-size: 2.2rem; }
.subject-tile .tile-title { font-size: 1.15rem; font-weight: 700; margin: 0.3rem 0 0.2rem 0; }
.subject-tile .tile-desc { font-size: 0.85rem; opacity: 0.92; margin: 0; }

/* Small coloured pill used to show which topic is currently selected. */
.topic-badge {
    display: inline-block;
    padding: 0.25rem 0.85rem;
    border-radius: 999px;
    color: white;
    font-weight: 600;
    font-size: 0.85rem;
    margin: 0.3rem 0 0.8rem 0;
}

/* ---------- INPUTS ---------- */
/* Default input backgrounds can end up nearly the same shade as the page
   gradient behind them, making fields like "Enter your expression..."
   hard to spot. Give every input a clearly visible white background with
   a real border so it always reads as an editable field. */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div {
    background-color: #ffffff;
    border: 1px solid #d8d7d0;
    color: #0b0b0b;
}

.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus,
.stSelectbox div[data-baseweb="select"] > div:focus-within {
    border-color: #2a78d6;
    box-shadow: 0 0 0 1px #2a78d6;
}

/* ---------- BUTTONS ---------- */
.stButton > button {
    background: #2a78d6;
    color: white;
    border-radius: 999px;
    padding: 0.6rem 1.4rem;
    font-weight: 600;
    border: none;
}

.stButton > button:hover {
    background: #184f95;
    transform: scale(1.02);
}

/* ---------- SIDEBAR ---------- */
/* A clean light sidebar (rather than a dark admin-panel navy) reads as a
   friendlier, more approachable "learning site" look. */
section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e1e0d9;
}

section[data-testid="stSidebar"] * {
    color: #0b0b0b !important;
}

section[data-testid="stSidebar"] .stButton > button {
    background: #2a78d6;
    color: white !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: #184f95;
}

/* ---------- METRICS ---------- */
[data-testid="stMetricValue"] {
    font-size: 2rem;
    color: #2a78d6;
}

</style>
""", unsafe_allow_html=True)


# =====================================================
# OCR FUNCTIONS
# =====================================================
def preprocess_image(pil_image):
    """Upscale + adaptively threshold before OCR. Tesseract badly misreads
    the tiny superscript exponents typical of maths photos (e.g. dropping
    or misreading the "2"/"6" in y=x^2-4x^6) unless the text is reasonably
    large and the threshold is tuned per-image rather than a fixed cutoff."""
    img = np.array(pil_image.convert("L"))

    # Scale up small images — tiny exponents are the single biggest cause
    # of OCR misreads on maths photos.
    img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    # Otsu's method picks the threshold from each image's own brightness
    # distribution instead of a fixed cutoff, which holds up far better
    # across photos taken in different lighting than a flat "150".
    _, img_bin = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return img_bin

# Restrict recognition to characters that actually appear in maths
# expressions, so Tesseract can't "correct" a faint digit into an
# unrelated symbol (e.g. misreading a small "6" as "®"). No space in the
# whitelist — spaces are stripped afterwards anyway, and a literal space
# here would get split into a separate command-line argument.
_OCR_WHITELIST = (
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "+-*/=()[]{}.,^<>≤≥√π"
)
_TESSERACT_CONFIG = f"--psm 6 -c tessedit_char_whitelist={_OCR_WHITELIST}"

def ocr_with_exponents(img):
    """Character-level OCR (not word-level) so superscript exponents get
    stitched into the right place in the output. This matters because
    Tesseract's word/line segmentation often puts a raised exponent into a
    DIFFERENT internal "line" than the baseline text it belongs to — a
    word-level pass then emits the exponents in the wrong order entirely
    (e.g. "26y=x-4x" instead of "y=x^2-4x^6"). Sorting individual
    characters by their horizontal position avoids that, and comparing
    each digit's vertical position only against the last ALPHANUMERIC
    baseline (not operators like "=", "-", which have unreliable vertical
    extents of their own) avoids false-positive exponents."""
    img_height = img.shape[0]
    boxes_str = pytesseract.image_to_boxes(img, config=_TESSERACT_CONFIG)

    chars = []
    for line in boxes_str.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        ch, left, bottom, _right, top = parts[0], int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        # image_to_boxes uses a bottom-left origin; flip to top-left so
        # "smaller value = higher up the page", matching normal intuition.
        top_px = img_height - top
        bottom_px = img_height - bottom
        chars.append({"char": ch, "left": left, "bottom": bottom_px, "height": bottom_px - top_px})
    chars.sort(key=lambda c: c["left"])

    result = ""
    prev_char = ""
    prev_bottom, prev_height, have_baseline = 0, 0, False
    for c in chars:
        text = c["char"]
        is_alnum = text.isalnum()

        if is_alnum and text.isdigit() and have_baseline and c["bottom"] < prev_bottom - max(5, prev_height * 0.3):
            result += "^" + text
        elif prev_char and re.match(r"[a-zA-Z]", prev_char) and re.match(r"\d", text):
            result += "*" + text
        else:
            result += text

        prev_char = text
        if is_alnum:
            prev_bottom = c["bottom"]
            prev_height = c["height"]
            have_baseline = True
    return result.replace(" ", "").replace("\n", "")

def clean_for_sympy(text):
    text = re.sub(r"([a-zA-Z])(\d+)", r"\1^\2", text)
    text = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", text)
    return text

def extract_pdf_text(uploaded_file):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    return "".join(page.get_text() for page in doc)

# =====================================================
# FINANCIAL MATHEMATICS — WORD PROBLEM INTERPRETER
# =====================================================
# Grade 12 CAPS Finance, Growth & Decay word problems are almost always
# built from the same handful of ingredients (an amount, a rate, a term,
# a compounding frequency, and sometimes a regular payment). Rather than
# forcing learners to type "P=1000,i=0.1,n=2", we scan the plain-English
# question for these ingredients and pick the right formula automatically.
FINANCE_FREQ_KEYWORDS = [
    ("semi-annually", 2), ("semi annually", 2),
    ("half-yearly", 2), ("half yearly", 2),
    ("quarterly", 4),
    ("monthly", 12),
    ("daily", 365),
    ("annually", 1), ("yearly", 1), ("per annum", 1), ("p.a.", 1), ("p.a", 1),
]

def _find_money_amounts(original_question):
    """Return [(value, char_index, lowercased_context_window)] for every
    Rand amount in the question, in the order they appear. Matched against
    the ORIGINAL (not lowercased) text and anchored on a capital "R" at a
    word boundary — matching case-insensitively on a bare "r" would also
    catch the last letter of ordinary words like "for 4 years" and
    misread them as amounts."""
    amounts = []
    for m in re.finditer(r"\bR\s?([\d][\d,]*\.?\d*)", original_question):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        window = original_question[max(0, m.start() - 25):m.start()].lower()
        amounts.append((value, m.start(), window))
    return amounts

def extract_financial_params(question):
    """Best-effort extraction of P (principal), rate (annual %), term
    (years), compounding frequency, and x (recurring payment) from a
    free-text finance question. Returns a dict of whatever it could find
    — callers must fall back to manual inputs for anything missing."""
    q = question.lower()
    params = {}

    amounts = _find_money_amounts(question)
    payment_triggers = ["save", "deposit", "payment of", "instalment", "installment", "pays", "pay "]
    principal_triggers = ["invest", "principal", "worth", "cost", "loan of", "borrow", "value of"]

    unclassified = []
    for value, _, window in amounts:
        if any(t in window for t in payment_triggers) and "x" not in params:
            params["x"] = value
        elif any(t in window for t in principal_triggers) and "P" not in params:
            params["P"] = value
        else:
            unclassified.append(value)
    # Anything not explicitly flagged as a recurring payment defaults to
    # being the principal/loan amount (the common case: "R5000 is invested...").
    if "P" not in params and unclassified:
        params["P"] = unclassified[0]

    rate_match = re.search(r"([\d]*\.?\d+)\s*%", q)
    if rate_match:
        params["rate"] = float(rate_match.group(1)) / 100

    years_match = re.search(r"([\d]*\.?\d+)\s*year", q)
    if years_match:
        params["years"] = float(years_match.group(1))
    else:
        months_match = re.search(r"([\d]*\.?\d+)\s*month", q)
        if months_match:
            params["years"] = float(months_match.group(1)) / 12

    params["freq"] = 1
    for kw, freq in FINANCE_FREQ_KEYWORDS:
        if kw in q:
            params["freq"] = freq
            break

    if "reducing balance" in q or "reducing-balance" in q or "declining balance" in q or "diminishing" in q:
        params["type"] = "depreciation_reducing"
    elif "straight line" in q or "straight-line" in q or "depreciat" in q:
        params["type"] = "depreciation_straight"
    elif any(w in q for w in ["loan", "repaid", "repayment", "bond", "borrow"]):
        params["type"] = "annuity_present"
    elif "x" in params and any(w in q for w in ["save", "deposit", "future value", "accumulate"]):
        params["type"] = "annuity_future"
    elif "simple interest" in q:
        params["type"] = "simple"
    else:
        params["type"] = "compound"

    return params

def plot_finance_chart(kind, P, i_period, n_period, x=None):
    """Small value-vs-time chart for a finance scenario — a picture makes
    growth/decay and amortisation much more concrete for learners than a
    single final number."""
    periods = np.arange(0, int(round(n_period)) + 1)
    if kind == "compound":
        values = P * (1 + i_period) ** periods
    elif kind == "simple":
        values = P * (1 + periods * i_period)
    elif kind == "depreciation_reducing":
        values = P * (1 - i_period) ** periods
    elif kind == "depreciation_straight":
        values = np.clip(P * (1 - periods * i_period), 0, None)
    elif kind == "annuity_future":
        values = x * ((1 + i_period) ** periods - 1) / i_period
    elif kind == "annuity_present":
        values = [P]
        balance = P
        for _ in periods[1:]:
            balance = balance * (1 + i_period) - x
            values.append(max(balance, 0))
        values = np.array(values)
    else:
        return None

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(periods, values, marker="o", linewidth=2, color="#2563eb")
    ax.fill_between(periods, values, alpha=0.1, color="#2563eb")
    ax.set_xlabel("Period")
    ax.set_ylabel("Value (R)")
    ax.set_title("Value over time")
    ax.grid(True, linestyle="--", alpha=0.5)
    return fig

# =====================================================
# PROBABILITY — WORD PROBLEM INTERPRETER
# =====================================================
def _dice_favourable(desc, faces=6):
    """Given a phrase like 'greater than 4', 'even', 'a prime number',
    return the set of face values on a `faces`-sided die that satisfy it."""
    desc = desc.lower()
    outcomes = set(range(1, faces + 1))
    m = re.search(r"greater than (\d+)", desc)
    if m:
        return {o for o in outcomes if o > int(m.group(1))}
    m = re.search(r"at least (\d+)", desc)
    if m:
        return {o for o in outcomes if o >= int(m.group(1))}
    m = re.search(r"less than (\d+)", desc)
    if m:
        return {o for o in outcomes if o < int(m.group(1))}
    m = re.search(r"at most (\d+)", desc)
    if m:
        return {o for o in outcomes if o <= int(m.group(1))}
    if "even" in desc:
        return {o for o in outcomes if o % 2 == 0}
    if "odd" in desc:
        return {o for o in outcomes if o % 2 == 1}
    if "prime" in desc:
        return {o for o in outcomes if o in (2, 3, 5, 7, 11, 13) and o <= faces}
    m = re.search(r"\b(\d+)\b", desc)
    if m and int(m.group(1)) in outcomes:
        return {int(m.group(1))}
    return outcomes

BAG_ITEM_NOUNS = [
    "balls", "marbles", "counters", "sweets", "cards", "discs", "tiles",
    "pens", "chips", "apples", "oranges", "tickets", "sweets", "beads",
]

def parse_bag_of_items(q):
    """Detect 'A bag contains 5 red and 3 blue balls...' style questions.
    Returns (counts_by_label dict, target_label) or (None, None). The list
    of colours/labels usually only has the noun ("balls") once, at the very
    end (e.g. "5 red and 3 blue balls"), so we first locate that noun and
    then pull every "<number> <label>" pair out of the list before it."""
    list_pattern = (
        r"((?:\d+\s+[a-zA-Z]+\s*,?\s*(?:and)?\s*)+)(?:" + "|".join(BAG_ITEM_NOUNS) + r")"
    )
    list_match = re.search(list_pattern, q)
    if not list_match:
        return None, None
    matches = re.findall(r"(\d+)\s+([a-zA-Z]+)", list_match.group(1))
    if not matches:
        return None, None
    counts = {label: int(n) for n, label in matches}

    target = None
    m = re.search(r"(?:drawing|selecting|choosing|picking|getting|obtaining)\s+(?:a|an)?\s*([a-zA-Z]+)", q)
    if m and m.group(1) in counts:
        target = m.group(1)
    if target is None:
        m = re.search(r"\bis\s+([a-zA-Z]+)\b", q)
        if m and m.group(1) in counts:
            target = m.group(1)
    if target is None and counts:
        target = list(counts.keys())[-1]
    return counts, target

def interpret_probability_text(question):
    """Best-effort natural-language interpretation of a Grade 12 probability
    question. Returns a dict describing how to solve + display it, or None
    if the text isn't recognised (caller falls back to manual entry)."""
    q = question.lower().strip()

    # ---- 1. Symbolic P(A)/P(B) rules (mutually exclusive / independent / complement) ----
    pa_match = re.search(r"p\(a\)\s*=\s*(\d+(?:\.\d+)?)", q)
    pb_match = re.search(r"p\(b\)\s*=\s*(\d+(?:\.\d+)?)", q)
    if pa_match and pb_match:
        pa, pb = float(pa_match.group(1)), float(pb_match.group(1))
        p_and_match = re.search(r"p\(a\s*(?:and|∩)\s*b\)\s*=\s*(\d+(?:\.\d+)?)", q)
        mutually_exclusive = "mutually exclusive" in q
        independent = "independent" in q

        wants_or = bool(re.search(r"p\(a\s*(?:or|∪)\s*b\)", q)) or "or b" in q
        wants_and = bool(re.search(r"find\s+p\(a\s*(?:and|∩)\s*b\)", q))
        wants_not_a = bool(re.search(r"p\(not\s*a\)|p\(a'\)|complement", q))

        if wants_not_a:
            return {"kind": "symbolic", "formula": r"P(A')=1-P(A)",
                    "steps": [rf"P(A')=1-{pa}"], "answer": 1 - pa}
        if wants_and and independent:
            return {"kind": "symbolic", "formula": r"P(A \text{ and } B)=P(A)\times P(B)",
                    "steps": [rf"P(A\text{{ and }}B)={pa}\times{pb}"], "answer": pa * pb}
        if wants_or and mutually_exclusive:
            return {"kind": "symbolic", "formula": r"P(A \text{ or } B)=P(A)+P(B)",
                    "steps": [rf"P(A\text{{ or }}B)={pa}+{pb}"], "answer": pa + pb}
        if wants_or and p_and_match:
            p_and = float(p_and_match.group(1))
            return {"kind": "symbolic",
                    "formula": r"P(A \text{ or } B)=P(A)+P(B)-P(A \text{ and } B)",
                    "steps": [rf"P(A\text{{ or }}B)={pa}+{pb}-{p_and}"], "answer": pa + pb - p_and}
        if wants_or:
            return {"kind": "symbolic", "formula": r"P(A \text{ or } B)=P(A)+P(B)",
                    "steps": [rf"P(A\text{{ or }}B)={pa}+{pb}"], "answer": pa + pb}

    # ---- 2. Bag / box of labelled items ----
    counts, target = parse_bag_of_items(q)
    if counts and target:
        total = sum(counts.values())
        return {
            "kind": "bag", "counts": counts, "target": target,
            "favourable": counts[target], "total": total,
            "answer": counts[target] / total,
        }

    # ---- 3. Combined two-stage independent events (die & coin, coin & coin, die & die) ----
    has_die = "die" in q or "dice" in q
    has_coin = "coin" in q

    if has_die and has_coin and (" and " in q):
        clauses = q.split(" and ")
        die_fav = _dice_favourable(clauses[-2] if len(clauses) > 1 else q)
        coin_target = "head" if "head" in q else ("tail" if "tail" in q else None)
        p_die = len(die_fav) / 6
        p_coin = 0.5 if coin_target else 1.0
        answer = p_die * p_coin
        return {
            "kind": "tree", "stages": [("Die", 6, len(die_fav)), ("Coin", 2, 1 if coin_target else 2)],
            "steps": [
                rf"P(\text{{die event}})=\frac{{{len(die_fav)}}}{{6}}",
                rf"P(\text{{coin event}})=\frac{{1}}{{2}}" if coin_target else r"P(\text{coin event})=1",
                rf"P(\text{{die}}\;\text{{and}}\;\text{{coin}})=\frac{{{len(die_fav)}}}{{6}}\times\frac12",
            ],
            "answer": answer,
        }

    # ---- 4. Single die ----
    if has_die:
        fav = _dice_favourable(q)
        return {
            "kind": "die", "favourable_set": fav, "faces": 6,
            "answer": len(fav) / 6,
        }

    # ---- 5. Single/double coin ----
    if has_coin:
        two_coins = bool(re.search(r"two coins|2 coins|both coins", q))
        if two_coins:
            outcomes = ["HH", "HT", "TH", "TT"]
            if "at least one head" in q:
                fav = [o for o in outcomes if "H" in o]
            elif "at least one tail" in q:
                fav = [o for o in outcomes if "T" in o]
            elif "two heads" in q or "both heads" in q:
                fav = ["HH"]
            elif "two tails" in q or "both tails" in q:
                fav = ["TT"]
            else:
                fav = outcomes
            return {"kind": "coins", "outcomes": outcomes, "favourable": fav,
                    "answer": len(fav) / len(outcomes)}
        else:
            return {"kind": "coin", "answer": 0.5}

    return None

def draw_tree_diagram(stage_labels):
    """Draw a simple two-stage probability tree diagram, e.g. for
    [("Die", ["1-6 outcomes"]), ("Coin", ["H", "T"])]."""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.axis("off")
    ax.plot(0, 0.5, "ko")
    stage1_name, stage1_opts = stage_labels[0]
    stage2_name, stage2_opts = stage_labels[1]
    n1 = len(stage1_opts)
    y1_positions = np.linspace(0.1, 0.9, n1)
    for y1, opt1 in zip(y1_positions, stage1_opts):
        ax.plot([0, 1], [0.5, y1], "b-", linewidth=1)
        ax.text(1.05, y1, str(opt1), va="center", fontsize=9)
        n2 = len(stage2_opts)
        y2_positions = np.linspace(y1 - 0.08, y1 + 0.08, n2) if n2 > 1 else [y1]
        for y2, opt2 in zip(y2_positions, stage2_opts):
            ax.plot([1.3, 2], [y1, y2], "g-", linewidth=1)
            ax.text(2.05, y2, str(opt2), va="center", fontsize=8)
    ax.set_xlim(-0.2, 3)
    ax.set_ylim(0, 1)
    ax.set_title(f"{stage1_name} → {stage2_name}", fontsize=10)
    return fig

# =====================================================
# EUCLIDEAN GEOMETRY — CIRCLE THEOREMS
# =====================================================
def solve_euclidean_geometry(question):
    """Recognise the handful of Grade 12 circle-theorem question shapes and
    apply the matching theorem. Returns None if nothing matches (caller
    shows the theorem reference instead)."""
    q = question.lower()

    if "centre" in q and "circumference" in q:
        m_centre = re.search(r"centre\D{0,15}?(\d+(?:\.\d+)?)", q)
        m_circ = re.search(r"circumference\D{0,15}?(\d+(?:\.\d+)?)", q)
        if m_centre:
            v = float(m_centre.group(1))
            return {"kind": "centre_circumference", "given": "centre", "value": v, "answer": v / 2}
        if m_circ:
            v = float(m_circ.group(1))
            return {"kind": "centre_circumference", "given": "circumference", "value": v, "answer": v * 2}

    if "cyclic quadrilateral" in q:
        m = re.search(r"(\d+(?:\.\d+)?)", q)
        if m:
            v = float(m.group(1))
            return {"kind": "cyclic_quad", "value": v, "answer": 180 - v}

    if "tangent" in q and ("chord" in q or "alternate segment" in q):
        m = re.search(r"(\d+(?:\.\d+)?)", q)
        if m:
            v = float(m.group(1))
            return {"kind": "tan_chord", "value": v, "answer": v}

    return None

def draw_euclidean_diagram(kind):
    """Illustrative (not-to-scale) circle-theorem schematic matching the
    detected theorem type."""
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    circle = plt.Circle((0, 0), 1, fill=False, color="#2563eb", linewidth=2)
    ax.add_patch(circle)
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-1.4, 1.4)
    ax.set_aspect("equal")
    ax.axis("off")

    if kind == "centre_circumference":
        O = (0, 0)
        A = (np.cos(np.radians(200)), np.sin(np.radians(200)))
        B = (np.cos(np.radians(-20)), np.sin(np.radians(-20)))
        C = (np.cos(np.radians(90)), np.sin(np.radians(90)))
        ax.plot(*O, "ko"); ax.text(0.05, 0.05, "O")
        for P, label in [(A, "A"), (B, "B"), (C, "C")]:
            ax.plot(*P, "ko")
            ax.text(P[0] * 1.1, P[1] * 1.1, label, ha="center")
        ax.plot([O[0], A[0]], [O[1], A[1]], "b-")
        ax.plot([O[0], B[0]], [O[1], B[1]], "b-")
        ax.plot([C[0], A[0]], [C[1], A[1]], "g-")
        ax.plot([C[0], B[0]], [C[1], B[1]], "g-")
        ax.set_title("Angle at centre = 2 × angle at circumference", fontsize=9)

    elif kind == "cyclic_quad":
        pts = {name: (np.cos(np.radians(a)), np.sin(np.radians(a)))
               for name, a in [("A", 100), ("B", 20), ("C", -80), ("D", 190)]}
        order = ["A", "B", "C", "D"]
        for i in range(4):
            p1, p2 = pts[order[i]], pts[order[(i + 1) % 4]]
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], "g-")
        for name, p in pts.items():
            ax.plot(*p, "ko")
            ax.text(p[0] * 1.1, p[1] * 1.1, name, ha="center")
        ax.set_title("Cyclic quadrilateral: opposite angles are supplementary", fontsize=9)

    else:  # tan_chord
        T = (np.cos(np.radians(-90)), np.sin(np.radians(-90)))
        P = (np.cos(np.radians(140)), np.sin(np.radians(140)))
        tangent_dir = np.array([-np.sin(np.radians(-90)), np.cos(np.radians(-90))])
        t1 = np.array(T) - 0.8 * tangent_dir
        t2 = np.array(T) + 0.8 * tangent_dir
        ax.plot([t1[0], t2[0]], [t1[1], t2[1]], "r-", label="Tangent")
        ax.plot([T[0], P[0]], [T[1], P[1]], "g-", label="Chord")
        ax.plot(*T, "ko"); ax.text(T[0], T[1] - 0.12, "T", ha="center")
        ax.plot(*P, "ko"); ax.text(P[0] * 1.1, P[1] * 1.1, "P", ha="center")
        ax.set_title("Tan-chord: angle = angle in alternate segment", fontsize=9)

    return fig

# =====================================================
# SESSION STATE
# =====================================================
if "learner" not in st.session_state:
    st.session_state.learner = {
        "name": "", "solved": 0, "Marks": 0,
        "solved_set": set(), "topic_counts": {},
    }

if "copied_text" not in st.session_state:
    st.session_state.copied_text = ""

def _extract_numbers(s):
    """Pull every number (incl. negatives/decimals) out of a string,
    ignoring LaTeX/units around it — used to loosely grade practice
    answers without needing full symbolic equivalence checking."""
    return sorted(round(float(n), 4) for n in re.findall(r"-?\d+\.?\d*", s))

def check_practice_answer(user_answer, expected_latex):
    """Best-effort grading: compares the multiset of numbers in the
    learner's typed answer against the expected answer. Returns True/False,
    or None if the expected answer has no numbers to compare against."""
    if not user_answer.strip():
        return None
    expected_nums = _extract_numbers(expected_latex)
    if not expected_nums:
        return None
    return _extract_numbers(user_answer) == expected_nums

# =====================================================
# PRACTICE QUESTIONS (FULL – PAPER 1 & 2)
# =====================================================
practice_data = {
"Paper 1": {
"Algebra": [
{"question": r"\text{Solve for } x:\; x^2 - 5x + 6 = 0",
 "hint": r"\text{Try to factorise into two brackets that multiply to give } 6 \text{ and add to give } {-5}.",
 "solution_steps":[
 {"explain": "Factorise the trinomial into two brackets that multiply out to give the original expression.", "latex": r"(x-2)(x-3)=0 \quad (1 Mark)"},
 {"explain": "Apply the zero product law: if two factors multiply to give zero, at least one of them must itself be zero.", "latex": r"x-2=0 \;\text{or}\; x-3=0 \quad (1 Mark)"},
 {"explain": "Solve each of the two simple linear equations for x.", "latex": r"x=2 \;\text{or}\; x=3 \quad (1 Mark)"},
 ],
 "final_answer": r"x=2 \;\text{or}\; x=3",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Solve for } x:\; 3x^2=12",
 "hint": r"\text{Divide both sides by 3 first, then take the square root of both sides.}",
 "solution_steps":[
 {"explain": "Divide both sides by 3 to isolate x².", "latex": r"x^2=4 \quad (1 Mark)"},
 {"explain": "Take the square root of both sides — remember a square root always gives BOTH a positive and a negative answer.", "latex": r"x=\pm2 \quad (2 Marks)"},
 ],
 "final_answer": r"x=\pm2",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Solve for } x:\; x^2 - 2x - 4 = 0 \;(\text{correct to 2 decimal places})",
 "hint": r"\text{This does not factorise nicely — use the quadratic formula.}",
 "solution_steps":[
 {"explain": "Identify the coefficients a, b and c so they can be substituted into the quadratic formula.", "latex": r"a=1,\;b=-2,\;c=-4 \quad (1 Mark)"},
 {"explain": "Substitute a, b and c into the quadratic formula.", "latex": r"x=\frac{-(-2)\pm\sqrt{(-2)^2-4(1)(-4)}}{2(1)} \quad (2 Marks)"},
 {"explain": "Simplify the numbers inside and outside the square root.", "latex": r"x=\frac{2\pm\sqrt{20}}{2} \quad (1 Mark)"},
 {"explain": "Use a calculator to evaluate both the + and − roots, rounding each to 2 decimal places.", "latex": r"x=3.24 \;\text{or}\; x=-1.24 \quad (2 Marks)"},
 ],
 "final_answer": r"x=3.24 \;\text{or}\; x=-1.24",
 "Marks":6,"difficulty":"Medium"},
{"question": r"\text{Solve for } x:\; 2x^2 + 3x - 5 \le 0",
 "hint": r"\text{Find the critical values first, then decide which region satisfies the inequality using a number line.}",
 "solution_steps":[
 {"explain": "Factorise the quadratic expression, exactly as you would for an equation.", "latex": r"(2x+5)(x-1)\le 0 \quad (2 Marks)"},
 {"explain": "Set each factor equal to zero to find the critical values — the points where the expression changes sign.", "latex": r"x=-\frac{5}{2} \;\text{or}\; x=1 \quad (1 Mark)"},
 {"explain": "Since the parabola opens upward (positive x² coefficient), it is ≤0 BETWEEN the two critical values.", "latex": r"-\frac{5}{2}\le x\le 1 \quad (2 Marks)"},
 ],
 "final_answer": r"-\frac{5}{2}\le x\le 1",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{Solve simultaneously for } x \text{ and } y:\; x+y=10,\; 2x-y=2",
 "hint": r"\text{Add the two equations together to eliminate } y.",
 "solution_steps":[
 {"explain": "Write down the first equation and label it (1) so it can be referred back to.", "latex": r"x+y=10 \quad \text{...(1)}"},
 {"explain": "Write down the second equation and label it (2).", "latex": r"2x-y=2 \quad \text{...(2)}"},
 {"explain": "Add equation (1) and (2) together — the +y and −y terms cancel out, leaving only x.", "latex": r"\text{Adding (1) and (2)}: 3x=12 \quad (2 Marks)"},
 {"explain": "Divide both sides by 3 to solve for x.", "latex": r"x=4 \quad (1 Mark)"},
 {"explain": "Substitute x=4 back into equation (1) to solve for y.", "latex": r"y=10-4=6 \quad (2 Marks)"},
 ],
 "final_answer": r"x=4,\; y=6",
 "Marks":5,"difficulty":"Medium"},
],
"Sequences": [
{"question": r"\text{Find the 10th term of } 3,7,11,\dots",
 "hint": r"\text{This is arithmetic — find the common difference } d \text{ first.}",
 "solution_steps":[
 {"explain": "Identify the first term a, and the common difference d (each term minus the one before it).", "latex": r"a=3,\; d=4 \quad (1 Mark)"},
 {"explain": "Write down the general term formula for an arithmetic sequence.", "latex": r"T_n=a+(n-1)d \quad (1 Mark)"},
 {"explain": "Substitute n=10, a and d into the formula and simplify.", "latex": r"T_{10}=39 \quad (1 Mark)"},
 ],
 "final_answer": r"39",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the 8th term of the geometric sequence } 2,6,18,\dots",
 "hint": r"\text{Find the common ratio } r=\frac{T_2}{T_1} \text{ then use } T_n=ar^{n-1}.",
 "solution_steps":[
 {"explain": "Identify the first term a, and the common ratio r (each term divided by the one before it).", "latex": r"a=2,\; r=3 \quad (1 Mark)"},
 {"explain": "Write down the general term formula for a geometric sequence.", "latex": r"T_n=ar^{n-1} \quad (1 Mark)"},
 {"explain": "Substitute n=8, a and r into the formula and simplify.", "latex": r"T_8=2(3)^7=4374 \quad (2 Marks)"},
 ],
 "final_answer": r"4374",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Calculate the sum of the first 15 terms of } 5,9,13,\dots",
 "hint": r"\text{Use } S_n=\frac{n}{2}[2a+(n-1)d].",
 "solution_steps":[
 {"explain": "Identify a, d, and the number of terms n we're summing.", "latex": r"a=5,\; d=4,\; n=15 \quad (1 Mark)"},
 {"explain": "Substitute these values into the arithmetic series sum formula.", "latex": r"S_{15}=\frac{15}{2}[2(5)+(14)(4)] \quad (2 Marks)"},
 {"explain": "Simplify the bracket first, then multiply to get the final total.", "latex": r"S_{15}=\frac{15}{2}(66)=495 \quad (2 Marks)"},
 ],
 "final_answer": r"495",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{Determine the sum to infinity of } 8,4,2,1,\dots",
 "hint": r"\text{Since } |r|<1 \text{, use } S_\infty=\frac{a}{1-r}.",
 "solution_steps":[
 {"explain": "Identify a and r. Since |r|<1, the terms shrink towards zero and a sum to infinity exists.", "latex": r"a=8,\; r=\frac12 \quad (1 Mark)"},
 {"explain": "Substitute a and r into the sum-to-infinity formula.", "latex": r"S_\infty=\frac{a}{1-r}=\frac{8}{1-\frac12} \quad (2 Marks)"},
 {"explain": "Simplify the fraction to get the final answer.", "latex": r"S_\infty=16 \quad (1 Mark)"},
 ],
 "final_answer": r"16",
 "Marks":4,"difficulty":"Medium"},
],
"Financial Mathematics": [
{"question": r"\text{Find } A \text{ if } P=1000,\; i=10\%,\; n=2 \text{ (compound interest)}",
 "hint": r"\text{Use the compound growth formula } A=P(1+i)^n.",
 "solution_steps":[
 {"explain": "Write down the compound growth formula (interest earns interest each period).", "latex": r"A=P(1+i)^n \quad (1 Mark)"},
 {"explain": "Substitute P, i (as a decimal) and n, then evaluate.", "latex": r"A=1000(1.1)^2=1210 \quad (2 Marks)"},
 ],
 "final_answer": r"R1210",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{R5000 is invested at 8\% p.a. simple interest for 3 years. Find the accumulated amount.}",
 "hint": r"\text{Simple interest uses } A=P(1+ni), \text{ not the power formula.}",
 "solution_steps":[
 {"explain": "Write down the simple interest formula — unlike compound interest, each year's interest is calculated only on the ORIGINAL principal, not on previous interest.", "latex": r"A=P(1+ni) \quad (1 Mark)"},
 {"explain": "Substitute P=5000, n=3 years and i=0.08.", "latex": r"A=5000(1+3\times0.08) \quad (2 Marks)"},
 {"explain": "Simplify inside the brackets, then multiply out.", "latex": r"A=5000(1.24)=6200 \quad (1 Mark)"},
 ],
 "final_answer": r"R6200",
 "Marks":4,"difficulty":"Easy"},
{"question": r"\text{A car costing R240 000 depreciates on the reducing-balance method at 12\% p.a. Find its value after 5 years.}",
 "hint": r"\text{Reducing balance depreciation uses } A=P(1-i)^n.",
 "solution_steps":[
 {"explain": "Write down the reducing-balance depreciation formula — the value drops by the same PERCENTAGE each year, so it's a decay version of the compound growth formula (minus instead of plus).", "latex": r"A=P(1-i)^n \quad (1 Mark)"},
 {"explain": "Substitute P=240000, i=0.12 and n=5.", "latex": r"A=240000(1-0.12)^5 \quad (2 Marks)"},
 {"explain": "Simplify inside the brackets first, then raise to the power of 5 and multiply.", "latex": r"A=240000(0.88)^5\approx126934.61 \quad (2 Marks)"},
 ],
 "final_answer": r"\approx R126\,934.61",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{Thabo saves R800 at the end of every month into an account earning 9\% p.a. compounded monthly for 4 years. Find the future value.}",
 "hint": r"\text{This is an ordinary annuity — use } F=\frac{x[(1+i)^n-1]}{i} \text{ with monthly } i \text{ and } n.",
 "solution_steps":[
 {"explain": "Since deposits are monthly, convert the annual rate and term into MONTHLY units: divide the rate by 12, and multiply the years by 12.", "latex": r"x=800,\; i=\frac{0.09}{12}=0.0075,\; n=4\times12=48 \quad (2 Marks)"},
 {"explain": "Write down the future value annuity formula for a series of equal regular deposits.", "latex": r"F=\frac{x[(1+i)^n-1]}{i} \quad (1 Mark)"},
 {"explain": "Substitute x, i and n, then evaluate with a calculator.", "latex": r"F=\frac{800[(1.0075)^{48}-1]}{0.0075}\approx45699.94 \quad (3 Marks)"},
 ],
 "final_answer": r"\approx R45\,699.94",
 "Marks":6,"difficulty":"Hard"},
],
"Calculus": [
{"question": r"\text{Differentiate } f(x)=3x^2",
 "hint": r"\text{Use the power rule: bring the exponent down and reduce it by 1.}",
 "solution_steps":[
 {"explain": "Use the power rule: multiply the coefficient by the exponent, then reduce the exponent by 1.", "latex": r"\frac{d}{dx}(3x^2)=6x \quad (3 Marks)"},
 ],
 "final_answer": r"6x",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Determine } f'(x) \text{ if } f(x)=2x^3-5x^2+4",
 "hint": r"\text{Differentiate each term separately using the power rule.}",
 "solution_steps":[
 {"explain": "Differentiate each term one at a time using the power rule; the constant term (4) disappears since the derivative of a constant is 0.", "latex": r"f'(x)=6x^2-10x \quad (3 Marks)"},
 ],
 "final_answer": r"f'(x)=6x^2-10x",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Use first principles to find } f'(x) \text{ if } f(x)=x^2",
 "hint": r"\text{Use } f'(x)=\lim_{h\to0}\frac{f(x+h)-f(x)}{h}.",
 "solution_steps":[
 {"explain": "Write down the first-principles definition of the derivative, and substitute f(x+h) and f(x).", "latex": r"f'(x)=\lim_{h\to0}\frac{(x+h)^2-x^2}{h} \quad (2 Marks)"},
 {"explain": "Expand (x+h)² and simplify the numerator — the x² terms cancel out.", "latex": r"=\lim_{h\to0}\frac{2xh+h^2}{h} \quad (2 Marks)"},
 {"explain": "Divide every term in the numerator by h, then let h→0 (h simply disappears).", "latex": r"=\lim_{h\to0}(2x+h)=2x \quad (2 Marks)"},
 ],
 "final_answer": r"f'(x)=2x",
 "Marks":6,"difficulty":"Medium"},
{"question": r"\text{Find the } x\text{-value(s) where } f(x)=x^3-3x \text{ has a turning point.}",
 "hint": r"\text{Turning points occur where } f'(x)=0.",
 "solution_steps":[
 {"explain": "Differentiate f(x) using the power rule.", "latex": r"f'(x)=3x^2-3 \quad (2 Marks)"},
 {"explain": "Turning points occur where the gradient is zero, so set f'(x)=0 and solve for x².", "latex": r"3x^2-3=0 \Rightarrow x^2=1 \quad (2 Marks)"},
 {"explain": "Take the square root of both sides — remember both the positive and negative root.", "latex": r"x=1 \;\text{or}\; x=-1 \quad (2 Marks)"},
 ],
 "final_answer": r"x=1 \;\text{or}\; x=-1",
 "Marks":6,"difficulty":"Medium"},
],
"Functions & Graphs": [
{"question": r"\text{Determine the } y\text{-intercept of } f(x)=x^2-4x+3",
 "hint": r"\text{Substitute } x=0 \text{ into the equation.}",
 "solution_steps":[
 {"explain": "The y-intercept is where the graph crosses the y-axis, i.e. where x=0 — substitute and simplify.", "latex": r"f(0)=0^2-4(0)+3=3 \quad (2 Marks)"},
 ],
 "final_answer": r"(0,3)",
 "Marks":2,"difficulty":"Easy"},
{"question": r"\text{Determine the } x\text{-intercepts of } f(x)=x^2-4x+3",
 "hint": r"\text{Set } f(x)=0 \text{ and factorise.}",
 "solution_steps":[
 {"explain": "The x-intercepts are where the graph crosses the x-axis, i.e. where f(x)=0 — set it to zero and factorise.", "latex": r"(x-1)(x-3)=0 \quad (2 Marks)"},
 {"explain": "Apply the zero product law to solve for x.", "latex": r"x=1 \;\text{or}\; x=3 \quad (1 Mark)"},
 ],
 "final_answer": r"(1,0) \;\text{and}\;(3,0)",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the equations of the asymptotes of } f(x)=\frac{2}{x-1}+3",
 "hint": r"\text{The asymptotes come directly from the values that make the denominator zero, and the vertical shift.}",
 "solution_steps":[
 {"explain": "The vertical asymptote occurs where the denominator of the fraction equals zero (division by zero is undefined).", "latex": r"\text{Vertical asymptote: } x=1 \quad (2 Marks)"},
 {"explain": "As x gets very large, 2/(x-1) approaches 0, so f(x) approaches the constant added outside the fraction.", "latex": r"\text{Horizontal asymptote: } y=3 \quad (2 Marks)"},
 ],
 "final_answer": r"x=1,\; y=3",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Determine the coordinates of the turning point of } f(x)=x^2-2x-3",
 "hint": r"\text{Use the axis of symmetry } x=-\frac{b}{2a}, \text{ then substitute back to find } y.",
 "solution_steps":[
 {"explain": "For a parabola, the turning point lies on the axis of symmetry x=-b/(2a) — substitute a and b.", "latex": r"x=-\frac{-2}{2(1)}=1 \quad (2 Marks)"},
 {"explain": "Substitute this x-value back into f(x) to find the corresponding y-coordinate.", "latex": r"f(1)=1-2-3=-4 \quad (2 Marks)"},
 ],
 "final_answer": r"(1,-4)",
 "Marks":4,"difficulty":"Medium"},
]
},
"Paper 2": {
"Analytical Geometry": [
{"question": r"\text{Find the distance between } A(1,2), B(4,6)",
 "hint": r"\text{Use the distance formula } d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}.",
 "solution_steps":[
 {"explain": "Substitute the coordinates of A and B into the distance formula (a consequence of Pythagoras' theorem) and simplify.", "latex": r"d=\sqrt{(4-1)^2+(6-2)^2}=5 \quad (3 Marks)"},
 ],
 "final_answer": r"5",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Determine the midpoint of } A(-2,3) \text{ and } B(6,-1)",
 "hint": r"\text{Use } M=\left(\frac{x_1+x_2}{2},\frac{y_1+y_2}{2}\right).",
 "solution_steps":[
 {"explain": "Substitute the coordinates into the midpoint formula: average the x-values and average the y-values.", "latex": r"M=\left(\frac{-2+6}{2},\frac{3+(-1)}{2}\right) \quad (2 Marks)"},
 {"explain": "Simplify each fraction.", "latex": r"M=(2,1) \quad (1 Mark)"},
 ],
 "final_answer": r"(2,1)",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the gradient of the line through } A(1,1) \text{ and } B(5,9)",
 "hint": r"\text{Use } m=\frac{y_2-y_1}{x_2-x_1}.",
 "solution_steps":[
 {"explain": "Substitute the coordinates into the gradient formula: the change in y divided by the change in x.", "latex": r"m=\frac{9-1}{5-1}=\frac{8}{4}=2 \quad (3 Marks)"},
 ],
 "final_answer": r"m=2",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Determine the equation of the line through } A(2,3) \text{ with gradient } 4",
 "hint": r"\text{Use } y-y_1=m(x-x_1).",
 "solution_steps":[
 {"explain": "Substitute the given point and gradient into the point-gradient form of a straight line.", "latex": r"y-3=4(x-2) \quad (2 Marks)"},
 {"explain": "Expand the brackets and simplify to the standard y=mx+c form.", "latex": r"y=4x-5 \quad (2 Marks)"},
 ],
 "final_answer": r"y=4x-5",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Determine the equation of the circle with centre } (0,0) \text{ and radius } 5",
 "hint": r"\text{Use } (x-a)^2+(y-b)^2=r^2 \text{ with centre } (a,b).",
 "solution_steps":[
 {"explain": "Substitute the centre (a,b) and radius r into the standard equation of a circle.", "latex": r"(x-0)^2+(y-0)^2=5^2 \quad (2 Marks)"},
 ],
 "final_answer": r"x^2+y^2=25",
 "Marks":2,"difficulty":"Easy"},
],
"Trigonometry": [
{"question": r"\text{Solve } \sin x=\frac12,\; 0^\circ\le x\le360^\circ",
 "hint": r"\text{Sine is positive in the 1st and 2nd quadrants.}",
 "solution_steps":[
 {"explain": "Use a calculator/known value to find the reference angle (30°), then apply the CAST rule: sine is positive in the 1st quadrant (30°) and the 2nd quadrant (180°−30°=150°).", "latex": r"x=30^\circ,\;150^\circ \quad (3 Marks)"},
 ],
 "final_answer": r"30^\circ,\;150^\circ",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Solve for } x:\; \cos x=-\frac{\sqrt3}{2},\; 0^\circ\le x\le360^\circ",
 "hint": r"\text{Cosine is negative in the 2nd and 3rd quadrants.}",
 "solution_steps":[
 {"explain": "Ignore the negative sign for now to find the reference (acute) angle.", "latex": r"\text{Reference angle}=30^\circ \quad (1 Mark)"},
 {"explain": "Cosine is negative in the 2nd quadrant, so use 180°−reference angle.", "latex": r"x=180^\circ-30^\circ=150^\circ \quad (1 Mark)"},
 {"explain": "Cosine is also negative in the 3rd quadrant, so use 180°+reference angle.", "latex": r"x=180^\circ+30^\circ=210^\circ \quad (1 Mark)"},
 ],
 "final_answer": r"150^\circ,\;210^\circ",
 "Marks":3,"difficulty":"Medium"},
{"question": r"\text{In } \triangle ABC,\; a=7,\;b=9,\; C=40^\circ. \text{ Find } c \text{ using the cosine rule.}",
 "hint": r"\text{Use } c^2=a^2+b^2-2ab\cos C.",
 "solution_steps":[
 {"explain": "Substitute the two known sides and the angle between them into the cosine rule.", "latex": r"c^2=7^2+9^2-2(7)(9)\cos40^\circ \quad (2 Marks)"},
 {"explain": "Evaluate the right-hand side with a calculator.", "latex": r"c^2\approx 33.48 \quad (1 Mark)"},
 {"explain": "Take the square root of both sides to find c.", "latex": r"c\approx5.79 \quad (1 Mark)"},
 ],
 "final_answer": r"c\approx5.79",
 "Marks":4,"difficulty":"Medium"},
{"question": r"\text{Simplify: } \frac{\sin^2\theta}{1-\cos^2\theta}",
 "hint": r"\text{Use the identity } \sin^2\theta+\cos^2\theta=1.",
 "solution_steps":[
 {"explain": "Use the Pythagorean identity sin²θ+cos²θ=1, rearranged to replace the denominator.", "latex": r"1-\cos^2\theta=\sin^2\theta \quad (2 Marks)"},
 {"explain": "The numerator and denominator are now identical, so they cancel to 1.", "latex": r"\frac{\sin^2\theta}{\sin^2\theta}=1 \quad (2 Marks)"},
 ],
 "final_answer": r"1",
 "Marks":4,"difficulty":"Medium"},
],
"Statistics & Probability": [
{"question": r"\text{Find the mean of } 2,4,6,8",
 "hint": r"\text{Add all values and divide by how many there are.}",
 "solution_steps":[
 {"explain": "Add up all the values, then divide by how many values there are (n=4).", "latex": r"\bar{x}=\frac{20}{4}=5 \quad (3 Marks)"},
 ],
 "final_answer": r"5",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Find the median of } 3,7,9,12,15",
 "hint": r"\text{Arrange the data set — it's already sorted — and pick the middle value.}",
 "solution_steps":[
 {"explain": "The data is already sorted. With 5 (an odd number of) values, the median is simply the middle one — the 3rd value.", "latex": r"\text{Middle value of 5 sorted numbers is the 3rd value} \quad (2 Marks)"},
 ],
 "final_answer": r"9",
 "Marks":2,"difficulty":"Easy"},
{"question": r"\text{Find the standard deviation of } 2,4,6,8 \;(\text{population})",
 "hint": r"\text{Use } \sigma=\sqrt{\frac{\sum(x-\bar x)^2}{n}}.",
 "solution_steps":[
 {"explain": "First calculate the mean, since it's needed for every deviation below.", "latex": r"\bar{x}=5 \quad (1 Mark)"},
 {"explain": "Find how far each value is from the mean, square each deviation (so negatives don't cancel positives), and add them all up.", "latex": r"\sum(x-\bar{x})^2=(2-5)^2+(4-5)^2+(6-5)^2+(8-5)^2=20 \quad (2 Marks)"},
 {"explain": "Divide by n (the number of values) and take the square root to undo the earlier squaring.", "latex": r"\sigma=\sqrt{\frac{20}{4}}=\sqrt5\approx2.24 \quad (2 Marks)"},
 ],
 "final_answer": r"\approx2.24",
 "Marks":5,"difficulty":"Medium"},
{"question": r"\text{A die is rolled once. Find the probability of getting a number greater than 4.}",
 "hint": r"\text{List the favourable outcomes out of the 6 possible outcomes.}",
 "solution_steps":[
 {"explain": "List every outcome on the die that satisfies \"greater than 4\".", "latex": r"\text{Favourable outcomes: } \{5,6\} \quad (1 Mark)"},
 {"explain": "Divide the number of favourable outcomes by the total number of possible outcomes (6 faces), and simplify.", "latex": r"P(E)=\frac{2}{6}=\frac13 \quad (2 Marks)"},
 ],
 "final_answer": r"\frac13",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{Events A and B are mutually exclusive with } P(A)=0.3 \text{ and } P(B)=0.4. \text{ Find } P(A \text{ or } B).",
 "hint": r"\text{For mutually exclusive events, } P(A\text{ or }B)=P(A)+P(B).",
 "solution_steps":[
 {"explain": "Since A and B are mutually exclusive (they can never both happen at once), there's no overlap to subtract — simply add the two probabilities.", "latex": r"P(A\text{ or }B)=P(A)+P(B) \quad (2 Marks)"},
 {"explain": "Substitute the given probabilities and add.", "latex": r"P(A\text{ or }B)=0.3+0.4=0.7 \quad (1 Mark)"},
 ],
 "final_answer": r"0.7",
 "Marks":3,"difficulty":"Medium"},
],
"Euclidean Geometry": [
{"question": r"\text{O is the centre of a circle. The angle at the centre } AOB=100^\circ. \text{ Find the angle at the circumference } ACB.",
 "hint": r"\text{The angle at the centre is twice the angle at the circumference subtended by the same arc.}",
 "solution_steps":[
 {"explain": "Apply the theorem: the angle at the centre is always double the angle at the circumference, when both are subtended by the same arc.", "latex": r"ACB=\frac12 \times AOB \quad (2 Marks)"},
 {"explain": "Substitute the given central angle and simplify.", "latex": r"ACB=\frac12\times100^\circ=50^\circ \quad (1 Mark)"},
 ],
 "final_answer": r"50^\circ",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{ABCD is a cyclic quadrilateral with } \hat{A}=110^\circ. \text{ Find } \hat{C}.",
 "hint": r"\text{Opposite angles in a cyclic quadrilateral are supplementary (add to } 180^\circ\text{).}",
 "solution_steps":[
 {"explain": "Apply the cyclic quadrilateral theorem: opposite angles always add up to 180°.", "latex": r"\hat{A}+\hat{C}=180^\circ \quad (2 Marks)"},
 {"explain": "Substitute the known angle and solve for the other one.", "latex": r"\hat{C}=180^\circ-110^\circ=70^\circ \quad (1 Mark)"},
 ],
 "final_answer": r"70^\circ",
 "Marks":3,"difficulty":"Easy"},
{"question": r"\text{A tangent touches a circle at point } T. \text{ The angle between the tangent and chord } TP \text{ is } 55^\circ. \text{ Find the angle in the alternate segment.}",
 "hint": r"\text{Tan-chord theorem: the angle between a tangent and a chord equals the angle in the alternate segment.}",
 "solution_steps":[
 {"explain": "Apply the tan-chord theorem directly: the angle between a tangent and a chord always equals the angle in the alternate segment — no calculation needed, just identify the equal angle.", "latex": r"\text{Angle in alternate segment}=55^\circ \quad (2 Marks)"},
 ],
 "final_answer": r"55^\circ",
 "Marks":2,"difficulty":"Medium"},
]
}
}

# =====================================================
# SIDEBAR
# =====================================================
st.sidebar.title("🎓 Matric Maths Master")

# Always re-check the tier from the DB (not a cached value from login),
# since a PayFast webhook may have upgraded/cancelled it since then.
current_tier = get_user_tier(auth_user["id"])
tier_info = TIER_CONFIG[current_tier]

# Admins get full (Premium-equivalent) access regardless of their actual
# subscription, purely for testing — their real billing tier/label is
# untouched, this only affects feature-gating checks below. Re-checked
# fresh every run (not cached in session_state) so a grant/revoke via
# `python -m backend.set_admin` takes effect on the next page load.
is_admin_user = is_user_admin(auth_user["id"])
effective_tier = "premium" if is_admin_user else current_tier

st.sidebar.markdown(f"👋 **{auth_user['name']}**")
st.sidebar.markdown(f"Plan: **{tier_info['label']}**" + (" · 👑 Admin" if is_admin_user else ""))

if daily_limit(effective_tier) is not None:
    used_today = get_today_count(auth_user["id"])
    st.sidebar.caption(f"AI Tutor solves today: {used_today}/{daily_limit(effective_tier)}")

if is_admin_user:
    if st.sidebar.button("🔄 Reset my daily usage"):
        reset_today_usage(auth_user["id"])
        st.sidebar.success("Usage reset — refresh to see it take effect.")

with st.sidebar.expander("💳 Upgrade / Manage Plan"):
    for tier_key in TIER_ORDER:
        cfg = TIER_CONFIG[tier_key]
        if cfg["price_zar"] == 0:
            continue
        if tier_key == current_tier:
            st.success(f"✅ You're on {cfg['label']} (R{cfg['price_zar']}/month)")

            confirm_key = f"confirm_cancel_{tier_key}"
            if st.session_state.get(confirm_key):
                st.warning("Are you sure? This stops your subscription and downgrades your account.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Yes, cancel", key=f"cancel_yes_{tier_key}"):
                        result = cancel_subscription(auth_user["id"])
                        if result["payfast_notified"]:
                            st.success("Subscription cancelled — you won't be billed again.")
                        else:
                            st.warning(
                                "Your account has been downgraded, but we couldn't confirm "
                                "the cancellation with PayFast automatically. Please also "
                                "check your PayFast dashboard (or contact PayFast support) "
                                "to make sure the recurring payment is stopped."
                            )
                        st.session_state[confirm_key] = False
                with col_no:
                    if st.button("Never mind", key=f"cancel_no_{tier_key}"):
                        st.session_state[confirm_key] = False
                        st.rerun()
            else:
                if st.button("Cancel Subscription", key=f"cancel_{tier_key}"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            continue
        st.markdown(f"**{cfg['label']} — R{cfg['price_zar']}/month**")
        if st.button(f"Upgrade to {cfg['label']}", key=f"upgrade_{tier_key}"):
            payload = build_checkout_payload(
                m_payment_id=f"{auth_user['id']}-{uuid.uuid4().hex[:8]}",
                amount=cfg["price_zar"],
                item_name=f"Malita {cfg['label']} Subscription",
                name_first=auth_user["name"].split(" ")[0],
                email_address=auth_user["email"],
                return_url=f"{APP_BASE_URL}/?upgraded=1",
                cancel_url=f"{APP_BASE_URL}/?cancelled=1",
                notify_url=APP_WEBHOOK_URL,
                recurring=True,
                recurring_amount=cfg["price_zar"],
                frequency=3,  # monthly
                cycles=0,     # bill indefinitely until cancelled
                # Carries our own user id + target tier through PayFast's
                # round trip so the webhook knows whose subscription to update.
                custom_fields={"custom_str1": str(auth_user["id"]), "custom_str2": tier_key},
            )
            checkout_url = build_checkout_url(payload)
            st.markdown(f"[Click here to pay securely via PayFast]({checkout_url})")

st.sidebar.divider()

# A Home-dashboard tile click sets "pending_nav" and reruns rather than
# writing to session_state["nav_mode"] directly, since that button is
# rendered lower down the script, after this radio widget already exists
# this run — Streamlit forbids mutating a widget's key post-instantiation.
if st.session_state.get("pending_nav"):
    st.session_state["nav_mode"] = st.session_state.pop("pending_nav")

_NAV_OPTIONS = [
    "🧮 AI Tutor",
    "📝 Practice Questions",
    "📷 OCR Question",
    "📚 Past Papers (PDF)",
    "🎯 Learner Profile",
    "📏 Formula Sheet",
    "🏠 Home",
]
mode = st.sidebar.radio(
    "Choose Mode",
    _NAV_OPTIONS,
    # index only applies the very first time this widget renders for a
    # session (Streamlit ignores it once "nav_mode" already has a value in
    # session_state) - this is what makes Home the default landing page.
    index=_NAV_OPTIONS.index("🏠 Home"),
    key="nav_mode",
)

st.sidebar.divider()
if st.sidebar.button("Log Out"):
    st.session_state.auth_user = None
    st.rerun()

# =====================================================
# PRACTICE QUESTIONS
# =====================================================
if mode=="📝 Practice Questions":
    st.title("📝 Practice Questions")

    if st.button("🎲 Surprise me with a random question"):
        rand_paper = random.choice(list(practice_data.keys()))
        rand_topic = random.choice(list(practice_data[rand_paper].keys()))
        rand_idx = random.randrange(len(practice_data[rand_paper][rand_topic]))
        st.session_state["pq_paper"] = rand_paper
        st.session_state["pq_topic"] = rand_topic
        st.session_state["pq_qnum"] = f"Q{rand_idx + 1}"
        st.rerun()

    paper = st.selectbox("Select Paper", list(practice_data.keys()), key="pq_paper")

    topic_options = list(practice_data[paper].keys())
    if st.session_state.get("pq_topic") not in topic_options:
        st.session_state["pq_topic"] = topic_options[0]
    topic = st.selectbox("Select Topic", topic_options, key="pq_topic")
    topic_badge(topic)

    questions = practice_data[paper][topic]
    q_numbers = [f"Q{i+1}" for i in range(len(questions))]
    if st.session_state.get("pq_qnum") not in q_numbers:
        st.session_state["pq_qnum"] = q_numbers[0]
    q_selected = st.selectbox("Select Question Number", q_numbers, key="pq_qnum")
    q_data = questions[q_numbers.index(q_selected)]
    q_key = f"{paper}|{topic}|{q_selected}"

    st.markdown(f"### {q_selected}")
    st.caption(f"Difficulty: {q_data.get('difficulty', '—')} · Marks: {q_data['Marks']}")
    st.latex(q_data["question"])

    if q_data.get("hint"):
        with st.expander("💡 Need a hint?"):
            st.latex(q_data["hint"])

    attempt = st.text_input("Attempt your answer first:", key=f"attempt_{q_key}")

    col_check, col_solution = st.columns(2)
    with col_check:
        if st.button("✅ Check My Answer", key=f"check_{q_key}"):
            verdict = check_practice_answer(attempt, q_data["final_answer"])
            if verdict is True:
                st.success("Correct! 🎉")
                st.balloons()
            elif verdict is False:
                st.error("Not quite — try again, or reveal the solution below.")
            else:
                st.info("Enter your answer above, then reveal the solution below to check your work.")

    with col_solution:
        show_solution = st.button("📖 Show Solution", key=f"solution_{q_key}")

    if show_solution:
        st.markdown("### ✏️ Step-by-Step Solution")
        for i, step in enumerate(q_data["solution_steps"], start=1):
            st.markdown(f"**Step {i}:** {step['explain']}")
            st.latex(step["latex"])
        st.success("Final Answer")
        st.latex(q_data["final_answer"])
        st.info(f"Total Marks: {q_data['Marks']}")

        learner = st.session_state.learner
        if q_key not in learner["solved_set"]:
            learner["solved_set"].add(q_key)
            learner["solved"] += 1
            learner["Marks"] += q_data["Marks"]
            learner["topic_counts"][topic] = learner["topic_counts"].get(topic, 0) + 1
            record_solved_question(
                auth_user["id"], "practice",
                paper=paper, topic=topic, question=q_data["question"],
            )

# =====================================================
# AI SOLVER (FULL PAPER 1 & PAPER 2 LOGIC)
# =====================================================

elif mode == "🧮 AI Tutor":

    # -------------------------------------------------
    # HEADER LAYOUT
    # -------------------------------------------------
    with st.container(border=True):
        col1, col2 = st.columns([1, 6])

        with col1:
            if logo_svg:
                st.markdown(
                    f"""
                    <img src="data:image/png;base64,{logo_svg}"
                         style="max-width:100%; height:auto; border-radius:12px;">
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.markdown("### 🎓")

        with col2:
            st.markdown("""
            <h3 style="margin-bottom:0;">AI Tutor</h3>
            <p style="font-size:1.1rem; color:#475569; margin-top:0;">
                Grade 12 Mathematics help, worked out one step at a time.
            </p>
            """, unsafe_allow_html=True)



    paper = st.selectbox("Select Paper", ["Paper 1", "Paper 2"])

    if paper == "Paper 1":
        topic = st.selectbox(
            "Topic",
            ["Algebra", "Sequences", "Financial Mathematics", "Calculus", "Functions & Graphs"]
        )
    else:
        topic = st.selectbox(
            "Topic",
            ["Analytical Geometry", "Trigonometry", "Statistics", "Probability", "Euclidean Geometry"]
        )
    topic_badge(topic)

    with st.expander("💡 Not sure what to type? See examples for this topic"):
        EXAMPLE_QUESTIONS = {
            "Algebra": ["x^2-5x+6=0", "2x+3<11", "x+y=10, 2x-y=2"],
            "Sequences": ["3,7,11,...,99", "2,6,18,54"],
            "Financial Mathematics": [
                "R5000 is invested at 8% p.a. compounded quarterly for 3 years. Find the accumulated amount.",
                "A car worth R240000 depreciates at 12% p.a. on the reducing balance method. Find its value after 5 years.",
                "Thabo saves R800 at the end of every month for 4 years in an account earning 9% p.a. compounded monthly. Find the future value.",
            ],
            "Calculus": ["differentiate 3x^2-5x+4", "f(x) = x^3 - 2x"],
            "Functions & Graphs": ["y=x^2-4x+3", "x=y^2", "y=2/(x-1)+3"],
            "Analytical Geometry": ["Find the distance between A(1,2) and B(4,6)", "gradient of A(1,1) and B(5,9)"],
            "Trigonometry": ["solve 2sin(x)=1 for 0<=x<=360", "sin(30)"],
            "Statistics": ["2,4,6,8,10,12", "mean and standard deviation of 5,8,12,15,20"],
            "Probability": [
                "A bag contains 5 red and 3 blue balls. Find the probability of drawing a red ball.",
                "A die is rolled and a coin is tossed. Find the probability of getting a 6 and a head.",
                "P(A)=0.4, P(B)=0.3, A and B are mutually exclusive. Find P(A or B).",
            ],
            "Euclidean Geometry": ["angle at centre = 100, find angle at circumference", "cyclic quadrilateral angle A = 110, find angle C"],
        }
        for ex in EXAMPLE_QUESTIONS.get(topic, []):
            st.code(ex, language=None)

    # A plain `value=` text_input "locks in" whatever the learner types and
    # ignores value= on later reruns — so a Clear button that only resets
    # copied_text wouldn't actually clear text already typed. Using an
    # explicit key lets both Clear and OCR/PDF "Transfer to Solver" update
    # the box reliably: copied_text is treated as a one-shot pending value,
    # adopted into the keyed widget then immediately consumed (reset to
    # "") so it can't re-overwrite a later manual edit or Clear.
    QUESTION_KEY = "ai_tutor_question_input"
    if QUESTION_KEY not in st.session_state:
        st.session_state[QUESTION_KEY] = st.session_state.copied_text
    if st.session_state.copied_text and st.session_state.copied_text != st.session_state[QUESTION_KEY]:
        st.session_state[QUESTION_KEY] = st.session_state.copied_text
    st.session_state.copied_text = ""

    # Create the Clear button (and apply its effect) BEFORE the text_input
    # below is instantiated — Streamlit raises an exception if a keyed
    # widget's session_state is written to AFTER that same widget has
    # already been created in this run, so the write order here matters
    # even though the button renders visually to the right of the input.
    col_input, col_clear = st.columns([6, 1])
    with col_clear:
        st.write("")  # spacer so the button lines up with the input box, not its label
        clear_clicked = st.button("🗑️ Clear")
    if clear_clicked:
        st.session_state[QUESTION_KEY] = ""

    with col_input:
        question = st.text_input(
            "Enter your expression or type your question in words:",
            key=QUESTION_KEY,
        )
    x = sp.symbols("x")

    solve_clicked = st.button("Solve")
    if solve_clicked and question:
        allowed, limit_message = can_solve(auth_user["id"], effective_tier)
        if not allowed:
            st.warning(limit_message)
            st.stop()
        record_solve(auth_user["id"])
        record_solved_question(auth_user["id"], "ai_tutor", paper=paper, topic=topic, question=question)
        try:
            # ------------------------------
            # CLEAN & PARSE INPUT
            # ------------------------------
            # Replace ^ with ** for SymPy and remove spaces
            q_clean = question.replace("^", "**").replace(" ", "")
            
            # Split by comma to handle simultaneous equations
            raw_eqs = q_clean.split(",")
            
            # Identify all variable symbols (e.g., x, y) - works for ANY letter(s)
            # the learner uses, not just x/y.
            symbols_in_expr = detect_variables(q_clean)
            symbols_dict = {s: sp.symbols(s) for s in symbols_in_expr}
            var_list = list(symbols_dict.values())

            # =====================================================
            # PAPER 1
            # =====================================================
            if topic == "Algebra":
                st.markdown("### Algebra Solution")

                # ------------------------------
                # CLEAN & PARSE INPUT
                # ------------------------------
                question_clean = question.replace("^", "**").replace(" ", "")
                question_clean = re.sub(r'(\))(\()', r'\1*\2', question_clean)
                question_clean = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', question_clean)
                question_clean = question_clean.replace("≤", "<=").replace("≥", ">=")

                raw_eqs = question_clean.split(",")
                symbols_in_expr = detect_variables(question_clean)
                symbols_dict = {s: sp.symbols(s) for s in symbols_in_expr}
                var_list = list(symbols_dict.values())

                try:
                    parsed_eqs = []
                    is_inequality = False

                    for eq_str in raw_eqs:
                        if any(op in eq_str for op in ["<=", ">=", "<", ">"]):
                            is_inequality = True
                            parsed_eqs.append(safe_parse(eq_str, symbols_dict))
                        elif "=" in eq_str:
                            lhs_str, rhs_str = eq_str.split("=")
                            lhs = safe_parse(lhs_str, symbols_dict)
                            rhs = safe_parse(rhs_str, symbols_dict)
                            parsed_eqs.append(lhs - rhs)
                        else:
                            parsed_eqs.append(safe_parse(eq_str, symbols_dict))

#---------------------------------------------START INEQUALITY SOLVER----------------------------------------------------------------------------------
                    # ---------------------------------------------
                    # START INEQUALITY SOLVER (CLEAN VERSION)
                    # ---------------------------------------------
                    if is_inequality:

                        var = var_list[0]
                        inequality = parsed_eqs[0]

                        st.write("##### 💡 Step 1: Analyse the inequality")
                        st.latex(sp.latex(inequality))

                        # ---------------------------------------------
                        # STEP 2.1: Write in standard form
                        # ---------------------------------------------
                        st.write("##### 📝 Step 2: Calculation")

                        lhs, rhs = inequality.lhs, inequality.rhs
                        expr = sp.simplify(lhs - rhs)

                        st.markdown("**Step 2.1: Write the inequality with zero on one side**")
                        st.latex(sp.latex(inequality.func(expr, 0)))

                        # ---------------------------------------------
                        # STEP 2.2: Determine degree
                        # ---------------------------------------------
                        degree = sp.degree(expr, var)
                        st.markdown("**Step 2.2: Determine the degree of the expression**")
                        st.write(f"The degree of the expression is **{degree}**.")

                        roots = []
                        can_proceed = False

                        # ---------------------------------------------
                        # STEP 2.3: Find the roots
                        # ---------------------------------------------
                        st.markdown("**Step 2.3: Find the roots of the expression**")

                        factored = sp.factor(expr)
                        expanded = sp.expand(expr)

                        # CASE 1: Already factorised
                        if expr.is_Mul:
                            st.write("The expression is already factorised.")
                            st.latex(sp.latex(expr))
                            roots = sp.solve(expr, var)
                            can_proceed = True

                        # CASE 2: Factorisable after factoring
                        elif factored != expanded:
                            st.write("Factorising the expression:")
                            st.latex(sp.latex(factored))
                            roots = sp.solve(factored, var)
                            can_proceed = True

                        # CASE 3: Quadratic but not factorisable
                        elif degree == 2:
                            st.write("The expression cannot be factorised easily, We use the quadratic formula.")
                            #st.write("We use the quadratic formula.")

                            a = expanded.coeff(var, 2)
                            b = expanded.coeff(var, 1)
                            c = expanded.coeff(var, 0)

                            st.latex(rf"a = {a}, \quad b = {b}, \quad c = {c}")
                            st.latex(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
                            st.latex(rf"x = \frac{{-({b}) \pm \sqrt{{({b})^2 - 4({a})({c})}}}}{{2({a})}}")

                            discriminant = b**2 - 4*a*c
                            st.latex(rf"\Delta = ({b})^2 - 4({a})({c})")
                            st.latex(rf"\Delta = {sp.latex(discriminant)}")

                            if discriminant.is_negative:
                                st.error(
                                    "Since the discriminant is negative, there are **no real roots**."
                                )
                                st.info("Grade 12 learners do not work with complex numbers.")
                                can_proceed = False
                            else:
                                st.info(
                                    "Since the discriminant is non-negative, real roots exist."
                                )
                                roots = sp.solve(expanded, var)
                                can_proceed = True

                        # CASE 4: Higher degree (Grade 12 limit)
                        else:
                            st.warning(
                                "This inequality cannot be solved using Grade 12 methods."
                            )
                            can_proceed = False

                        # ---------------------------------------------
                        # STEP 2.4: Display roots
                        # ---------------------------------------------
                        if can_proceed and roots:
                            st.markdown("**Step 2.4: Critical values**")
                            for r in roots:
                                st.latex(f"{sp.latex(var)} = {sp.latex(r)}")

                            # ---------------------------------------------
                            # STEP 2.5: Solve inequality
                            # ---------------------------------------------
                            st.markdown("**Step 2.5: Solve the inequality**")
                            solution = solve_univariate_inequality(
                                inequality, var, relational=False
                            )

                            # ---------------------------------------------
                            # FINAL ANSWER
                            # ---------------------------------------------
                            st.markdown("### 🏁 Final Answer")

                            if isinstance(solution, sp.Interval):
                                left, right = solution.start, solution.end
                                left_op = "<" if solution.left_open else r"\leq"
                                right_op = "<" if solution.right_open else r"\leq"

                                st.latex(
                                    rf"{sp.latex(left)} {left_op} {sp.latex(var)} {right_op} {sp.latex(right)}"
                                )
                            else:
                                st.latex(sp.latex(solution))


#--------------------------------------------------END INEQUALITY SOLVER----------------------------------------------------------------------------------

                    # --------------------------------------------------
                    # ALGEBRAIC EQUATION SOLVER (NO INEQUALITIES)
                    # GRADE 12 SAFE – REAL ROOTS ONLY
                    # --------------------------------------------------
                    else:
                        breakpoint = False
                    #st.markdown("✏️ **Algebraic Equation Solution**")

                    # Assumptions:
                    # - parsed_eqs: list of sympy expressions already equal to 0
                    # - raw_eqs: original user input strings
                    # - var_list: detected variables
                    # - symbols_dict: sympy symbol dictionary

                        if len(parsed_eqs) == 1 and len(var_list) == 1:
                            var = var_list[0]
                            expr = parsed_eqs[0]

                            # ----------------------------------
                            # STEP 1: Write equation
                            # ----------------------------------
                            st.markdown("###### Step 1: Write the equation")

                            if "=" in raw_eqs[0]:
                                lhs_str, rhs_str = raw_eqs[0].split("=")
                                lhs = safe_parse(lhs_str, symbols_dict)
                                rhs = safe_parse(rhs_str, symbols_dict)
                                equation = lhs - rhs
                                st.latex(sp.latex(sp.Eq(lhs, rhs)))
                            else:
                                equation = expr
                                st.latex(sp.latex(expr) + " = 0")

                            # ----------------------------------
                            # STEP 2: Standard form
                            # ----------------------------------

                            st.markdown("###### Step 2: Write in standard form")

                            # expr_raw = equation BEFORE expansion
                            expr_raw = expr

                            # RHS is zero because we moved everything to LHS
                            rhs_is_zero = True

                            # ----------------------------------
                            # CASE 1: Already factorised (product form)
                            # ----------------------------------
                            if rhs_is_zero and expr_raw.is_Mul:
                                st.write("The equation is already factorised.")
                                st.latex(sp.latex(expr_raw) + " = 0")

                                factored = expr_raw

                            # ----------------------------------
                            # CASE 2: Not factorised → try factorising
                            # ----------------------------------
                            elif rhs_is_zero:
                                expr_std = sp.expand(expr_raw)
                                st.latex(sp.latex(expr_std) + " = 0")

                                degree = sp.degree(expr_std, var)
                                st.info(f"The degree of the equation is **{degree}**.")

                                factored = sp.factor(expr_std)

                                if factored != expr_std:
                                    st.write("Factorising the expression:")
                                    st.latex(sp.latex(factored) + " = 0")
                                else:
                                    pass
                                    #st.warning("Expression cannot be factorised further using Grade 12 methods.")
                                    #factored = expr_std

                            # ----------------------------------
                            # CASE 3: RHS ≠ 0 → must expand
                            # ----------------------------------
                            else:
                                st.write("Right-hand side is not zero. Rewrite in standard form.")
                                expr_std = sp.expand(expr_raw)
                                st.latex(sp.latex(expr_std) + " = 0")
                                factored = sp.factor(expr_std)


                            # ----------------------------------
                            # STEP 4: Solve factor-by-factor
                            # ----------------------------------
                            #st.info("Solve each factor:")

                            factors = factored.as_ordered_factors()
                            all_roots = []

                            for f in factors:
                                
                                # Remove powers: (x-2)^2 → x-2
                                base, power = f.as_base_exp()
                                base = sp.factor(base)

                                if not base.has(var):
                                    continue

                                deg = sp.degree(base, var)

                                # ------------------------------
                                # LINEAR FACTOR
                                # ------------------------------
                                
                                if deg == 1:
                                    st.markdown(f"**Solve:** ${sp.latex(base)} = 0$")
                                    root = sp.solve(base, var)[0]
                                    st.latex(rf"{sp.latex(var)} = {sp.latex(root)}")
                                    all_roots.append(root)

                                # ------------------------------
                                # QUADRATIC FACTOR
                                # ------------------------------
                                elif deg == 2:
                                    st.info(f"**Solve quadratic factor:** ${sp.latex(base)} = 0$")

                                    a = base.coeff(var, 2)
                                    b = base.coeff(var, 1)
                                    c = base.coeff(var, 0)

                                    st.markdown("Quadratic Formula:")
                                    st.latex(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
                                    st.latex(rf"a = {a}, \quad b = {b}, \quad c = {c}")
                                    st.latex(rf"{sp.latex(var)} = \frac{{-({b}) \pm \sqrt{{({b})^2 - 4({a})({c})}}}}{{2({a})}}")

                                    discriminant = b**2 - 4*a*c
                                    st.latex(r"\Delta = b^2 - 4ac")
                                    st.latex(rf"\Delta = ({b})^2 - 4({a})({c})")
                                    st.latex(rf"\Delta = {sp.latex(discriminant)}")

                                    if discriminant < 0:
                                        st.error("No real roots (ignored at Grade 12 level).")
                                        continue

                                    roots = sp.solve(base, var)
                                    for r in roots:
                                        st.latex(rf"{sp.latex(var)} = {sp.latex(r)}")
                                        all_roots.append(r)

                                # ------------------------------
                                # HIGHER DEGREE (IGNORED)
                                # ------------------------------
                                else:
                                    st.warning(
                                        f"Factor ${sp.latex(base)}$ is degree {deg} and "
                                        "cannot be solved using Grade 12 methods."
                                    )

                            # ----------------------------------
                            # FINAL ANSWER
                            # ----------------------------------
                            st.markdown("###### 🏁 Final Answer")

                            # Remove duplicates (handles repeated roots)
                            final_roots = list(dict.fromkeys(all_roots))

                            if final_roots:
                                answer = " \\text{ or } ".join(
                                    [rf"{sp.latex(var)} = {sp.latex(r)}" for r in final_roots]
                                )
                                st.latex(answer)
                            else:
                                st.error("No real solutions found.")

                        #else:
                        #    st.warning("This solver currently supports ONE equation with ONE variable only.")

                                        # -----------------------------------
                                # MULTI-VARIABLE SYSTEM (STEP-BY-STEP)
                                # -----------------------------------
                        else:
                            st.markdown("### 🔢 Solving Simultaneous Equations (Elimination Method)")

                            # Only handle 2 equations & 2 variables for step-by-step
                            if len(parsed_eqs) == 2 and len(var_list) == 2:
                                x, y = var_list
                                eq1, eq2 = parsed_eqs

                                # Convert to Eq objects if needed
                                if not isinstance(eq1, sp.Equality):
                                    eq1 = sp.Eq(eq1, 0)
                                if not isinstance(eq2, sp.Equality):
                                    eq2 = sp.Eq(eq2, 0)

                                st.markdown("**Step 1: Write the equations**")

                                # Use raw equations exactly as entered
                                lhs1, rhs1 = raw_eqs[0].split("=")
                                lhs2, rhs2 = raw_eqs[1].split("=")

                                eq1_display = sp.Eq(
                                    safe_parse(lhs1, symbols_dict),
                                    safe_parse(rhs1, symbols_dict)
                                )

                                eq2_display = sp.Eq(
                                    safe_parse(lhs2, symbols_dict),
                                    safe_parse(rhs2, symbols_dict)
                                )

                                st.latex(sp.latex(eq1_display))
                                st.latex(sp.latex(eq2_display))


                                # Move to standard form
                                expr1 = eq1.lhs - eq1.rhs
                                expr2 = eq2.lhs - eq2.rhs

                                a1 = expr1.coeff(x)
                                b1 = expr1.coeff(y)
                                c1 = -expr1.subs({x: 0, y: 0})

                                a2 = expr2.coeff(x)
                                b2 = expr2.coeff(y)
                                c2 = -expr2.subs({x: 0, y: 0})

                                st.markdown("**Step 2: Write in standard form**")
                                #st.latex(rf"{a1}{sp.latex(x)} + {b1}{sp.latex(y)} = {c1}")
                                #st.latex(rf"{a2}{sp.latex(x)} + {b2}{sp.latex(y)} = {c2}")
                                st.latex(sp.latex(eq1))
                                st.latex(sp.latex(eq2))

                                # -----------------------------------
                                # Step 3: Eliminate one variable (SHOW FULL SIMPLIFICATION)
                                # -----------------------------------
                                st.markdown("**Step 3: Eliminate one variable**")

                                st.markdown("Subtract equation (2) from equation (1):")

                                # Step 3.1: Write subtraction explicitly
                                st.markdown("**Step 3.1: Substitute and subtract**")
                                st.latex(
                                    rf"({sp.latex(expr1)}) - ({sp.latex(expr2)}) = 0"
                                )

                                # Step 3.2: Remove brackets (change signs)
                                st.markdown("**Step 3.2: Remove brackets**")

                                # Get terms of expr1 and expr2 separately
                                terms1 = expr1.as_ordered_terms()
                                terms2 = [-t for t in expr2.as_ordered_terms()]  # flip signs manually

                                # Combine terms without simplifying
                                all_terms = terms1 + terms2

                                # Convert each term to LaTeX and join with proper signs
                                def term_latex(term):
                                    s = sp.latex(term)
                                    # ensure unary plus is handled nicely
                                    if s[0] != '-' :
                                        s = '+' + s
                                    return s

                                latex_terms = ''.join([term_latex(t) for t in all_terms])

                                # Remove leading '+' if present
                                if latex_terms[0] == '+':
                                    latex_terms = latex_terms[1:]                               
                                #result_expr = sp.expand(removed_brackets)
                                st.latex(
                                    rf"{latex_terms} = 0"
                                )

                                # Step 3.3: Expand terms
                                st.markdown("**Step 3.3: Expand terms**")

                                expanded = sp.expand(expr1 - expr2)
                                st.latex(sp.latex(expanded) + " = 0")
                                #rf"{sp.latex(expanded)} = 0"
                                #st.latex(sp.latex(expanded))

                                # Step 3.4: Rearrange to standard form
                                st.markdown("**Step 3.4: Rearrange and simplify**")

                                simplified = sp.simplify(expanded)
                                st.latex(sp.latex(simplified) + " = 0")

                                new_eq = simplified



                                # Solve for y
                                y_value = sp.solve(new_eq, y)[0]

                                # --- Step 4: Solve for y ---
                                # We calculate the expression for y first
                                y_expr = sp.solve(new_eq, y)[0] 

                                st.markdown("**Step 4: Solve for** $y$")
                                # If y_expr still contains 'x', we show it as an intermediate step
                                st.latex(rf"{sp.latex(y)} = {sp.latex(y_expr)}")

                                # --- Step 5: Substitute into one of the original equations ---
                                st.markdown("**Step 5: Substitute into one of the original equations**")
                                substituted = eq1.subs(y, y_expr)
                                st.latex(sp.latex(substituted))

                                # --- Step 6: Solve for x ---
                                x_value = sp.solve(substituted, x)[0]
                                st.markdown("**Step 6: Solve for** $x$")
                                st.latex(rf"{sp.latex(x)} = {sp.latex(x_value)}")

                                # --- Final Answer (With explicit substitution for y) ---
                                st.markdown("### 🏁 Final Answer")

                                # 1. Substitute the numerical x_value into the y_expression to show the "work"
                                y_final_substitution = y_expr.subs(x, x_value)
                                y_final_numeric = sp.simplify(y_final_substitution)

                                # 2. Display x
                                st.latex(rf"{sp.latex(x)} = {sp.latex(x_value)}")

                                # 3. Display y substitution step (e.g., y = 30 - 3)
                                # We check if y_expr was dependent on x to avoid redundant lines if y was already a number
                                if y_expr.has(x):
                                    st.latex(rf"{sp.latex(y)} = {sp.latex(y_expr.subs(x, sp.Symbol(sp.latex(x_value))))}") 
                                    
                                # 4. Display y final result (e.g., y = 27)
                                st.latex(rf"{sp.latex(y)} = {sp.latex(y_final_numeric)}")

                            else:
                                st.warning("Step-by-step solution is currently supported for 2 equations with 2 variables only.")
                                solution = sp.solve(parsed_eqs, var_list, dict=True)
                                for sol in solution:
                                    for var in var_list:
                                        st.latex(f"{sp.latex(var)} = {sp.latex(sol[var])}")


                except Exception as e:
                    st.error("Error parsing expression.")
                    st.caption(str(e))

       #-----------------------------------------------------------------------------------------------         
                           #SEQUENCES MODULE
        #----------------------------------------------------------------------------------------------
            elif topic == "Sequences":
                st.markdown("### 🔢 Sequence Analyzer")

                try:
                    raw = question.strip()

                    # ------------------------------
                    # STEP 1: Split at ...
                    # ------------------------------
                    if "..." in raw or ".." in raw:
                        parts = re.split(r"\.\.\.|\.{2}", raw, maxsplit=1)
                        left_part = parts[0]
                        right_part = parts[1] if len(parts) > 1 else ""
                    else:
                        left_part = raw
                        right_part = ""

                    # Normalize separators
                    left_part = left_part.replace("+", ",")
                    right_part = right_part.replace("+", ",")

                    # Extract numbers
                    left_numbers = re.findall(r"-?\d+\.?\d*", left_part)
                    seq = [int(n) for n in left_numbers]

                    right_numbers = re.findall(r"-?\d+\.?\d*", right_part)
                    last_term = int(right_numbers[-1]) if right_numbers else None

                    # ------------------------------
                    # STEP 2: Display given sequence
                    # ------------------------------
                    st.markdown("**Step 1: Write the sequence**")
                    st.latex(",\\;".join(map(str, seq)) + (",\\;\\ldots" if "..." in raw else ""))

                    if len(seq) < 3:
                        st.error("At least 3 terms are required to identify a sequence.")
                        st.stop()

                    # ------------------------------
                    # STEP 3: Detect sequence type
                    # ------------------------------
                    diffs = [seq[i+1] - seq[i] for i in range(len(seq)-1)]
                    ratios = []

                    if all(seq[i] != 0 for i in range(len(seq)-1)):
                        ratios = [seq[i+1] / seq[i] for i in range(len(seq)-1)]

                    TOL = 1e-6
                    is_arithmetic = all(abs(d - diffs[0]) < TOL for d in diffs)
                    is_geometric = ratios and all(abs(r - ratios[0]) < TOL for r in ratios)

                    # ------------------------------
                    # ARITHMETIC SEQUENCE
                    # ------------------------------
                    if is_arithmetic:
                        a = seq[0]
                        d = diffs[0]

                        st.success("This is an **Arithmetic Sequence**")

                        st.markdown("**Step 2: Identify parameters**")

                        #st.markdown("### 🔍 Step 2: Find a and d")

                        # Ensure at least 2 terms exist
                        if len(seq) < 2:
                            st.error("At least two terms are required to find a and d.")
                        else:
                            # First term
                            a = seq[0]
                            # Common difference
                            d = seq[1] - seq[0]

                            # Display steps
                            st.markdown("**First term (a):**")
                            st.latex(r"a = T_1")
                            st.latex(rf"a = {a}")

                            st.markdown("**Common difference (d):**")
                            st.latex(r"d = T_2 - T_1")
                            #st.latex(rf"d = {seq[1]} - {seq[0]} = {d}")
                            st.latex(rf"d = {seq[1]} - {seq[0]}")
                            #st.latex(rf"a = {a}, \quad d = {d}")
                            st.latex(rf"\quad d = {d}")


                        st.markdown("**Step 3: General term**")
                        st.latex(r"T_n = a + (n-1)d")
                        st.latex(rf"T_n = {a} + (n-1)({d})")
                        st.latex(rf"T_n = {a} + {d}n-{d}")
                        expanded = sp.expand(a + (sp.Symbol('n') - 1)*d)
                        #st.markdown("**Expand**")
                        st.latex(rf"T_n = {sp.latex(expanded)}")
                        #simplified = sp.simplify(expanded)
                        #st.markdown("**Simplified general term**")
                        #st.latex(rf"T_n = {sp.latex(simplified)}")



                        if last_term is not None:
                            st.markdown("**Step 4: Find number of terms**")
                            st.latex(rf"{last_term} = {a} + (n-1){d}")
                            n = (last_term - a) / d + 1
                            n = int(n) if n.is_integer() else n
                            st.latex(rf"n = {n}")

                            st.markdown("**Step 5: Sum of terms**")
                            st.latex(r"S_n = \frac{n}{2}(a + l)")
                            st.latex(rf"S_{n} = \frac{{{n}}}{2}({a}+{last_term})")

                    # ------------------------------
                    # GEOMETRIC SEQUENCE
                    # ------------------------------
                    elif is_geometric:
                        a = seq[0]
                        r = ratios[0]

                        st.success("This is a **Geometric Sequence**")

                        st.markdown("**Step 2: Identify parameters**")

                        
                        a = seq[0]
                        #st.markdown("**Step 2: Identify the first term (a)**")
                        st.latex(r"a = T_1")
                        st.latex(rf"a = {a}")

                        # Step 3: Identify common ratio (r)
                        if len(seq) >= 2:
                            r = seq[1] / seq[0]
                            #st.markdown("**Step 3: Identify the common ratio (r)**")
                            st.latex(r"r = \frac{T_2}{T_1}=\frac{T_3}{T_2}")
                            st.latex(rf"r = \frac{{{seq[1]}}}{{{seq[0]}}}")
                            #r_frac = sp.Rational(r).limit_denominator()
                            #st.latex(rf"\quad r = \frac{{{r_frac.numerator}}}{{{r_frac.denominator}}}")
                            st.latex(rf"\quad r = {r}")

                        st.markdown("**Step 3: General term**")
                        st.latex(r"T_n = ar^{n-1}")
                        st.latex(rf"T_n = {a}({r})^{{n-1}}")

                        if last_term is not None:
                            st.markdown("**Step 4: Find number of terms**")
                            st.latex(rf"{last_term} = {a}({r})^{{n-1}}")
                            n = sp.solve(sp.Eq(last_term, a * r**(sp.symbols("n")-1)), sp.symbols("n"))
                            st.latex(rf"n = {sp.latex(n)}")

                    # ------------------------------
                    # NEITHER
                    # ------------------------------
                    else:
                        st.error("This sequence is neither arithmetic nor geometric.")

                except Exception as e:
                    st.error("Could not analyse the sequence.")
                    st.caption(str(e))






            elif topic == "Financial Mathematics":
                st.markdown("### 💰 Finance, Growth & Decay")

                try:
                    # Legacy shorthand "P=1000,i=10,n=2" still works exactly
                    # as before. Anything else is treated as a plain-English
                    # word problem and run through the finance parser.
                    P_match = re.search(r"\bP\s*=\s*([-+]?\d*\.?\d+)", question)
                    i_match = re.search(r"\bi\s*=\s*([-+]?\d*\.?\d+)", question)
                    n_match = re.search(r"\bn\s*=\s*([-+]?\d*\.?\d+)", question)

                    if P_match and i_match and n_match:
                        detected = {
                            "type": "compound", "P": float(P_match.group(1)),
                            "rate": float(i_match.group(1)) / 100,
                            "years": float(n_match.group(1)), "freq": 1,
                        }
                    else:
                        detected = extract_financial_params(question)

                    TYPE_LABELS = {
                        "compound": "Compound Interest / Growth",
                        "simple": "Simple Interest",
                        "depreciation_straight": "Straight-line Depreciation",
                        "depreciation_reducing": "Reducing-balance Depreciation",
                        "annuity_future": "Future Value Annuity (regular savings)",
                        "annuity_present": "Present Value Annuity (loan repayments)",
                    }
                    type_keys = list(TYPE_LABELS.keys())
                    default_idx = type_keys.index(detected.get("type", "compound"))

                    calc_type = st.selectbox(
                        "Detected calculation type (change if this isn't right):",
                        type_keys, index=default_idx,
                        format_func=lambda k: TYPE_LABELS[k],
                    )

                    col_a, col_b, col_c, col_d = st.columns(4)
                    with col_a:
                        P = st.number_input("Amount (P)", value=float(detected.get("P", 1000.0)))
                    with col_b:
                        rate_pct = st.number_input("Annual rate (%)", value=float(detected.get("rate", 0.1) * 100))
                    with col_c:
                        years = st.number_input("Term (years)", value=float(detected.get("years", 1.0)))
                    with col_d:
                        if calc_type in ("compound", "annuity_future", "annuity_present"):
                            freq_options = {"Annually": 1, "Half-yearly": 2, "Quarterly": 4, "Monthly": 12, "Daily": 365}
                            freq_default = detected.get("freq", 1)
                            freq_names = list(freq_options.keys())
                            freq_defaults_reverse = {v: k for k, v in freq_options.items()}
                            freq_name = st.selectbox(
                                "Compounding", freq_names,
                                index=freq_names.index(freq_defaults_reverse.get(freq_default, "Annually")),
                            )
                            freq = freq_options[freq_name]
                        else:
                            st.caption("Compounding frequency not used for this calculation type.")
                            freq = 1

                    rate = rate_pct / 100
                    i = rate / freq
                    n = years * freq

                    if calc_type in ("annuity_future", "annuity_present"):
                        x = st.number_input(
                            "Regular payment (x)", value=float(detected.get("x", 500.0))
                        )

                    st.markdown("###### ✏️ Step-by-step Solution")

                    if calc_type == "compound":
                        st.latex(r"A = P(1+i)^n")
                        st.latex(rf"i = \frac{{{rate*100:.4g}\%}}{{{freq}}} = {i:.6g},\quad n = {years:.4g}\times{freq}={n:.4g}")
                        A = P * (1 + i) ** n
                        st.latex(rf"A = {P:.4g}(1+{i:.6g})^{{{n:.4g}}} = R{A:,.2f}")
                        final_value, chart_kind, chart_args = A, "compound", dict(P=P, i_period=i, n_period=n)

                    elif calc_type == "simple":
                        st.latex(r"A = P(1+ni)")
                        A = P * (1 + n * i) if freq != 1 else P * (1 + years * rate)
                        n_disp = years if freq == 1 else n
                        i_disp = rate if freq == 1 else i
                        st.latex(rf"A = {P:.4g}(1+{n_disp:.4g}\times{i_disp:.6g}) = R{A:,.2f}")
                        final_value, chart_kind, chart_args = A, "simple", dict(P=P, i_period=i_disp, n_period=n_disp)

                    elif calc_type == "depreciation_straight":
                        st.latex(r"A = P(1-ni)")
                        A = max(P * (1 - years * rate), 0)
                        st.latex(rf"A = {P:.4g}(1-{years:.4g}\times{rate:.6g}) = R{A:,.2f}")
                        final_value, chart_kind, chart_args = A, "depreciation_straight", dict(P=P, i_period=rate, n_period=years)

                    elif calc_type == "depreciation_reducing":
                        st.latex(r"A = P(1-i)^n")
                        A = P * (1 - rate) ** years
                        st.latex(rf"A = {P:.4g}(1-{rate:.6g})^{{{years:.4g}}} = R{A:,.2f}")
                        final_value, chart_kind, chart_args = A, "depreciation_reducing", dict(P=P, i_period=rate, n_period=years)

                    elif calc_type == "annuity_future":
                        st.latex(r"F = \frac{x[(1+i)^n - 1]}{i}")
                        st.latex(rf"i = \frac{{{rate*100:.4g}\%}}{{{freq}}} = {i:.6g},\quad n = {years:.4g}\times{freq}={n:.4g}")
                        F = x * ((1 + i) ** n - 1) / i
                        st.latex(rf"F = \frac{{{x:.4g}[(1+{i:.6g})^{{{n:.4g}}} - 1]}}{{{i:.6g}}} = R{F:,.2f}")
                        final_value, chart_kind, chart_args = F, "annuity_future", dict(P=0, i_period=i, n_period=n, x=x)

                    else:  # annuity_present — loan, solve for the instalment x
                        st.latex(r"P = \frac{x[1-(1+i)^{-n}]}{i} \;\Rightarrow\; x = \frac{Pi}{1-(1+i)^{-n}}")
                        st.latex(rf"i = \frac{{{rate*100:.4g}\%}}{{{freq}}} = {i:.6g},\quad n = {years:.4g}\times{freq}={n:.4g}")
                        instalment = P * i / (1 - (1 + i) ** (-n))
                        st.latex(rf"x = \frac{{{P:.4g}\times{i:.6g}}}{{1-(1+{i:.6g})^{{-{n:.4g}}}}} = R{instalment:,.2f} \;\text{{per period}}")
                        final_value, chart_kind, chart_args = instalment, "annuity_present", dict(P=P, i_period=i, n_period=n, x=instalment)

                    st.success(f"🏁 Final Answer: R{final_value:,.2f}")

                    fig = plot_finance_chart(chart_kind, **chart_args)
                    if fig is not None:
                        st.pyplot(fig, use_container_width=True)

                except Exception as e:
                    st.error("Could not parse financial parameters from the question.")
                    st.caption(str(e))


            elif topic == "Calculus":
                st.markdown("### 📐 Differentiation: Comparison of Methods")
                
                try:
                    # --- 1. CLEAN & PARSE INPUT ---
                    expr_str = question.lower()
                    # Remove common prefixes (any single-letter dependent variable,
                    # e.g. "y=", "f(x)=", "g(t)=", not just x)
                    expr_str = re.sub(r"(find derivative of|differentiate|d\w*/d\w*)", "", expr_str)
                    expr_str = re.sub(r"^[a-zA-Z]\([a-zA-Z]\)\s*=", "", expr_str)
                    expr_str = re.sub(r"^[a-zA-Z]\s*=", "", expr_str)
                    expr_str = expr_str.strip()

                    # Handle implicit multiplication and powers
                    expr_str = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', expr_str)
                    expr_str = re.sub(r'(\))(\()', r'\1*\2', expr_str)
                    expr_str = expr_str.replace("^", "**")

                    # Detect whichever variable the learner used (x, a, t, ...)
                    detected_vars = detect_variables(expr_str)
                    var_name = detected_vars[0] if detected_vars else "x"
                    x = sp.symbols(var_name)
                    symbols_dict = {var_name: x}

                    expr = safe_parse(expr_str, symbols_dict)
                    h = sp.symbols("h")

                    # --- 2. CREATE SIDE-BY-SIDE COLUMNS ---
                    col1, col2 = st.columns(2)

                    # --- LEFT COLUMN: POWER RULE ---
                    with col1:
                        st.subheader("🚀 Power Rule")
                        st.info("The standard shortcut method.")
                        
                        derivative_pr = sp.diff(expr, x)
                        
                        st.markdown("**Step 1: Apply rules to terms**")
                        terms = expr.as_ordered_terms()
                        for term in terms:
                            coeff, power = term.as_coeff_exponent(x)
                            if power != 0:
                                st.latex(rf"\frac{{d}}{{d{var_name}}}({sp.latex(term)}) = {sp.latex(coeff * power)}{var_name}^{{{sp.latex(power-1)}}}")
                            else:
                                st.latex(rf"\frac{{d}}{{d{var_name}}}({sp.latex(term)}) = 0")
                        
                        st.markdown("**Final Result (Power Rule):**")
                        st.latex(rf"f'({var_name}) = {sp.latex(derivative_pr)}")

                    # --- RIGHT COLUMN: FIRST PRINCIPLE ---
                    with col2:
                        st.subheader("📝 First Principle")
                        st.info("Definition using limits.")
                        
                        # Step 1: Formula and Substitution
                        st.markdown("**Step 1: Substitution**")
                        f_x = expr
                        f_xh = expr.subs(x, x + h)
                        
                        st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} \frac{{f({var_name}+h) - f({var_name})}}{{h}}")
                        st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} \frac{{{sp.latex(f_xh)} - ({sp.latex(f_x)})}}{{h}}")
                        
                        # Step 2: Simplify numerator
                        st.markdown("**Step 2: Expand Numerator**")
                        numerator_expanded = sp.expand(f_xh - f_x)
                        st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} \frac{{{sp.latex(numerator_expanded)}}}{{h}}")
                        
                        # Step 3: Factor and Cancel h
                        st.markdown("**Step 3: Cancel $h$**")
                        # We divide by h manually to show the cancellation clearly
                        terms_after_h = sp.expand(numerator_expanded / h)
                        st.latex(rf"f'({var_name}) = \lim_{{h \to 0}} ({sp.latex(terms_after_h)})")
                        
                        # Step 4: Final Limit
                        st.markdown("**Step 4: Final Result**")
                        derivative_fp = sp.limit(numerator_expanded / h, h, 0)
                        st.latex(rf"f'({var_name}) = {sp.latex(derivative_fp)}")

                except Exception as e:
                    st.error("Could not parse the expression for differentiation.")
                    st.caption(f"Error details: {str(e)}")


            elif topic == "Functions & Graphs":
                st.markdown("### 📈 Functions & Graphs")

                try:
                    # ---------------------------------------------------
                    # 1. CLEAN INPUT
                    # ---------------------------------------------------
                    expr_str = question.lower()
                    expr_str = re.sub(r"(graph|sketch|draw)", "", expr_str)
                    expr_str = expr_str.strip()
                    expr_str = expr_str.replace("^", "**")

                    # Handle implicit multiplication
                    expr_str = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', expr_str)
                    expr_str = re.sub(r'(\))(\()', r'\1*\2', expr_str)

                    # ---------------------------------------------------
                    # 1b. DETECT VARIABLES — works whichever letters the
                    # learner used, and understands BOTH "y = x**2" AND
                    # "x = y**2" (variable roles swapped), or any other
                    # letter pair like "b = a**2 - 4a + 2".
                    # ---------------------------------------------------
                    detected_vars = detect_variables(expr_str)
                    symbols_dict = {v: sp.symbols(v) for v in detected_vars}

                    if "=" in expr_str:
                        lhs_str, rhs_str = expr_str.split("=", 1)
                        lhs_expr = safe_parse(lhs_str, symbols_dict)
                        rhs_expr = safe_parse(rhs_str, symbols_dict)
                    else:
                        # No '=' given, e.g. just "x**2-4x+2" -> assume it's
                        # the formula for a dependent variable "y" (or a
                        # fresh name if "y" is itself the only detected var).
                        rhs_expr = safe_parse(expr_str, symbols_dict)
                        dep_name = "y" if "y" not in detected_vars else "z"
                        lhs_expr = sp.symbols(dep_name)
                        symbols_dict[dep_name] = lhs_expr
                        detected_vars = sorted(set(detected_vars) | {dep_name})

                    equation = lhs_expr - rhs_expr
                    eq_symbols = sorted(equation.free_symbols, key=lambda s: s.name)

                    if len(eq_symbols) > 2:
                        st.error("This solver currently supports relations between two variables only (e.g. x and y).")
                        st.stop()

                    # ----------------------------------
                    # DECIDE WHICH SYMBOL IS "DEPENDENT" (out_var) vs
                    # "INDEPENDENT" (indep_var) FOR THE STEP-BY-STEP ANALYSIS.
                    # Prefer whichever side of "=" was a single bare symbol
                    # (e.g. "y=..." -> out_var=y ; "x=y**2" -> out_var=x).
                    # ----------------------------------
                    out_var = None
                    indep_var = None
                    formula = None

                    if isinstance(lhs_expr, sp.Symbol) and lhs_expr in eq_symbols:
                        out_var = lhs_expr
                        formula = rhs_expr
                    elif isinstance(rhs_expr, sp.Symbol) and rhs_expr in eq_symbols:
                        out_var = rhs_expr
                        formula = lhs_expr
                    else:
                        # True implicit relation (both sides mix variables),
                        # e.g. a circle x**2+y**2=25 -- fall back to solving.
                        out_var = eq_symbols[-1] if len(eq_symbols) > 1 else eq_symbols[0]
                        formula = None

                    remaining = [s for s in eq_symbols if s != out_var]
                    indep_var = remaining[0] if remaining else sp.symbols(
                        "x" if out_var.name != "x" else "t"
                    )

                    # For PLOTTING, always show x horizontally and y vertically
                    # when those are the two letters in play; otherwise plot
                    # alphabetically first symbol horizontally.
                    if {s.name for s in eq_symbols} == {"x", "y"}:
                        plot_horiz = sp.symbols("x")
                        plot_vert = sp.symbols("y")
                    elif len(eq_symbols) == 2:
                        plot_horiz, plot_vert = eq_symbols[0], eq_symbols[1]
                    else:
                        plot_horiz = indep_var
                        plot_vert = out_var

                    # branches = expression(s) for plot_vert purely in terms
                    # of plot_horiz, e.g. "x=y**2" -> [sqrt(x), -sqrt(x)].
                    # We ALWAYS solve directly against the full relation
                    # (rather than trusting `formula` blindly) because
                    # `formula` can be expressed in terms of the WRONG
                    # variable whenever the learner writes the equation with
                    # variables "swapped", e.g. "x = y**2" instead of the
                    # usual "y = x**2". Solving explicitly for plot_vert is
                    # what makes graphs like x=y^2 render correctly instead
                    # of silently being plotted as if it said y=x^2.
                    if formula is not None and out_var == plot_vert:
                        branches = [formula]
                    else:
                        try:
                            branches = sp.solve(sp.Eq(lhs_expr, rhs_expr), plot_vert)
                        except Exception:
                            branches = None
                        if not branches:
                            branches = None

                    is_explicit_function = bool(
                        branches is not None and len(branches) == 1
                        and not branches[0].has(plot_vert)
                    )

                    x = indep_var  # kept for readability in the walkthrough below
                    expr = branches[0] if is_explicit_function else None

                    st.markdown("##### 🔹 Given Relation")
                    st.latex(sp.latex(sp.Eq(lhs_expr, rhs_expr)))

                    if branches and not is_explicit_function:
                        branch_strs = " or ".join(
                            rf"${sp.latex(plot_vert)}={sp.latex(b)}$" for b in branches
                        )
                        st.caption(f"Rewritten to isolate ${sp.latex(plot_vert)}$: {branch_strs}")

                    # ---------------------------------------------------
                    # DETAILED STEP-BY-STEP ANALYSIS
                    # Only fully meaningful when we have one explicit
                    # formula: out_var = f(indep_var). For genuinely
                    # implicit relations (e.g. circles, or "x=y**2" which
                    # isn't a function of x at all — it fails the vertical
                    # line test) we skip straight to generic intercepts
                    # plus the graph, further down.
                    # ---------------------------------------------------
                    if is_explicit_function:

                        # ---------------------------------------------------
                        # 2. DOMAIN
                        # ---------------------------------------------------
                        st.markdown(f"##### 🔹 Domain (in terms of {sp.latex(indep_var)})")
                        domain = sp.calculus.util.continuous_domain(expr, indep_var, sp.S.Reals)
                        st.latex(r"\text{Domain: } " + sp.latex(domain))

                        # ---------------------------------------------------
                        # 3. Y-INTERCEPT (value of out_var when indep_var = 0)
                        # ---------------------------------------------------
                        st.markdown(f"##### 🔹 {sp.latex(out_var)}-intercept")
                        try:
                            y_int = expr.subs(indep_var, 0)
                            st.latex(rf"\text{{intercept: }} ({sp.latex(indep_var)}=0,\ {sp.latex(out_var)}={sp.latex(y_int)})")
                        except Exception:
                            st.latex(r"\text{No intercept found}")

                        # ---------------------------------------------------
                        # 4. X-INTERCEPTS (indep_var values where out_var = 0)
                        # ---------------------------------------------------
                        st.markdown(f"##### 🔹 {sp.latex(indep_var)}-intercepts")
                        real_roots = []
                        try:
                            roots = sp.solve(expr, indep_var)
                            for r in roots:
                                if r.is_real:
                                    real_roots.append(r)
                                    st.latex(rf"({sp.latex(r)}, 0)")
                            if not real_roots:
                                st.latex(r"\text{No real intercepts}")
                        except Exception:
                            st.write("Could not determine intercepts symbolically.")

                        # ---------------------------------------------------
                        # 5. FIRST DERIVATIVE
                        # ---------------------------------------------------
                        st.markdown("##### 🔹 First Derivative")
                        derivative = sp.diff(expr, indep_var)
                        st.latex(rf"\frac{{d{sp.latex(out_var)}}}{{d{sp.latex(indep_var)}}} = " + sp.latex(derivative))

                        # ---------------------------------------------------
                        # 6. TURNING POINTS
                        # ---------------------------------------------------
                        st.markdown("##### 🔹 Turning Points")
                        turning_points = []
                        try:
                            turning_x = sp.solve(derivative, indep_var)
                            if turning_x:
                                second_derivative = sp.diff(derivative, indep_var)
                                for tx in turning_x:
                                    if tx.is_real:
                                        ty = expr.subs(indep_var, tx)
                                        turning_points.append(ty)
                                        st.latex(rf"{sp.latex(indep_var)} = {sp.latex(tx)}, {sp.latex(out_var)} = {sp.latex(ty)}")

                                        nature = second_derivative.subs(indep_var, tx)
                                        if nature > 0: st.latex(r"\text{Minimum}")
                                        elif nature < 0: st.latex(r"\text{Maximum}")
                                        else: st.latex(r"\text{Inflection}")
                            else:
                                st.latex(r"\text{No turning points}")
                        except Exception:
                            st.write("Calculated numerically in graph.")

                        # ---------------------------------------------------
                        # 7. AXIS OF SYMMETRY
                        # ---------------------------------------------------
                        try:
                            if sp.degree(expr, indep_var) == 2:
                                st.markdown("##### 🔹 Axis of Symmetry")
                                a_coeff = expr.coeff(indep_var, 2)
                                b_coeff = expr.coeff(indep_var, 1)
                                axis = -b_coeff / (2 * a_coeff)
                                st.latex(rf"{sp.latex(indep_var)} = {sp.latex(axis)}")
                        except Exception:
                            pass

                        # ---------------------------------------------------
                        # 8. RANGE
                        # ---------------------------------------------------
                        st.markdown("##### 🔹 Range")
                        try:
                            if sp.degree(expr, indep_var) in [0, 1]:
                                st.latex(r"\text{Range: } (-\infty, \infty)")
                            elif turning_points:
                                deg = sp.degree(expr, indep_var)
                                lead_coeff = expr.coeff(indep_var, deg)
                                y_min, y_max = min(turning_points), max(turning_points)
                                if deg % 2 == 0:
                                    if lead_coeff > 0: st.latex(rf"{sp.latex(out_var)} \ge {sp.latex(y_min)}")
                                    else: st.latex(rf"{sp.latex(out_var)} \le {sp.latex(y_max)}")
                                else: st.latex(r"\text{Range: } (-\infty, \infty)")
                        except Exception:
                            st.write("Determined by function type.")

                        # ---------------------------------------------------
                        # 9. ASYMPTOTES
                        # ---------------------------------------------------
                        st.markdown("##### 🔹 Asymptotes")
                        try:
                            num, den = sp.fraction(expr)
                            vert_asym = sp.solve(den, indep_var) if den != 1 else []
                            for va in vert_asym:
                                if va.is_real:
                                    st.latex(rf"{sp.latex(indep_var)} = {sp.latex(va)}")

                            horiz_pos = sp.limit(expr, indep_var, sp.oo)
                            horiz_neg = sp.limit(expr, indep_var, -sp.oo)
                            if horiz_pos.is_finite: st.latex(rf"{sp.latex(out_var)} = {sp.latex(horiz_pos)}")
                            if horiz_neg.is_finite: st.latex(rf"{sp.latex(out_var)} = {sp.latex(horiz_neg)}")
                        except Exception:
                            pass
                    else:
                        st.info(
                            f"This relation is not a function of ${sp.latex(plot_horiz)}$ in the usual "
                            "sense (it fails the vertical line test) — showing its intercepts, domain "
                            "and graph below instead."
                        )
                        relation_eq = sp.Eq(lhs_expr, rhs_expr)

                        st.markdown(f"##### 🔹 {sp.latex(plot_vert)}-intercept(s)")
                        try:
                            y_ints = [r for r in sp.solve(relation_eq.subs(plot_horiz, 0), plot_vert) if r.is_real]
                            if y_ints:
                                for yi in y_ints:
                                    st.latex(rf"({sp.latex(plot_horiz)}=0,\ {sp.latex(plot_vert)}={sp.latex(yi)})")
                            else:
                                st.latex(r"\text{No real intercepts}")
                        except Exception:
                            st.write("Could not determine intercepts symbolically.")

                        st.markdown(f"##### 🔹 {sp.latex(plot_horiz)}-intercept(s)")
                        try:
                            x_ints = [r for r in sp.solve(relation_eq.subs(plot_vert, 0), plot_horiz) if r.is_real]
                            if x_ints:
                                for xi in x_ints:
                                    st.latex(rf"({sp.latex(xi)},\ {sp.latex(plot_vert)}=0)")
                            else:
                                st.latex(r"\text{No real intercepts}")
                        except Exception:
                            st.write("Could not determine intercepts symbolically.")

                        if branches:
                            try:
                                domain = sp.Union(*[
                                    sp.calculus.util.continuous_domain(b, plot_horiz, sp.S.Reals)
                                    for b in branches
                                ])
                                st.markdown(f"##### 🔹 Domain (in terms of {sp.latex(plot_horiz)})")
                                st.latex(r"\text{Domain: } " + sp.latex(domain))
                            except Exception:
                                pass

                    # ---------------------------------------------------
                    # 📉 SKETCH OF THE GRAPH (SMART MODE, generic variables)
                    # ---------------------------------------------------
                    st.markdown("##### 📉 Sketch of the Graph")

                    horiz_vals = np.linspace(-10, 10, 4000)
                    fig, ax = plt.subplots(figsize=(7, 5))

                    if not branches:
                        st.warning("No real solutions exist for this relation, so it cannot be graphed.")
                    else:
                        expr_str_for_type = str(branches[0])
                        is_trig = any(f in expr_str_for_type for f in ["sin", "cos", "tan", "sec", "csc"])

                        if len(branches) > 1:
                            # Multiple branches, e.g. x=y**2 -> y=+-sqrt(x)
                            for sol in branches:
                                f = sp.lambdify(plot_horiz, sol, "numpy")
                                vert_vals = f(horiz_vals)
                                vert_vals = np.where(np.isfinite(vert_vals), vert_vals, np.nan)
                                ax.plot(horiz_vals, vert_vals, linewidth=2)
                        elif is_trig:
                            f = sp.lambdify(plot_horiz, branches[0], "numpy")
                            vert_vals = f(horiz_vals)
                            vert_vals = np.where(np.abs(vert_vals) > 50, np.nan, vert_vals)
                            ax.plot(horiz_vals, vert_vals, linewidth=2)
                        else:
                            plot_expr = branches[0]
                            f = sp.lambdify(plot_horiz, plot_expr, "numpy")
                            vert_vals = f(horiz_vals)

                            num, den = sp.fraction(plot_expr)
                            vertical_asymptotes = []
                            if den != 1:
                                vertical_asymptotes = [float(v) for v in sp.solve(den, plot_horiz) if v.is_real]
                            for va in vertical_asymptotes:
                                vert_vals[np.abs(horiz_vals - va) < 0.05] = np.nan
                                ax.axvline(va, linestyle="--", color="red", linewidth=2)

                            lim_pos = sp.limit(plot_expr, plot_horiz, sp.oo)
                            lim_neg = sp.limit(plot_expr, plot_horiz, -sp.oo)
                            if lim_pos.is_real and lim_pos.is_finite:
                                ax.axhline(float(lim_pos), linestyle="--", color="red", linewidth=2)
                            if lim_neg.is_real and lim_neg.is_finite:
                                ax.axhline(float(lim_neg), linestyle="--", color="red", linewidth=2)

                            vert_vals = np.where(np.isfinite(vert_vals), vert_vals, np.nan)
                            ax.plot(horiz_vals, vert_vals, linewidth=2)

                    ax.axhline(0, color="black", linewidth=0.8)
                    ax.axvline(0, color="black", linewidth=0.8)
                    ax.grid(True, linestyle="--", alpha=0.5)

                    ax.set_xlabel(str(plot_horiz))
                    ax.set_ylabel(str(plot_vert))
                    ax.set_title("Sketch of the Function")

                    st.pyplot(fig, use_container_width=True)



                except Exception as e:
                    st.error("Could not parse the function for graphing.")
                    st.caption(str(e))



            # =====================================================
            # PAPER 2
            # =====================================================
            elif topic == "Analytical Geometry":
                st.markdown("### 📏 Points, Distance, Gradient & Line Equation")

                # Look for two "(x,y)" coordinate pairs typed anywhere in the
                # question text, e.g. "Find the distance between A(1,2) and B(4,6)".
                coord_matches = re.findall(r"\(\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)", question)

                col1, col2 = st.columns(2)
                with col1:
                    x1 = st.number_input("x₁", value=float(coord_matches[0][0]) if len(coord_matches) >= 1 else 1.0)
                    y1 = st.number_input("y₁", value=float(coord_matches[0][1]) if len(coord_matches) >= 1 else 2.0)
                with col2:
                    x2 = st.number_input("x₂", value=float(coord_matches[1][0]) if len(coord_matches) >= 2 else 4.0)
                    y2 = st.number_input("y₂", value=float(coord_matches[1][1]) if len(coord_matches) >= 2 else 6.0)

                st.markdown(f"**Points:** $A({_fmt_num(x1)},{_fmt_num(y1)})$ and $B({_fmt_num(x2)},{_fmt_num(y2)})$")

                st.markdown("**Step 1: Distance**")
                st.latex(r"d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}")
                d = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                st.latex(rf"d=\sqrt{{({_fmt_num(x2)}-{_fmt_num(x1)})^2+({_fmt_num(y2)}-{_fmt_num(y1)})^2}}={round(d, 3)}")

                st.markdown("**Step 2: Midpoint**")
                st.latex(r"M=\left(\frac{x_1+x_2}{2},\frac{y_1+y_2}{2}\right)")
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                st.latex(rf"M=({_fmt_num(mx)},{_fmt_num(my)})")

                st.markdown("**Step 3: Gradient**")
                st.latex(r"m=\frac{y_2-y_1}{x_2-x_1}")
                if x2 != x1:
                    m = (y2 - y1) / (x2 - x1)
                    st.latex(rf"m=\frac{{{_fmt_num(y2)}-{_fmt_num(y1)}}}{{{_fmt_num(x2)}-{_fmt_num(x1)}}}={round(m, 3)}")

                    st.markdown("**Step 4: Equation of the line** $AB$")
                    st.latex(r"y-y_1=m(x-x_1)")
                    c = y1 - m * x1
                    sign = "+" if c >= 0 else "-"
                    st.latex(rf"y={round(m,3)}x{sign}{round(abs(c),3)}")
                else:
                    st.warning("The line through A and B is vertical (undefined gradient).")
                    st.latex(rf"x={_fmt_num(x1)}")

                st.markdown("##### 📉 Plot")
                fig, ax = plt.subplots(figsize=(5.5, 5))
                ax.plot([x1, x2], [y1, y2], "o-", color="#2563eb", linewidth=2, markersize=8)
                ax.annotate(f"A({_fmt_num(x1)},{_fmt_num(y1)})", (x1, y1), textcoords="offset points", xytext=(8, 8))
                ax.annotate(f"B({_fmt_num(x2)},{_fmt_num(y2)})", (x2, y2), textcoords="offset points", xytext=(8, 8))
                ax.plot(mx, my, "rs")
                ax.annotate(f"M({_fmt_num(mx)},{_fmt_num(my)})", (mx, my), textcoords="offset points", xytext=(8, -12), color="red")
                ax.axhline(0, color="black", linewidth=0.8)
                ax.axvline(0, color="black", linewidth=0.8)
                ax.grid(True, linestyle="--", alpha=0.5)
                ax.set_aspect("equal", adjustable="datalim")
                st.pyplot(fig, use_container_width=True)

            elif topic == "Trigonometry":
                st.markdown("### 📐 Trigonometry")

                q_lower = question.lower()
                is_equation = ("=" in question) and any(f in q_lower for f in ["sin", "cos", "tan"])

                if is_equation:
                    try:
                        eq_clean = question.replace("^", "**")

                        domain_match = re.search(
                            r"(-?\d+(?:\.\d+)?)\s*(?:<=|≤)\s*[a-zA-Zθ]+\s*(?:<=|≤)\s*(-?\d+(?:\.\d+)?)",
                            eq_clean,
                        )
                        if domain_match:
                            lo, hi = float(domain_match.group(1)), float(domain_match.group(2))
                            eq_only = eq_clean[:domain_match.start()] + eq_clean[domain_match.end():]
                        else:
                            lo, hi = 0.0, 360.0
                            eq_only = eq_clean

                        eq_only = re.sub(r"(?i)\bsolve\b(\s+for\s+[a-zA-Z]+)?", "", eq_only)
                        eq_only = re.sub(r"(?i)\bfor\b", "", eq_only)
                        eq_only = eq_only.strip(" ,:")
                        eq_only = re.sub(r'(\d)([a-zA-Z\(])', r'\1*\2', eq_only)

                        detected_vars = detect_variables(eq_only)
                        var_name = detected_vars[0] if detected_vars else "x"
                        xvar = sp.symbols(var_name)
                        symbols_dict = {var_name: xvar}

                        lhs_str, rhs_str = eq_only.split("=")
                        lhs = safe_parse(lhs_str, symbols_dict)
                        rhs = safe_parse(rhs_str, symbols_dict)

                        st.markdown("**Step 1: Write the equation**")
                        st.latex(sp.latex(sp.Eq(lhs, rhs)))

                        # Trig functions need radians internally, but NSC
                        # questions are always posed in degrees — substituting
                        # x -> x*pi/180 lets sympy solve/period-detect directly
                        # in "x = degrees" units, so no extra conversion needed
                        # on the solutions it returns.
                        expr_deg = lhs - rhs
                        expr_rad = expr_deg.subs(xvar, xvar * sp.pi / 180)

                        base_solutions = [s for s in sp.solve(sp.Eq(expr_rad, 0), xvar) if s.is_real]
                        period = sp.periodicity(expr_rad, xvar)
                        period_deg = float(period) if period else 360.0

                        st.markdown(
                            f"**Step 2: Find all solutions in the interval** "
                            f"${lo:g}^\\circ \\le {var_name} \\le {hi:g}^\\circ$ "
                            f"(period $={period_deg:g}^\\circ$)"
                        )

                        all_solutions = set()
                        for base in base_solutions:
                            base_deg = float(base)
                            k = int(np.floor((lo - base_deg) / period_deg)) - 1
                            while True:
                                candidate = base_deg + k * period_deg
                                if candidate > hi + 1e-6:
                                    break
                                if candidate >= lo - 1e-6:
                                    all_solutions.add(round(candidate, 2))
                                k += 1

                        if all_solutions:
                            sol_list = sorted(all_solutions)
                            for s in sol_list:
                                st.latex(rf"{var_name}={s:g}^\circ")
                            st.success("🏁 Final Answer: " + ", ".join(f"{s:g}°" for s in sol_list))
                        else:
                            st.error("No solutions found in the given interval.")

                    except Exception as e:
                        st.error("Could not solve this trigonometric equation.")
                        st.caption(str(e))

                else:
                    st.markdown("#### Trigonometric Ratio Calculator")
                    angle_match = re.search(r"-?\d+\.?\d*", question)
                    angle = st.number_input(
                        "Angle (degrees)", value=float(angle_match.group()) if angle_match else 30.0
                    )
                    rad = np.deg2rad(angle)

                    st.latex(rf"\sin({angle:g}^\circ) = {round(np.sin(rad),3)}")
                    st.latex(rf"\cos({angle:g}^\circ) = {round(np.cos(rad),3)}")
                    st.latex(rf"\tan({angle:g}^\circ) = {round(np.tan(rad),3)}")

                    st.markdown("##### 🔵 Unit Circle")
                    fig, ax = plt.subplots(figsize=(4, 4))
                    theta = np.linspace(0, 2 * np.pi, 200)
                    ax.plot(np.cos(theta), np.sin(theta), color="#94a3b8")
                    ax.plot([0, np.cos(rad)], [0, np.sin(rad)], "o-", color="#2563eb", linewidth=2)
                    ax.axhline(0, color="black", linewidth=0.8)
                    ax.axvline(0, color="black", linewidth=0.8)
                    ax.set_aspect("equal")
                    ax.set_title(f"{angle:g}° on the unit circle")
                    st.pyplot(fig, use_container_width=True)

            elif topic == "Statistics":
                st.markdown("### 📊 Descriptive Statistics")

                default_data = question if re.search(r"\d", question) else "2,4,6,8,10,12"
                data = st.text_input("Enter data (comma-separated)", default_data)
                values = sorted(float(v) for v in re.findall(r"-?\d+\.?\d*", data))

                if len(values) < 2:
                    st.warning("Please enter at least two numbers, separated by commas.")
                else:
                    n_vals = len(values)
                    mean = float(np.mean(values))
                    median = float(np.median(values))
                    counts = {v: values.count(v) for v in set(values)}
                    max_count = max(counts.values())
                    modes = sorted(v for v, c in counts.items() if c == max_count) if max_count > 1 else []
                    variance = float(np.var(values))
                    std_dev = float(np.std(values))
                    q1 = float(np.percentile(values, 25))
                    q3 = float(np.percentile(values, 75))

                    def _fmt(v):
                        return str(int(v)) if float(v).is_integer() else f"{v:.4g}"

                    st.markdown("**Step 1: Arrange the data in ascending order**")
                    st.latex(",\\;".join(_fmt(v) for v in values))

                    st.markdown("**Step 2: Mean**")
                    st.latex(r"\bar{x}=\frac{\sum x}{n}")
                    st.latex(rf"\bar{{x}}=\frac{{{_fmt(sum(values))}}}{{{n_vals}}}={_fmt(mean)}")

                    st.markdown("**Step 3: Median**")
                    st.latex(rf"\text{{Median}}={_fmt(median)}")

                    st.markdown("**Step 4: Mode**")
                    if modes:
                        st.latex(r"\text{Mode}=" + ",\\;".join(_fmt(m) for m in modes))
                    else:
                        st.latex(r"\text{No mode — every value occurs once}")

                    st.markdown("**Step 5: Range**")
                    st.latex(rf"\text{{Range}}={_fmt(max(values))}-{_fmt(min(values))}={_fmt(max(values)-min(values))}")

                    st.markdown("**Step 6: Variance and Standard Deviation**")
                    st.latex(r"\sigma^2=\frac{\sum(x-\bar{x})^2}{n}")
                    st.latex(rf"\sigma^2={_fmt(variance)}")
                    st.latex(r"\sigma=\sqrt{\sigma^2}")
                    st.latex(rf"\sigma={_fmt(std_dev)}")

                    st.markdown("**Step 7: Five-number summary**")
                    st.latex(
                        rf"\text{{Min}}={_fmt(min(values))},\;Q_1={_fmt(q1)},\;"
                        rf"\text{{Median}}={_fmt(median)},\;Q_3={_fmt(q3)},\;\text{{Max}}={_fmt(max(values))}"
                    )

                    st.markdown("##### 📦 Box-and-Whisker Diagram")
                    fig, ax = plt.subplots(figsize=(6, 2))
                    ax.boxplot(values, vert=False, widths=0.6, patch_artist=True,
                               boxprops=dict(facecolor="#93c5fd"))
                    ax.set_yticks([])
                    ax.set_xlabel("Value")
                    st.pyplot(fig, use_container_width=True)

            elif topic == "Probability":
                st.markdown("### 🎲 Probability")

                result = interpret_probability_text(question)

                if result is None:
                    st.info(
                        "Couldn't automatically interpret this as a word problem — "
                        "enter favourable/total outcomes manually below, or try phrasing "
                        "like the examples shown above (e.g. dice, coins, or a bag of coloured balls)."
                    )
                    favourable = st.number_input("Favourable outcomes", 1)
                    total = st.number_input("Total outcomes", 6)
                    prob = favourable / total
                    st.latex(r"P(E)=\frac{n(E)}{n(S)}")
                    st.latex(rf"P(E)={round(prob,3)}")

                else:
                    kind = result["kind"]

                    if kind == "symbolic":
                        st.markdown("**Using the appropriate probability rule:**")
                        st.latex(result["formula"])
                        for step in result["steps"]:
                            st.latex(step)
                        st.success(f"🏁 P = {result['answer']:.4g}")

                    elif kind == "bag":
                        st.markdown("**Step 1: Identify the sample space**")
                        counts_str = ", ".join(f"{v} {k}" for k, v in result["counts"].items())
                        st.write(f"The bag/box contains: {counts_str} (total = {result['total']}).")
                        st.markdown(f"**Step 2: Favourable outcomes — {result['target']}**")
                        st.latex(r"P(E)=\frac{n(E)}{n(S)}")
                        st.latex(rf"P(\text{{{result['target']}}})=\frac{{{result['favourable']}}}{{{result['total']}}}={result['answer']:.4g}")
                        st.success(f"🏁 P({result['target']}) = {result['answer']:.4g}")

                        fig, ax = plt.subplots(figsize=(5, 3))
                        ax.bar(list(result["counts"].keys()), list(result["counts"].values()), color="#60a5fa")
                        ax.set_ylabel("Count")
                        ax.set_title("Contents of the bag/box")
                        st.pyplot(fig, use_container_width=True)

                    elif kind == "tree":
                        st.markdown("**Step 1: Draw a tree diagram for the two independent stages**")
                        st.latex(r"P(A \text{ and } B) = P(A)\times P(B)")
                        for step in result["steps"]:
                            st.latex(step)
                        st.success(f"🏁 P = {result['answer']:.4g}")

                        fig = draw_tree_diagram([("Die", list(range(1, 7))), ("Coin", ["H", "T"])])
                        st.pyplot(fig, use_container_width=True)

                    elif kind == "die":
                        fav = sorted(result["favourable_set"])
                        st.markdown("**Step 1: Sample space of a die**")
                        st.latex(r"S=\{1,2,3,4,5,6\}")
                        st.markdown("**Step 2: Favourable outcomes**")
                        st.latex(r"E=\{" + ",".join(map(str, fav)) + r"\}" if fav else r"E=\varnothing")
                        st.latex(r"P(E)=\frac{n(E)}{n(S)}")
                        st.latex(rf"P(E)=\frac{{{len(fav)}}}{{6}}={result['answer']:.4g}")
                        st.success(f"🏁 P(E) = {result['answer']:.4g}")

                    elif kind == "coins":
                        st.markdown("**Step 1: Sample space of two coins**")
                        st.latex(r"S=\{HH,HT,TH,TT\}")
                        st.markdown("**Step 2: Favourable outcomes**")
                        st.latex(r"E=\{" + ",".join(result["favourable"]) + r"\}")
                        st.latex(rf"P(E)=\frac{{{len(result['favourable'])}}}{{4}}={result['answer']:.4g}")
                        st.success(f"🏁 P(E) = {result['answer']:.4g}")

                    else:  # single coin
                        st.markdown("**Sample space:** $S=\\{H,T\\}$")
                        st.latex(r"P(E)=\frac12=0.5")
                        st.success("🏁 P(E) = 0.5")

            elif topic == "Euclidean Geometry":
                st.markdown("### ⚪ Euclidean Geometry")

                result = solve_euclidean_geometry(question)

                if result is None:
                    st.info(
                        "Type a question using keywords like 'angle at centre', "
                        "'angle at circumference', 'cyclic quadrilateral', or "
                        "'tangent chord' — or browse the theorem reference below."
                    )
                else:
                    kind = result["kind"]
                    if kind == "centre_circumference":
                        st.markdown("**Theorem:** The angle at the centre is twice the angle at the circumference subtended by the same arc.")
                        st.latex(r"\hat{O}=2\hat{C}")
                        if result["given"] == "centre":
                            st.latex(rf"\hat{{C}}=\frac{{{result['value']:g}^\circ}}{{2}}={result['answer']:g}^\circ")
                        else:
                            st.latex(rf"\hat{{O}}=2\times{result['value']:g}^\circ={result['answer']:g}^\circ")
                    elif kind == "cyclic_quad":
                        st.markdown("**Theorem:** Opposite angles of a cyclic quadrilateral are supplementary.")
                        st.latex(r"\hat{A}+\hat{C}=180^\circ")
                        st.latex(rf"\hat{{C}}=180^\circ-{result['value']:g}^\circ={result['answer']:g}^\circ")
                    else:
                        st.markdown("**Theorem (tan-chord):** The angle between a tangent and a chord equals the angle in the alternate segment.")
                        st.latex(rf"\text{{Angle in alternate segment}}={result['answer']:g}^\circ")

                    st.success(f"🏁 Answer: {result['answer']:g}°")
                    fig = draw_euclidean_diagram(kind)
                    st.pyplot(fig, use_container_width=True)

                with st.expander("📖 Circle Theorem Quick Reference"):
                    st.latex(r"\hat{O}=2\hat{C}\quad\text{angle at centre}=2\times\text{angle at circumference}")
                    st.latex(r"\hat{A}+\hat{C}=180^\circ\quad\text{opposite angles of a cyclic quadrilateral}")
                    st.latex(r"\text{Angles subtended by the same chord/arc in the same segment are equal}")
                    st.latex(r"\text{Tangent-chord angle}=\text{angle in the alternate segment}")
                    st.latex(r"\text{A line from the centre perpendicular to a chord bisects the chord}")

        except Exception as e:
            st.error("Invalid expression or input")
            st.caption(str(e))

# =====================================================
# OCR
# =====================================================
elif mode=="📷 OCR Question":
    st.title("📷 OCR Question")
    if not can_use_ocr(effective_tier):
        st.warning("📷 Photo upload & OCR is a Learner/Premium feature. Upgrade from the sidebar to unlock it.")
    else:
        img_file = st.file_uploader("Upload image", type=["png","jpg","jpeg"])
        if img_file:
            img = Image.open(img_file)
            st.image(img, use_column_width=True)
            raw = ocr_with_exponents(preprocess_image(img))
            cleaned = clean_for_sympy(raw)
            st.code(cleaned)
            if st.button("Transfer to Solver"):
                st.session_state.copied_text = cleaned

# =====================================================
# PDF
# =====================================================

elif mode=="📚 Past Papers (PDF)":
    st.title("📚 PDF Extractor")
    if not can_use_pdf(effective_tier):
        st.warning("📚 Past paper PDF extraction is a Learner/Premium feature. Upgrade from the sidebar to unlock it.")
    else:
        pdf = st.file_uploader("Upload PDF", type=["pdf"])
        if pdf:
            text = extract_pdf_text(pdf)
            edited = st.text_area("Extracted Text", text, height=300)
            if st.button("Transfer to Solver"):
                st.session_state.copied_text = edited

# =====================================================
# PROFILE
# =====================================================
elif mode=="🎯 Learner Profile":
    st.title("🎯 Learner Profile")
    learner = st.session_state.learner

    col1, col2 = st.columns(2)
    col1.metric("Questions Solved", learner["solved"])
    col2.metric("Marks Earned", learner["Marks"])

    solved = learner["solved"]
    if solved >= 30:
        badge = "🥇 Gold Achiever"
    elif solved >= 15:
        badge = "🥈 Silver Achiever"
    elif solved >= 5:
        badge = "🥉 Bronze Achiever"
    else:
        badge = "🌱 Getting Started"
    st.markdown(f"#### Badge: {badge}")
    next_milestone = next((m for m in (5, 15, 30) if solved < m), None)
    if next_milestone:
        st.progress(min(solved / next_milestone, 1.0))
        st.caption(f"{next_milestone - solved} more solved questions to your next badge.")

    topic_counts = learner.get("topic_counts", {})
    if topic_counts:
        st.markdown("#### 📊 Questions solved per topic")
        fig, ax = plt.subplots(figsize=(6, 3))
        topics_list = list(topic_counts.keys())
        bar_colors = [TOPIC_COLORS.get(t, _DEFAULT_TOPIC_COLOR) for t in topics_list]
        ax.bar(topics_list, list(topic_counts.values()), color=bar_colors)
        ax.set_ylabel("Solved")
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        st.pyplot(fig, use_container_width=True)
    else:
        st.info("Solve some practice questions to see your progress here!")

    st.markdown("#### 🕒 Recent Activity")
    recent = get_recent_solved(auth_user["id"])
    if recent:
        for r in recent:
            source_label = "AI Tutor" if r["source"] == "ai_tutor" else "Practice"
            when = r["solved_at"].strftime("%d %b %Y, %H:%M") if r["solved_at"] else ""
            paper_topic = " · ".join(p for p in (r["paper"], r["topic"]) if p)
            st.caption(f"**{source_label}** — {paper_topic} — {when}")
            if r["question"]:
                st.code(r["question"], language=None)
    else:
        st.info("No solved-question history yet — this fills in as you use the AI Tutor or Practice Questions.")

# =====================================================
# FORMULA SHEET
# =====================================================
elif mode == "📏 Formula Sheet":
    st.title("📏 Complete Matric Formula Sheet")
    st.info("Grouped according to NSC Papers")


    col1, col2 = st.columns(2)

    with col1:
        st.header("📑 Paper 1")
        with st.expander("Algebra & Sequences", expanded=True):
            st.latex(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
            st.latex(r"T_n = a + (n-1)d")
            st.latex(r"S_n = \frac{n}{2}[2a + (n-1)d]")
            st.latex(r"T_n = ar^{n-1}")
            st.latex(r"S_\infty = \frac{a}{1-r}")

        with st.expander("Financial Mathematics"):
            st.latex(r"A = P(1 + i)^n")
            st.latex(r"A = P(1 + ni)")
            st.latex(r"F = \frac{x[(1+i)^n - 1]}{i}")
            st.latex(r"P = \frac{x[1-(1+i)^{-n}]}{i}")

        with st.expander("Calculus"):
            st.latex(r"f'(x)=\lim_{h\to0}\frac{f(x+h)-f(x)}{h}")
            st.latex(r"\frac{d}{dx}[x^n]=nx^{n-1}")

    with col2:
        st.header("📑 Paper 2")
        with st.expander("Analytical Geometry", expanded=True):
            st.latex(r"d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}")
            st.latex(r"(x-a)^2+(y-b)^2=r^2")

        with st.expander("Trigonometry"):
            st.latex(r"\frac{a}{\sin A}=\frac{b}{\sin B}")
            st.latex(r"a^2=b^2+c^2-2bc\cos A")

        with st.expander("Statistics & Probability"):
            st.latex(r"\bar{x}=\frac{\sum x}{n}")
            st.latex(r"\sigma^2=\frac{\sum(x-\bar{x})^2}{n}")
            st.latex(r"P(A)=\frac{n(A)}{n(S)}")

# =====================================================
# HOME DASHBOARD
# =====================================================
else:
    st.title(f"👋 Welcome back, {auth_user['name'].split(' ')[0]}!")
    st.caption("Pick where you'd like to start.")

    HOME_TILES = [
        {"mode": "🧮 AI Tutor", "icon": "🧮", "title": "AI Tutor",
         "desc": "Get any Grade 12 question solved step by step.",
         "color": "#2a78d6"},
        {"mode": "📝 Practice Questions", "icon": "📝", "title": "Practice Questions",
         "desc": "Work through curated questions with hints and full solutions.",
         "color": "#eb6834"},
        {"mode": "📷 OCR Question", "icon": "📷", "title": "OCR Question",
         "desc": "Snap a photo of a question and let us read it for you.",
         "color": "#1baf7a"},
        {"mode": "📚 Past Papers (PDF)", "icon": "📚", "title": "Past Papers",
         "desc": "Upload a past paper PDF and pull questions straight from it.",
         "color": "#eda100"},
        {"mode": "🎯 Learner Profile", "icon": "🎯", "title": "Learner Profile",
         "desc": "Track your progress, badges, and solved-question history.",
         "color": "#4a3aa7"},
        {"mode": "📏 Formula Sheet", "icon": "📏", "title": "Formula Sheet",
         "desc": "The complete NSC formula sheet, organised by paper.",
         "color": "#e34948"},
    ]

    for row_start in range(0, len(HOME_TILES), 3):
        row = HOME_TILES[row_start:row_start + 3]
        cols = st.columns(3)
        for col, tile in zip(cols, row):
            with col:
                st.markdown(
                    f"""
                    <div class="subject-tile" style="--tile-color:{tile['color']};">
                        <div class="tile-icon">{tile['icon']}</div>
                        <p class="tile-title">{tile['title']}</p>
                        <p class="tile-desc">{tile['desc']}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Open →", key=f"home_tile_{tile['mode']}"):
                    st.session_state["pending_nav"] = tile["mode"]
                    st.rerun()

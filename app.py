import os
from dotenv import load_dotenv
load_dotenv()

import re
import sympy as sp
import streamlit as st
import streamlit.components.v1 as components
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
from backend.math_utils import safe_parse, detect_variables, _fmt_num
from backend.solver import (
    solve_algebra, solve_sequences, solve_financial_mathematics, solve_calculus,
    solve_functions_graphs, solve_analytical_geometry, solve_trigonometry,
    solve_statistics, solve_probability, solve_euclidean_geometry_topic,
)
from backend.ocr import preprocess_image, ocr_with_exponents, clean_for_sympy
from backend.pdf_extract import extract_pdf_text

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
# PWA SUPPORT (installable on Android/iOS home screens)
# =====================================================
# Streamlit has no built-in way to add tags to <head> or host static
# assets, so: (1) ./static/ is served at /app/static/<file> via
# enableStaticServing in .streamlit/config.toml, and (2) this component
# runs a script that reaches into the PARENT document (components.v1.html
# renders in a same-origin iframe, so window.parent.document is reachable)
# to attach the manifest link, theme-color/apple-touch-icon meta tags, and
# register the service worker. Guarded by element IDs so re-running this
# on every Streamlit rerun doesn't keep appending duplicate tags.
components.html(
    """
    <script>
    (function() {
        try {
            var doc = window.parent.document;
            function addOnce(id, build) {
                if (!doc.getElementById(id)) {
                    var el = build();
                    el.id = id;
                    doc.head.appendChild(el);
                }
            }
            addOnce('malita-manifest', function() {
                var link = doc.createElement('link');
                link.rel = 'manifest';
                link.href = '/app/static/manifest.json';
                return link;
            });
            addOnce('malita-theme-color', function() {
                var meta = doc.createElement('meta');
                meta.name = 'theme-color';
                meta.content = '#2a78d6';
                return meta;
            });
            addOnce('malita-apple-icon', function() {
                var link = doc.createElement('link');
                link.rel = 'apple-touch-icon';
                link.href = '/app/static/icon-192.png';
                return link;
            });
            addOnce('malita-apple-capable', function() {
                var meta = doc.createElement('meta');
                meta.name = 'apple-mobile-web-app-capable';
                meta.content = 'yes';
                return meta;
            });
            if (window.parent.navigator.serviceWorker) {
                window.parent.navigator.serviceWorker.register('/app/static/service-worker.js');
            }
        } catch (e) {
            console.error('Malita PWA setup failed:', e);
        }
    })();
    </script>
    """,
    height=0,
)

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

# Safe math expression parsing (safe_parse/detect_variables/_fmt_num) now
# lives in backend/math_utils.py (imported above) so api_server.py can
# share the exact same parsing code as the native app comes online.

def _render_image_step(data_uri):
    # StepRecorder.pyplot() always encodes as "data:image/png;base64,...."
    # so both Streamlit (here) and the API (sends the data URI as-is) can
    # share the exact same encoding step.
    b64_data = data_uri.split(",", 1)[1]
    st.image(base64.b64decode(b64_data), use_column_width=True)


def render_steps(steps):
    """Render a list of structured steps (as returned by backend/solver.py
    solve_* functions) as Streamlit widgets. Keeps the AI Tutor's on-screen
    output identical to before the solving logic moved into backend/ -
    only the "sink" changed, not the content or order."""
    _RENDERERS = {
        "markdown": st.markdown,
        "latex": st.latex,
        "write": st.write,
        "info": st.info,
        "warning": st.warning,
        "error": st.error,
        "success": st.success,
        "caption": st.caption,
        "image": _render_image_step,
    }
    for step in steps:
        _RENDERERS[step["type"]](step["content"])

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
   colour per tile so they read like a subject/topic picker rather than a
   single flat-blue app. Each tile gets a fixed class (.tile-c1 .. .tile-c6)
   with its own hardcoded background - not a CSS custom property - so the
   colour can never be silently dropped by a browser/host that mishandles
   inline "style" custom properties. */
.subject-tile {
    position: relative;
    border-radius: 20px;
    padding: 1.4rem 1.2rem;
    color: white;
    box-shadow: 0 10px 22px rgba(0,0,0,0.12);
    margin-bottom: 0.6rem;
    overflow: hidden;
}
.tile-c1 { background: #2a78d6; }
.tile-c2 { background: #eb6834; }
.tile-c3 { background: #1baf7a; }
.tile-c4 { background: #eda100; }
.tile-c5 { background: #4a3aa7; }
.tile-c6 { background: #e34948; }

.subject-tile .tile-icon { font-size: 2.2rem; position: relative; z-index: 1; }
.subject-tile .tile-title { font-size: 1.15rem; font-weight: 700; margin: 0.3rem 0 0.2rem 0; position: relative; z-index: 1; }
.subject-tile .tile-desc { font-size: 0.85rem; opacity: 0.92; margin: 0; position: relative; z-index: 1; }
.subject-tile .tile-illustration {
    position: absolute;
    right: -10px;
    bottom: -10px;
    opacity: 0.16;
    z-index: 0;
}

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
    "🏠 Home",
    "🧮 AI Tutor",
    "📝 Practice Questions",
    "📷 OCR Question",
    "📚 Past Papers (PDF)",
    "🎯 Learner Profile",
    "📏 Formula Sheet",
]
_radio_kwargs = {}
if "nav_mode" not in st.session_state:
    # Passing BOTH index= and a pre-existing session_state["nav_mode"] (set
    # above whenever a Home-tile click just fired) makes Streamlit warn that
    # the widget "was created with a default value but also had its value
    # set via the Session State API" - so only pass index the very first
    # time this widget renders for a session, before nav_mode exists at all.
    # That first-render default is what makes Home the landing page.
    _radio_kwargs["index"] = _NAV_OPTIONS.index("🏠 Home")

mode = st.sidebar.radio(
    "Choose Mode",
    _NAV_OPTIONS,
    key="nav_mode",
    **_radio_kwargs,
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
                render_steps(solve_algebra(question))

            elif topic == "Sequences":
                render_steps(solve_sequences(question))

            elif topic == "Financial Mathematics":
                render_steps(solve_financial_mathematics(question))

            elif topic == "Calculus":
                render_steps(solve_calculus(question))

            elif topic == "Functions & Graphs":
                render_steps(solve_functions_graphs(question))

            elif topic == "Analytical Geometry":
                render_steps(solve_analytical_geometry(question))

            elif topic == "Trigonometry":
                render_steps(solve_trigonometry(question))

            elif topic == "Statistics":
                render_steps(solve_statistics(question))

            elif topic == "Probability":
                render_steps(solve_probability(question))

            elif topic == "Euclidean Geometry":
                render_steps(solve_euclidean_geometry_topic(question))

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
            text = extract_pdf_text(pdf.read())
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

    # Small flat-style watermark illustrations (plain inline SVG, no external
    # images/fonts needed) so each tile carries a subject-relevant picture
    # rather than colour alone.
    _SVG_TUTOR = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <circle cx="30" cy="28" r="13"/>
        <path d="M12 78 C12 56 20 47 30 47 C40 47 48 56 48 78 Z"/>
        <rect x="52" y="15" width="36" height="24" rx="8"/>
        <path d="M60 39 L56 48 L68 39 Z"/>
        </svg>"""
    _SVG_PENCIL_NOTES = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <rect x="20" y="15" width="50" height="65" rx="4"/>
        <rect x="28" y="28" width="34" height="6" rx="2" fill-opacity="0.5"/>
        <rect x="28" y="40" width="34" height="6" rx="2" fill-opacity="0.5"/>
        <rect x="28" y="52" width="20" height="6" rx="2" fill-opacity="0.5"/>
        <path d="M60 60 L80 40 L88 48 L68 68 L58 70 Z"/>
        </svg>"""
    _SVG_CAMERA = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <rect x="10" y="30" width="80" height="55" rx="8"/>
        <rect x="35" y="18" width="30" height="14" rx="4"/>
        <circle cx="50" cy="58" r="18" fill="none" stroke="white" stroke-width="6"/>
        </svg>"""
    _SVG_BOOKS = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <rect x="15" y="65" width="70" height="12" rx="2"/>
        <rect x="20" y="50" width="60" height="12" rx="2"/>
        <rect x="25" y="35" width="50" height="12" rx="2"/>
        </svg>"""
    _SVG_PROGRESS = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <rect x="15" y="55" width="14" height="30"/>
        <rect x="35" y="40" width="14" height="45"/>
        <rect x="55" y="25" width="14" height="60"/>
        <path d="M80 15 L84 23 L93 24 L86.5 30 L88 39 L80 34.5 L72 39 L73.5 30 L67 24 L76 23 Z"/>
        </svg>"""
    _SVG_RULER = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <rect x="10" y="65" width="80" height="16" rx="2" transform="rotate(-8 50 73)"/>
        <rect x="15" y="15" width="10" height="55" rx="2" transform="rotate(20 20 42)"/>
        </svg>"""

    HOME_TILES = [
        {"mode": "🧮 AI Tutor", "icon": "🧮", "title": "AI Tutor",
         "desc": "Get any Grade 12 question solved step by step.",
         "css_class": "tile-c1", "illustration": _SVG_TUTOR},
        {"mode": "📝 Practice Questions", "icon": "📝", "title": "Practice Questions",
         "desc": "Work through curated questions with hints and full solutions.",
         "css_class": "tile-c2", "illustration": _SVG_PENCIL_NOTES},
        {"mode": "📷 OCR Question", "icon": "📷", "title": "OCR Question",
         "desc": "Snap a photo of a question and let us read it for you.",
         "css_class": "tile-c3", "illustration": _SVG_CAMERA},
        {"mode": "📚 Past Papers (PDF)", "icon": "📚", "title": "Past Papers",
         "desc": "Upload a past paper PDF and pull questions straight from it.",
         "css_class": "tile-c4", "illustration": _SVG_BOOKS},
        {"mode": "🎯 Learner Profile", "icon": "🎯", "title": "Learner Profile",
         "desc": "Track your progress, badges, and solved-question history.",
         "css_class": "tile-c5", "illustration": _SVG_PROGRESS},
        {"mode": "📏 Formula Sheet", "icon": "📏", "title": "Formula Sheet",
         "desc": "The complete NSC formula sheet, organised by paper.",
         "css_class": "tile-c6", "illustration": _SVG_RULER},
    ]

    for row_start in range(0, len(HOME_TILES), 3):
        row = HOME_TILES[row_start:row_start + 3]
        cols = st.columns(3)
        for col, tile in zip(cols, row):
            with col:
                st.markdown(
                    f"""
                    <div class="subject-tile {tile['css_class']}">
                        {tile['illustration']}
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

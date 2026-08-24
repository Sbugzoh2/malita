import os
from dotenv import load_dotenv
load_dotenv()

import re
import sympy as sp
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import numpy as np
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
    create_password_reset, reset_password, cancel_subscription, create_api_token,
)
from backend.email_util import send_email
from backend.tiers import TIER_CONFIG, TIER_ORDER, can_use_ocr, can_use_pdf, can_use_past_papers, can_use_llm_fallback, daily_limit
from backend.usage import can_solve, record_solve, get_today_count, reset_today_usage
from backend.records import record_solved_question, get_recent_solved, get_learner_stats
from backend.payfast import build_checkout_payload, build_checkout_redirect_snippet
from backend.math_utils import safe_parse, detect_variables, _fmt_num
from backend.solver import (
    solve_algebra, solve_sequences, solve_financial_mathematics, solve_calculus,
    solve_functions_graphs, solve_analytical_geometry, solve_trigonometry,
    solve_statistics, solve_probability, solve_euclidean_geometry_topic,
    steps_contain_error,
)
from backend.practice import practice_data, check_practice_answer
from backend.past_papers import list_past_papers, get_past_paper_file, add_past_paper, delete_past_paper
from backend.llm_tutor import solve_with_llm, solve_full_paper
from backend.llm_ocr import solve_photo_with_llm, transcribe_pdf_with_llm

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8501")
APP_WEBHOOK_URL = os.environ.get("APP_WEBHOOK_URL", "http://localhost:8001/payfast/notify")
# api_server.py hosts the Terms/Privacy pages (one canonical copy the
# mobile app links to as well) - see api_server.py's /terms, /privacy.
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8002")

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
                    user = login_user(login_email, login_password, source="web")
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
            reg_id_number = st.text_input("ID number", key="reg_id_number", max_chars=13)
            st.caption("We use this to work out your date of birth automatically - no need to type it separately.")
            reg_password = st.text_input("Password", type="password", key="reg_pw")
            reg_password_confirm = st.text_input("Confirm password", type="password")
            st.caption(
                f"By creating an account you agree to Malita's [Terms & Conditions]({API_BASE_URL}/terms) "
                f"and [Privacy Policy]({API_BASE_URL}/privacy)."
            )
            submitted_reg = st.form_submit_button("Create Free Account")
            if submitted_reg:
                if reg_password != reg_password_confirm:
                    st.error("Passwords don't match.")
                else:
                    try:
                        user = register_user(
                            reg_name, reg_email, reg_password, reg_school,
                            province=reg_province, city_town=reg_city, id_number=reg_id_number,
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
    # Physical Sciences topics reuse the same 8 validated hues (cycled, not
    # invented) rather than introducing new, unchecked colors.
    "Momentum": "#2a78d6",
    "Vertical Projectile Motion": "#eb6834",
    "Work, Energy & Power": "#1baf7a",
    "Doppler Effect": "#eda100",
    "Electrostatics": "#e87ba4",
    "Electric Circuits": "#008300",
    "Electrodynamics": "#4a3aa7",
    "Stoichiometry": "#e34948",
    "Rate and Extent of Reaction": "#2a78d6",
    "Chemical Equilibrium": "#eb6834",
    "Acids and Bases": "#1baf7a",
    "Electrochemistry": "#eda100",
    "Organic Chemistry": "#e87ba4",
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
.tile-c7 { background: #0f9b8e; }

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
            st.info("Redirecting you to PayFast to complete payment…")
            components.html(build_checkout_redirect_snippet(payload), height=0)

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
    "🗄️ Past Papers Library",
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

st.sidebar.caption(
    f"[Terms & Conditions]({API_BASE_URL}/terms) · [Privacy Policy]({API_BASE_URL}/privacy)"
)

# =====================================================
# PRACTICE QUESTIONS
# =====================================================
if mode=="📝 Practice Questions":
    st.title("📝 Practice Questions")

    subject = st.radio("Subject", ["🧮 Mathematics", "🔬 Physical Sciences"], horizontal=True, key="pq_subject")
    subject_key = "Mathematics" if subject == "🧮 Mathematics" else "Physical Sciences"
    subject_data = practice_data[subject_key]

    if st.button("🎲 Surprise me with a random question"):
        rand_paper = random.choice(list(subject_data.keys()))
        rand_topic = random.choice(list(subject_data[rand_paper].keys()))
        rand_idx = random.randrange(len(subject_data[rand_paper][rand_topic]))
        st.session_state["pq_paper"] = rand_paper
        st.session_state["pq_topic"] = rand_topic
        st.session_state["pq_qnum"] = f"Q{rand_idx + 1}"
        st.rerun()

    paper_options = list(subject_data.keys())
    if st.session_state.get("pq_paper") not in paper_options:
        st.session_state["pq_paper"] = paper_options[0]
    paper = st.selectbox("Select Paper", paper_options, key="pq_paper")

    topic_options = list(subject_data[paper].keys())
    if st.session_state.get("pq_topic") not in topic_options:
        st.session_state["pq_topic"] = topic_options[0]
    topic = st.selectbox("Select Topic", topic_options, key="pq_topic")
    topic_badge(topic)

    questions = subject_data[paper][topic]
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

    attempt = st.text_input(
        "Type your final answer here (e.g. x=3 or x=2), then check it:",
        key=f"attempt_{q_key}",
    )

    col_check, col_solution = st.columns(2)
    with col_check:
        if st.button("✅ Check My Answer", key=f"check_{q_key}"):
            verdict = check_practice_answer(attempt, q_data["final_answer"])
            if verdict is True:
                st.success("Correct! 🎉")
                st.balloons()
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
            elif verdict is False:
                st.error("Not quite — try again, or reveal the solution below.")
            else:
                st.info("Type your final answer above (e.g. x=3 or x=2), then check it.")

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
        st.caption(
            "Marks are only added to your Learner Profile when you type the final answer above and "
            "check it correctly — viewing this solution is just for reference."
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



    input_method = st.radio(
        "How would you like to ask your question?",
        ["✍️ Type a Question", "📷 Photo", "📄 PDF Document"],
        horizontal=True,
    )

    if input_method == "✍️ Type a Question":
        subject = st.radio("Subject", ["🧮 Mathematics", "🔬 Physical Sciences"], horizontal=True, key="ai_tutor_subject")

        if subject == "🧮 Mathematics":
            paper = st.selectbox("Select Paper", ["Paper 1", "Paper 2"], key="ai_tutor_paper_maths")
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
        else:
            paper = st.selectbox("Select Paper", ["Physics", "Chemistry"], key="ai_tutor_paper_physci")
            if paper == "Physics":
                topic = st.selectbox(
                    "Topic",
                    ["Momentum", "Vertical Projectile Motion", "Work, Energy & Power", "Doppler Effect",
                     "Electrostatics", "Electric Circuits", "Electrodynamics"]
                )
            else:
                topic = st.selectbox(
                    "Topic",
                    ["Stoichiometry", "Rate and Extent of Reaction", "Chemical Equilibrium",
                     "Acids and Bases", "Electrochemistry", "Organic Chemistry"]
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
                "Momentum": ["A 0.5 kg ball at 4 m/s hits a stationary 1.5 kg ball. After, the 0.5 kg ball moves at 1 m/s. Find the other ball's velocity."],
                "Vertical Projectile Motion": ["A ball is thrown upward at 15 m/s. Find the maximum height reached (g=9.8 m/s^2)."],
                "Work, Energy & Power": ["A 60 kg cyclist speeds up from 4 m/s to 10 m/s. Find the increase in kinetic energy."],
                "Doppler Effect": ["An ambulance emits 600 Hz moving towards you at 30 m/s. Find the frequency heard (speed of sound = 340 m/s)."],
                "Electrostatics": ["Find the force between charges of +3x10^-6 C and +5x10^-6 C that are 0.2 m apart (k=9x10^9)."],
                "Electric Circuits": ["A 12 V battery with internal resistance 0.5 ohm is connected to a 5.5 ohm resistor. Find the current."],
                "Electrodynamics": ["A 200 turn coil has its flux change from 0.002 Wb to 0.008 Wb in 0.4 s. Find the induced emf."],
                "Stoichiometry": ["Calculate the number of moles in 11 g of CO2 (M(C)=12, M(O)=16)."],
                "Rate and Extent of Reaction": ["Concentration drops from 0.80 to 0.50 mol/dm^3 in 25 s. Find the average rate."],
                "Chemical Equilibrium": ["0.4 mol A and 0.6 mol B in a 2 dm^3 container at equilibrium for A<=>B. Calculate Kc."],
                "Acids and Bases": ["Calculate the pH of a solution with [H3O+]=1x10^-3 mol/dm^3."],
                "Electrochemistry": ["Given Cu2+/Cu, E°=+0.34 V and Zn2+/Zn, E°=-0.76 V, calculate E°cell."],
                "Organic Chemistry": ["Give the IUPAC name of CH3-CH2-CH2-CH3."],
            }
            for ex in EXAMPLE_QUESTIONS.get(topic, []):
                st.code(ex, language=None)

        # A plain `value=` text_input "locks in" whatever the learner types and
        # ignores value= on later reruns — so a Clear button that only resets
        # copied_text wouldn't actually clear text already typed. Using an
        # explicit key lets both Clear and a one-shot prefill update the box
        # reliably: copied_text is treated as a one-shot pending value,
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

        # Physical Sciences has no deterministic solver at all - every
        # question goes straight through the LLM, the same fallback path
        # Mathematics only reaches when its SymPy solver can't parse
        # something. That makes it a paid-tier feature, same as OCR/PDF -
        # see tiers.py's llm_fallback_enabled.
        if subject == "🔬 Physical Sciences" and not can_use_llm_fallback(effective_tier):
            st.warning("🔬 Physical Sciences is a Learner/Premium feature. Upgrade from the sidebar to unlock it.")
        else:
            solve_clicked = st.button("Solve")
            if solve_clicked and question:
                allowed, limit_message = can_solve(auth_user["id"], effective_tier)
                if not allowed:
                    st.warning(limit_message)
                    st.stop()
                record_solve(auth_user["id"])
                record_solved_question(auth_user["id"], "ai_tutor", paper=paper, topic=topic, question=question)

                if subject == "🔬 Physical Sciences":
                    with st.spinner("Working through it…"):
                        try:
                            render_steps(solve_with_llm(question, topic=topic, paper=paper, subject="Physical Sciences"))
                        except Exception as e:
                            st.error("Couldn't solve that question. Please try rephrasing it.")
                            st.caption(str(e))
                else:
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
                            steps = solve_algebra(question)

                        elif topic == "Sequences":
                            steps = solve_sequences(question)

                        elif topic == "Financial Mathematics":
                            steps = solve_financial_mathematics(question)

                        elif topic == "Calculus":
                            steps = solve_calculus(question)

                        elif topic == "Functions & Graphs":
                            steps = solve_functions_graphs(question)

                        elif topic == "Analytical Geometry":
                            steps = solve_analytical_geometry(question)

                        elif topic == "Trigonometry":
                            steps = solve_trigonometry(question)

                        elif topic == "Statistics":
                            steps = solve_statistics(question)

                        elif topic == "Probability":
                            steps = solve_probability(question)

                        elif topic == "Euclidean Geometry":
                            steps = solve_euclidean_geometry_topic(question)

                        else:
                            steps = []

                        # Every solve_* function catches its own parsing failures
                        # internally and returns an "error" step rather than raising -
                        # so a failed solve has to be detected here, not just in the
                        # except block below (which only ever catches the rarer case
                        # of something crashing before it can even build a step list).
                        if steps_contain_error(steps) and can_use_llm_fallback(effective_tier):
                            with st.spinner("That one needs a closer look — let me work through it…"):
                                try:
                                    steps = solve_with_llm(question, topic=topic, paper=paper, subject="Mathematics")
                                    render_steps(steps)
                                    st.caption("✨ Solved with AI assistance — this question needed extra help beyond our standard solver.")
                                except Exception:
                                    render_steps(steps)
                        else:
                            render_steps(steps)

                    except Exception as e:
                        if can_use_llm_fallback(effective_tier):
                            with st.spinner("That one needs a closer look — let me work through it…"):
                                try:
                                    render_steps(solve_with_llm(question, topic=topic, paper=paper, subject="Mathematics"))
                                    st.caption("✨ Solved with AI assistance — this question needed extra help beyond our standard solver.")
                                except Exception:
                                    st.error("Invalid expression or input")
                                    st.caption(str(e))
                        else:
                            st.error("Invalid expression or input")
                            st.caption(str(e))

    elif input_method == "📷 Photo":
        st.caption(
            "Take or upload a photo of one or more maths questions — Malita reads and solves "
            "every question directly here, no need to retype anything."
        )
        if not can_use_ocr(effective_tier):
            st.warning("📷 Photo upload & OCR is a Learner/Premium feature. Upgrade from the sidebar to unlock it.")
        else:
            img_file = st.file_uploader("Upload image", type=["png","jpg","jpeg"])
            if img_file:
                img_bytes = img_file.getvalue()
                img = Image.open(img_file)
                st.image(img, use_column_width=True)

                solve_key = f"ocr_solved_{img_file.file_id}"
                if solve_key not in st.session_state:
                    with st.spinner("Reading and solving every question in this photo with AI — this may take a moment…"):
                        try:
                            st.session_state[solve_key] = solve_photo_with_llm(img_bytes)
                        except Exception:
                            st.session_state[solve_key] = None
                            st.error("Couldn't read that photo. Please try a clearer picture, better lighting, or less glare.")

                solved = st.session_state.get(solve_key)
                if solved:
                    for q in solved:
                        st.markdown(f"#### Question {q['number']}")
                        render_steps(q["steps"])
                        st.divider()

                    if st.button("🔄 Not right? Re-read and re-solve this photo"):
                        del st.session_state[solve_key]
                        st.rerun()

    else:  # 📄 PDF Document
        st.caption(
            "Upload any PDF containing maths questions — a past paper, a worksheet, homework, "
            "anything with problems on it — not just official exam papers. Malita reads and solves "
            "every question directly here, no need to retype anything."
        )
        if not can_use_pdf(effective_tier):
            st.warning("📄 PDF upload is a Learner/Premium feature. Upgrade from the sidebar to unlock it.")
        else:
            pdf = st.file_uploader("Upload PDF", type=["pdf"])
            if pdf:
                pdf_bytes = pdf.read()
                st.caption(f"{pdf.name} · {len(pdf_bytes) // 1024} KB")

                solve_key = f"pdf_solved_{pdf.file_id}"
                if solve_key not in st.session_state:
                    with st.spinner("Reading and solving every question in this document with AI — this may take a minute…"):
                        try:
                            transcribed = transcribe_pdf_with_llm(pdf_bytes)
                            st.session_state[solve_key] = solve_full_paper(transcribed, paper_title=pdf.name) if transcribed.strip() else []
                        except Exception:
                            st.session_state[solve_key] = None
                            st.error("Couldn't read that document. Please try a clearer scan or a different file.")

                solved = st.session_state.get(solve_key)
                if solved:
                    for q in solved:
                        st.markdown(f"#### Question {q['number']}")
                        render_steps(q["steps"])
                        st.divider()

                    if st.button("🔄 Not right? Re-read and re-solve this document"):
                        del st.session_state[solve_key]
                        st.rerun()
                elif solved == []:
                    st.warning("Couldn't detect individual questions in this document.")

# =====================================================
# PAST PAPERS LIBRARY
# =====================================================
elif mode == "🗄️ Past Papers Library":
    st.title("🗄️ Past Papers Library")
    st.caption("Real NSC Grade 12 past exam papers, ready to download.")

    # SA schools sit these exam sittings across a school year, in
    # chronological order - kept here (rather than free text) so every
    # upload uses one consistent label the year-expander sort can rely on.
    EXAM_SERIES_OPTIONS = [
        "February/March (Supplementary)",
        "March/April Control Test",
        "June Exam",
        "September (Trial)",
        "November (Final)",
    ]
    DOCUMENT_TYPE_OPTIONS = ["Question Paper", "Memo"]
    SUBJECT_OPTIONS = ["Mathematics", "Physical Sciences"]

    if is_admin_user:
        with st.expander("➕ Add a new past paper (admin only)"):
            with st.form("add_past_paper_form", clear_on_submit=True):
                up_col1, up_col2 = st.columns(2)
                with up_col1:
                    up_subject = st.selectbox("Subject", SUBJECT_OPTIONS)
                    up_year = st.number_input("Year", min_value=2000, max_value=2100, value=2021, step=1)
                    up_paper_number = st.selectbox("Paper", [1, 2])
                    up_document_type = st.selectbox("Document type", DOCUMENT_TYPE_OPTIONS)
                with up_col2:
                    up_exam_series = st.selectbox("Exam", EXAM_SERIES_OPTIONS, index=len(EXAM_SERIES_OPTIONS) - 1)
                    up_variant = st.selectbox("Variant", ["English", "Afrikaans/English (Bilingual)"])
                up_file = st.file_uploader("PDF file", type=["pdf"], key="past_paper_upload")
                submitted = st.form_submit_button("Upload paper")
                if submitted:
                    if not up_file:
                        st.error("Please choose a PDF file to upload.")
                    else:
                        title = f"{up_exam_series} {up_year}"
                        add_past_paper(
                            title=title, year=int(up_year), paper_number=int(up_paper_number),
                            file_name=up_file.name, file_data=up_file.read(),
                            variant=up_variant, exam_series=up_exam_series,
                            document_type=up_document_type, subject=up_subject,
                            uploaded_by=auth_user["id"],
                        )
                        st.success(f"Uploaded {title} — {up_subject} Paper {up_paper_number} {up_document_type} ({up_variant}).")
                        st.rerun()

    if not can_use_past_papers(effective_tier):
        st.warning("🗄️ The Past Papers Library is a Premium feature. Upgrade from the sidebar to unlock it.")
    else:
        all_papers = list_past_papers()
        if not all_papers:
            st.info("No papers uploaded yet — check back soon.")
        else:
            available_subjects = sorted({p["subject"] for p in all_papers})
            subject_filter = (
                st.radio("Subject", available_subjects, horizontal=True, key="pp_subject_filter")
                if len(available_subjects) > 1 else available_subjects[0]
            )
            papers = [p for p in all_papers if p["subject"] == subject_filter]

            def _render_paper_row(p):
                pc1, pc2, pc3 = st.columns([3, 1, 1])
                with pc1:
                    st.markdown(
                        f"{p['subject']} Paper {p['paper_number']} · {p['document_type']} · {p['variant']}"
                    )
                    st.caption(f"{p['file_size'] // 1024} KB")
                view_key = f"view_paper_{p['id']}"
                with pc2:
                    if st.button("👁️ View", key=f"view_btn_{p['id']}"):
                        st.session_state[view_key] = not st.session_state.get(view_key, False)
                with pc3:
                    fname, fdata = get_past_paper_file(p["id"])
                    st.download_button(
                        "⬇️ Download", data=fdata, file_name=fname,
                        mime="application/pdf", key=f"dl_{p['id']}",
                    )
                if is_admin_user:
                    if st.button("🗑️ Delete", key=f"del_{p['id']}"):
                        delete_past_paper(p["id"])
                        st.rerun()

                if st.session_state.get(view_key):
                    # A base64 data: URI iframe only reliably shows page 1 of
                    # a multi-page PDF (the browser's embedded viewer doesn't
                    # scroll/paginate past it reliably at that size) - pointing
                    # the iframe at a real URL (the same download endpoint the
                    # mobile app already uses) instead lets the browser fetch
                    # and render it the normal way, with full scrolling.
                    if "view_api_token" not in st.session_state:
                        st.session_state["view_api_token"] = create_api_token(auth_user["id"])
                    pdf_url = f"{API_BASE_URL}/past-papers/{p['id']}/download?token={st.session_state['view_api_token']}"
                    st.markdown(
                        f'<iframe src="{pdf_url}" width="100%" height="800" '
                        f'style="border:1px solid #e1e0d9;border-radius:8px;"></iframe>',
                        unsafe_allow_html=True,
                    )

            years = sorted({p["year"] for p in papers}, reverse=True)
            for i, year in enumerate(years):
                year_papers = [p for p in papers if p["year"] == year]
                with st.expander(f"📅 {year} ({len(year_papers)} document{'s' if len(year_papers) != 1 else ''})", expanded=(i == 0)):
                    seen_series = set()
                    for series in EXAM_SERIES_OPTIONS:
                        series_papers = [p for p in year_papers if p["exam_series"] == series]
                        if not series_papers:
                            continue
                        seen_series.add(series)
                        st.markdown(f"**{series}**")
                        for p in series_papers:
                            _render_paper_row(p)
                    # Any exam series added before this dropdown existed (or
                    # any custom value) still shows up here rather than
                    # silently vanishing from the library.
                    other_papers = [p for p in year_papers if p["exam_series"] not in seen_series]
                    if other_papers:
                        st.markdown(f"**{other_papers[0]['exam_series'] or 'Other'}**")
                        for p in other_papers:
                            _render_paper_row(p)

# =====================================================
# PROFILE
# =====================================================
elif mode=="🎯 Learner Profile":
    st.title("🎯 Learner Profile")
    # Built from the solved_questions table, not st.session_state, so
    # progress survives logging out/in or switching devices.
    learner = get_learner_stats(auth_user["id"])

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
    recent = get_recent_solved(auth_user["id"], limit=100)
    if recent:
        # Practice-source questions are already proper LaTeX (backslash
        # commands like \text{}); AI Tutor questions are whatever the
        # learner typed, which ranges from a clean expression to a full
        # English word problem - blindly running everything through
        # st.latex() mangles a word problem (math mode ignores spaces and
        # italicises every letter), so only genuine LaTeX or a short,
        # word-free expression gets typeset; anything else stays plain text.
        _CLEAN_EXPR_RE = re.compile(r"[0-9a-zA-Z\s\^\+\-\*/=<>().,;:]+")
        _LONG_WORD_RE = re.compile(r"[a-zA-Z]{4,}")

        def _render_activity_question(text):
            if not text:
                return
            if "\\" in text or (_CLEAN_EXPR_RE.fullmatch(text) and not _LONG_WORD_RE.search(text)):
                st.latex(text)
            else:
                st.markdown(text)

        def _count_activities(node):
            if isinstance(node, list):
                return len(node)
            return sum(_count_activities(v) for v in node.values())

        def _plural(n):
            return "activity" if n == 1 else "activities"

        # Type -> Date -> Paper -> Topic -> activities (newest first at
        # every level, since get_recent_solved() already returns newest
        # first and dict insertion order preserves that as we group).
        grouped: dict = {}
        for r in recent:
            type_label = "AI Tutor" if r["source"] == "ai_tutor" else "Practice Question"
            date_label = r["solved_at"].strftime("%d %b %Y") if r["solved_at"] else "Unknown date"
            paper_label = r["paper"] or "No paper specified"
            topic_label = r["topic"] or "No topic specified"
            (grouped.setdefault(type_label, {})
                    .setdefault(date_label, {})
                    .setdefault(paper_label, {})
                    .setdefault(topic_label, [])
                    .append(r))

        _INDENT = " " * 4  # non-breaking spaces - a plain leading " " collapses in HTML

        def _toggle_section(label, key, indent_level=0, default_open=False):
            # Streamlit forbids nesting an st.expander inside another
            # st.expander, and also caps st.columns at one level of nesting -
            # both ruled out a "real" nested container per level. Only the
            # outermost Type level below is a real expander; Date/Paper/Topic
            # are plain buttons toggling session_state, indented with
            # leading spaces instead of a layout container.
            if key not in st.session_state:
                st.session_state[key] = default_open
            icon = "▾" if st.session_state[key] else "▸"
            if st.button(f"{_INDENT * indent_level}{icon} {label}", key=f"btn_{key}"):
                st.session_state[key] = not st.session_state[key]
            return st.session_state[key]

        for ti, (type_label, by_date) in enumerate(grouped.items()):
            type_count = _count_activities(by_date)
            with st.expander(f"🗂️ {type_label} — {type_count} {_plural(type_count)}", expanded=(ti == 0)):
                for di, (date_label, by_paper) in enumerate(by_date.items()):
                    date_count = _count_activities(by_paper)
                    date_key = f"activity_open_date_{ti}_{di}"
                    date_open = _toggle_section(
                        f"📅 {date_label} — {date_count} {_plural(date_count)}",
                        date_key, indent_level=1, default_open=(ti == 0 and di == 0),
                    )
                    if date_open:
                        for pi, (paper_label, by_topic) in enumerate(by_paper.items()):
                            paper_count = _count_activities(by_topic)
                            paper_key = f"activity_open_paper_{ti}_{di}_{pi}"
                            paper_open = _toggle_section(
                                f"📄 {paper_label} — {paper_count} {_plural(paper_count)}",
                                paper_key, indent_level=2, default_open=(ti == 0 and di == 0 and pi == 0),
                            )
                            if paper_open:
                                for toi, (topic_label, activities) in enumerate(by_topic.items()):
                                    topic_key = f"activity_open_topic_{ti}_{di}_{pi}_{toi}"
                                    topic_open = _toggle_section(
                                        f"{topic_label} — {len(activities)} {_plural(len(activities))}",
                                        topic_key, indent_level=3,
                                        default_open=(ti == 0 and di == 0 and pi == 0 and toi == 0),
                                    )
                                    if topic_open:
                                        for r in activities:
                                            when = r["solved_at"].strftime("%H:%M") if r["solved_at"] else ""
                                            st.caption(f"{_INDENT * 4}{when}")
                                            _render_activity_question(r["question"])
                                            st.divider()
    else:
        st.info("No solved-question history yet — this fills in as you use the AI Tutor or Practice Questions.")

# =====================================================
# FORMULA SHEET
# =====================================================
elif mode == "📏 Formula Sheet":
    fs_subject = st.radio("Subject", ["🧮 Mathematics", "🔬 Physical Sciences"], horizontal=True, key="fs_subject")

    if fs_subject == "🧮 Mathematics":
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

    else:
        st.title("📏 Physical Sciences Data Sheet")
        st.info("The core constants and formulas from the NSC Information Sheet — for tables not included here (e.g. standard electrode potentials), refer to your exam data booklet.")

        col1, col2 = st.columns(2)

        with col1:
            st.header("📑 Paper 1 — Physics")
            with st.expander("Physical Constants", expanded=True):
                st.latex(r"g = 9.8\ \text{m}\cdot\text{s}^{-2}")
                st.latex(r"G = 6.67\times10^{-11}\ \text{N}\cdot\text{m}^2\cdot\text{kg}^{-2}")
                st.latex(r"c = 3.0\times10^{8}\ \text{m}\cdot\text{s}^{-1}")
                st.latex(r"e = 1.6\times10^{-19}\ \text{C}")
                st.latex(r"m_e = 9.11\times10^{-31}\ \text{kg}")
                st.latex(r"h = 6.63\times10^{-34}\ \text{J}\cdot\text{s}")
                st.latex(r"k = 9.0\times10^{9}\ \text{N}\cdot\text{m}^2\cdot\text{C}^{-2}")

            with st.expander("Mechanics"):
                st.latex(r"v = u + at")
                st.latex(r"\Delta x = ut + \tfrac12at^2")
                st.latex(r"v^2 = u^2 + 2a\Delta x")
                st.latex(r"F_{net} = ma")
                st.latex(r"p = mv \qquad F\Delta t = \Delta p")
                st.latex(r"W = F\Delta x\cos\theta \qquad P = \frac{W}{\Delta t} = Fv")
                st.latex(r"E_p = mgh \qquad E_k = \tfrac12mv^2")
                st.latex(r"F_g = \frac{Gm_1m_2}{d^2}")

            with st.expander("Waves, Sound & Light"):
                st.latex(r"v = f\lambda")
                st.latex(r"f_L = f_s\left(\frac{v\pm v_L}{v\pm v_s}\right) \quad \text{(Doppler Effect)}")

        with col2:
            st.header("📑 Paper 1 — Electricity & Magnetism")
            with st.expander("Electrostatics & Circuits", expanded=True):
                st.latex(r"F = \frac{kQ_1Q_2}{r^2} \qquad E = \frac{kQ}{r^2}")
                st.latex(r"V = \frac{W}{Q} \qquad I = \frac{\Delta Q}{\Delta t}")
                st.latex(r"R = \frac{V}{I} \qquad P = VI = I^2R = \frac{V^2}{R}")
                st.latex(r"\varepsilon = I(R+r)")
                st.latex(r"R_s = R_1+R_2+\dots \qquad \frac{1}{R_p} = \frac{1}{R_1}+\frac{1}{R_2}+\dots")

            with st.expander("Electrodynamics"):
                st.latex(r"\varepsilon = N\frac{\Delta\Phi}{\Delta t} \quad \text{(Faraday's Law)}")
                st.latex(r"\Phi = BA\cos\theta")

            st.header("📑 Paper 2 — Chemistry")
            with st.expander("Stoichiometry & Gases", expanded=True):
                st.latex(r"N_A = 6.02\times10^{23}\ \text{mol}^{-1}")
                st.latex(r"V_m = 22.4\ \text{dm}^3\cdot\text{mol}^{-1}\ \text{at STP}")
                st.latex(r"R = 8.31\ \text{J}\cdot\text{K}^{-1}\cdot\text{mol}^{-1}")
                st.latex(r"n = \frac{m}{M} \qquad n = \frac{N}{N_A} \qquad n = cV")
                st.latex(r"pV = nRT")

            with st.expander("Equilibrium, Acids & Bases"):
                st.latex(r"K_c = \frac{[\text{products}]}{[\text{reactants}]}")
                st.latex(r"pH = -\log[H_3O^+] \qquad pOH = -\log[OH^-]")
                st.latex(r"K_w = [H_3O^+][OH^-] = 1\times10^{-14}\ \text{at } 25^\circ\text{C}")
                st.latex(r"pH + pOH = 14")

            with st.expander("Electrochemistry"):
                st.latex(r"E^\circ_{cell} = E^\circ_{cathode} - E^\circ_{anode}")

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
    _SVG_LIBRARY = """<svg class="tile-illustration" width="120" height="120" viewBox="0 0 100 100" fill="white">
        <rect x="15" y="20" width="70" height="55" rx="6" fill-opacity="0.5"/>
        <rect x="22" y="30" width="56" height="8" rx="2"/>
        <rect x="22" y="44" width="56" height="8" rx="2"/>
        <rect x="22" y="58" width="34" height="8" rx="2"/>
        </svg>"""

    HOME_TILES = [
        {"mode": "🧮 AI Tutor", "icon": "🧮", "title": "AI Tutor",
         "desc": "Type a question, snap or upload a photo, or upload a PDF — all solved step by step.",
         "css_class": "tile-c1", "illustration": _SVG_TUTOR},
        {"mode": "📝 Practice Questions", "icon": "📝", "title": "Practice Questions",
         "desc": "Work through curated questions with hints and full solutions.",
         "css_class": "tile-c2", "illustration": _SVG_PENCIL_NOTES},
        {"mode": "🗄️ Past Papers Library", "icon": "🗄️", "title": "Past Papers Library",
         "desc": "Browse and download real NSC past exam papers.",
         "css_class": "tile-c7", "illustration": _SVG_LIBRARY},
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

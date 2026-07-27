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

#from frontend import *

from backend.db import init_db, SA_PROVINCES
from backend.auth import register_user, login_user, get_user_tier, AuthError
from backend.tiers import TIER_CONFIG, TIER_ORDER, can_use_ocr, can_use_pdf, daily_limit
from backend.usage import can_solve, record_solve, get_today_count
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
# MOVING BANNER CSS

st.markdown("""
<div class="moving-banner">
    <div class="banner-text">
        📘 Master Algebra • 📈 Ace Functions • ✏️ Step-by-step Solutions • 🎯 Grade 12 Exam Ready • 🇿🇦
    </div>
</div>
""", unsafe_allow_html=True)


st.markdown("""                        
<style>

/* Moving banner container */
.moving-banner {
    background: white;
    border-radius: 18px;
    padding: 16px 0;
    margin-bottom: 24px;
    overflow: hidden;
    box-shadow: 0 10px 25px rgba(0,0,0,0.08);
}

/* Scrolling text */
.banner-text {
    display: inline-block;
    white-space: nowrap;
    font-size: 1.05rem;
    font-weight: 600;
    color: #1e293b;
    animation: scroll-left 18s linear infinite;
}

/* Animation */
@keyframes scroll-left {
    0% {
        transform: translateX(100%);
    }
    100% {
        transform: translateX(-100%);
    }
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
.stApp {
    background: linear-gradient(135deg, #f8fafc, #eef2ff);
}

/* ---------- HEADINGS ---------- */
h1, h2, h3 {
    color: #1e293b;
    font-weight: 700;
}

/* ---------- CARDS ---------- */
.card {
    background: white;
    padding: 1.5rem;
    border-radius: 16px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.08);
    margin-bottom: 1.5rem;
}

/* ---------- BUTTONS ---------- */
.stButton > button {
    background: linear-gradient(135deg, #2563eb, #4f46e5);
    color: white;
    border-radius: 10px;
    padding: 0.6rem 1.2rem;
    font-weight: 600;
    border: none;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #1e40af, #4338ca);
    transform: scale(1.02);
}

/* ---------- SIDEBAR ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a, #1e293b);
}

section[data-testid="stSidebar"] * {
    color: white !important;
}

/* ---------- METRICS ---------- */
[data-testid="stMetricValue"] {
    font-size: 2rem;
    color: #2563eb;
}

</style>
""", unsafe_allow_html=True)


# =====================================================
# OCR FUNCTIONS
# =====================================================
def preprocess_image(pil_image):
    img = np.array(pil_image.convert("L"))
    _, img_bin = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY_INV)
    return img_bin

def ocr_with_exponents(img):
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    result, prev_bottom, prev_text = "", 0, ""
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        top, height = data["top"][i], data["height"][i]
        if prev_text and top + height < prev_bottom - 5:
            result += "^" + text
        else:
            if prev_text and re.match(r"[a-zA-Z]", prev_text) and re.match(r"\d", text):
                result += "*" + text
            else:
                result += text
        prev_bottom = top + height
        prev_text = text
    return result.replace(" ", "").replace("\n", "")

def clean_for_sympy(text):
    text = re.sub(r"([a-zA-Z])(\d+)", r"\1^\2", text)
    text = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", text)
    return text

def extract_pdf_text(uploaded_file):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    return "".join(page.get_text() for page in doc)

# =====================================================
# SESSION STATE
# =====================================================
if "learner" not in st.session_state:
    st.session_state.learner = {"name": "", "solved": 0, "Marks": 0}

if "copied_text" not in st.session_state:
    st.session_state.copied_text = ""

# =====================================================
# PRACTICE QUESTIONS (FULL – PAPER 1 & 2)
# =====================================================
practice_data = {
"Paper 1": {
"Algebra": [
{"question": r"\text{Solve for } x:\; x^2 - 5x + 6 = 0",
 "solution_steps":[
 r"(x-2)(x-3)=0 \quad (1 Mark)",
 r"x-2=0 \;\text{or}\; x-3=0 \quad (1 Mark)",
 r"x=2 \;\text{or}\; x=3 \quad (1 Mark)"
 ],
 "final_answer": r"x=2 \;\text{or}\; x=3",
 "Marks":3},
{"question": r"\text{Solve for } x:\; 3x^2=12",
 "solution_steps":[
 r"x^2=4 \quad (1 Mark)",
 r"x=\pm2 \quad (2 Marks)"
 ],
 "final_answer": r"x=\pm2",
 "Marks":3}

],
"Sequences": [
{"question": r"\text{Find the 10th term of } 3,7,11,\dots",
 "solution_steps":[
 r"a=3,\; d=4 \quad (1 Mark)",
 r"T_n=a+(n-1)d \quad (1 Mark)",
 r"T_{10}=39 \quad (1 Mark)"
 ],
 "final_answer": r"39",
 "Marks":3}
],
"Financial Mathematics": [
{"question": r"\text{Find } A \text{ if } P=1000,\; i=10\%,\; n=2",
 "solution_steps":[
 r"A=P(1+i)^n \quad (1 Mark)",
 r"A=1000(1.1)^2=1210 \quad (2 Marks)"
 ],
 "final_answer": r"1210",
 "Marks":3}
],
"Calculus": [
{"question": r"\text{Differentiate } f(x)=3x^2",
 "solution_steps":[
 r"\frac{d}{dx}(3x^2)=6x \quad (3 Marks)"
 ],
 "final_answer": r"6x",
 "Marks":3}
]
},
"Paper 2": {
"Analytical Geometry": [
{"question": r"\text{Find the distance between } A(1,2), B(4,6)",
 "solution_steps":[
 r"d=\sqrt{(4-1)^2+(6-2)^2}=5 \quad (3 Marks)"
 ],
 "final_answer": r"5",
 "Marks":3}
],
"Trigonometry": [
{"question": r"\text{Solve } \sin x=\frac12,\; 0^\circ\le x\le360^\circ",
 "solution_steps":[
 r"x=30^\circ,\;150^\circ \quad (3 Marks)"
 ],
 "final_answer": r"30^\circ,\;150^\circ",
 "Marks":3}
],
"Statistics & Probability": [
{"question": r"\text{Find the mean of } 2,4,6,8",
 "solution_steps":[
 r"\bar{x}=\frac{20}{4}=5 \quad (3 Marks)"
 ],
 "final_answer": r"5",
 "Marks":3}
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

st.sidebar.markdown(f"👋 **{auth_user['name']}**")
st.sidebar.markdown(f"Plan: **{tier_info['label']}**")

if daily_limit(current_tier) is not None:
    used_today = get_today_count(auth_user["id"])
    st.sidebar.caption(f"AI Tutor solves today: {used_today}/{daily_limit(current_tier)}")

with st.sidebar.expander("💳 Upgrade / Manage Plan"):
    for tier_key in TIER_ORDER:
        cfg = TIER_CONFIG[tier_key]
        if cfg["price_zar"] == 0:
            continue
        if tier_key == current_tier:
            st.success(f"✅ You're on {cfg['label']} (R{cfg['price_zar']}/month)")
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

if st.sidebar.button("Log Out"):
    st.session_state.auth_user = None
    st.rerun()

st.sidebar.divider()

mode = st.sidebar.radio(
    "Choose Mode",
    ["📚 Past Papers (PDF)",
     "📷 OCR Question",
     "🧮 AI Tutor",
     "📝 Practice Questions",
     "🎯 Learner Profile",
     "📏 Formula Sheet"]
)

# =====================================================
# PRACTICE QUESTIONS
# =====================================================
if mode=="📝 Practice Questions":
    st.title("📝 Practice Questions")
    paper = st.selectbox("Select Paper", list(practice_data.keys()))
    topic = st.selectbox("Select Topic", list(practice_data[paper].keys()))
    questions = practice_data[paper][topic]
    q_numbers = [f"Q{i+1}" for i in range(len(questions))]
    q_selected = st.selectbox("Select Question Number", q_numbers)
    q_data = questions[q_numbers.index(q_selected)]

    st.markdown(f"### {q_selected}")
    st.latex(q_data["question"])
    st.text_input("Attempt your answer first:")

    if st.button("Show Solution"):
        st.markdown("### ✏️ Step-by-Step Solution")
        for step in q_data["solution_steps"]:
            st.latex(step)
        st.success("Final Answer")
        st.latex(q_data["final_answer"])
        st.info(f"Total Marks: {q_data['Marks']}")
        st.session_state.learner["solved"] += 1
        st.session_state.learner["Marks"] += q_data["Marks"]

# =====================================================
# AI SOLVER (FULL PAPER 1 & PAPER 2 LOGIC)
# =====================================================

elif mode == "🧮 AI Tutor":

    # -------------------------------------------------
    # CSS (ANIMATION + STYLING)
    # -------------------------------------------------
    st.markdown("""
    <style>
    @keyframes float {
        0% { transform: translateY(0px); }
        50% { transform: translateY(-6px); }
        100% { transform: translateY(0px); }
    }

    .logo {
        animation: float 3s ease-in-out infinite;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,0.15));
    }

    .header-box {
        background: white;
        padding: 1.5rem 2rem;
        border-radius: 16px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------
    # HEADER LAYOUT
    # -------------------------------------------------
    st.markdown('<div class="header-box">', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 6])

    with col1:
        if logo_svg:
            st.markdown(
                f"""
                <img src="data:image/png;base64,{logo_svg}"
                     class="logo"
                     width="400">
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown("### 🎓")

    with col2:
        st.markdown("""
        <h3 style="margin-bottom:0;">AI TUTOR</h3>
        <p style="font-size:1.1rem; color:#475569; margin-top:0;">
            AI-powered Grade 12 Mathematics Tutor 🇿🇦
        </p>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # 👉 Continue with your AI Tutor logic below



    paper = st.selectbox("Select Paper", ["Paper 1", "Paper 2"])

    if paper == "Paper 1":
        topic = st.selectbox(
            "Topic",
            ["Algebra", "Sequences", "Financial Mathematics", "Calculus", "Functions & Graphs"]
        )
    else:
        topic = st.selectbox(
            "Topic",
            ["Analytical Geometry", "Trigonometry", "Statistics", "Probability"]
        )

    question = st.text_input("Enter your expression:", st.session_state.copied_text)
    x = sp.symbols("x")

    solve_clicked = st.button("Solve")
    if solve_clicked and question:
        allowed, limit_message = can_solve(auth_user["id"], current_tier)
        if not allowed:
            st.warning(limit_message)
            st.stop()
        record_solve(auth_user["id"])
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
                st.markdown("### 💰 Compound Interest")

                try:
                    # Extract P, i, n from question automatically if possible
                    P_match = re.search(r"P\s*=\s*([-+]?\d*\.?\d+)", question)
                    i_match = re.search(r"i\s*=\s*([-+]?\d*\.?\d+)", question)
                    n_match = re.search(r"n\s*=\s*([-+]?\d*\.?\d+)", question)

                    P = float(P_match.group(1)) if P_match else st.number_input("Principal (P)", 1000.0)
                    i = float(i_match.group(1))/100 if i_match else st.number_input("Interest rate (%)", 10.0)/100
                    n = float(n_match.group(1)) if n_match else st.number_input("Time (years)", 2.0)

                    A = P * (1 + i) ** n

                    st.latex(r"A = P(1+i)^n")
                    st.latex(rf"A = {round(A, 2)}")

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

                    if formula is None:
                        # Implicit relation: solve for the plotting "vertical"
                        # variable in terms of the "horizontal" one, this may
                        # produce multiple branches (e.g. y = +-sqrt(...)).
                        branches = sp.solve(sp.Eq(lhs_expr, rhs_expr), plot_vert)
                    else:
                        branches = [formula] if out_var == plot_vert else None

                    x = indep_var  # kept for readability in the walkthrough below
                    expr = formula if formula is not None else None

                    st.markdown("##### 🔹 Given Relation")
                    st.latex(sp.latex(sp.Eq(lhs_expr, rhs_expr)))

                    # ---------------------------------------------------
                    # DETAILED STEP-BY-STEP ANALYSIS
                    # Only fully meaningful when we have one explicit
                    # formula: out_var = f(indep_var). For genuinely
                    # implicit relations (e.g. circles) we skip straight to
                    # the graph plus basic intercepts per branch.
                    # ---------------------------------------------------
                    if expr is not None and out_var == plot_vert:

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
                        st.info("This is an implicit relation between two variables — showing the graph and intercepts below.")

                    # ---------------------------------------------------
                    # 📉 SKETCH OF THE GRAPH (SMART MODE, generic variables)
                    # ---------------------------------------------------
                    st.markdown("##### 📉 Sketch of the Graph")

                    horiz_vals = np.linspace(-10, 10, 4000)
                    fig, ax = plt.subplots(figsize=(7, 5))

                    expr_str_for_type = str(formula) if formula is not None else str(equation)
                    is_trig = any(f in expr_str_for_type for f in ["sin", "cos", "tan", "sec", "csc"])

                    if branches is None:
                        branches = [formula]

                    if len(branches) > 1 or (formula is not None and out_var != plot_vert):
                        # Multiple branches / relation graphed implicitly
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
                st.markdown("### 📏 Distance Between Two Points")

                x1 = st.number_input("x₁", 1.0)
                y1 = st.number_input("y₁", 2.0)
                x2 = st.number_input("x₂", 4.0)
                y2 = st.number_input("y₂", 6.0)

                d = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

                st.latex(r"d=\sqrt{(x_2-x_1)^2+(y_2-y_1)^2}")
                st.latex(rf"d={round(d,2)}")

            elif topic == "Trigonometry":
                st.markdown("### 📐 Trigonometric Ratios")

                angle = st.number_input("Angle (degrees)", 30.0)
                rad = np.deg2rad(angle)

                st.latex(rf"\sin({angle}^\circ) = {round(np.sin(rad),3)}")
                st.latex(rf"\cos({angle}^\circ) = {round(np.cos(rad),3)}")
                st.latex(rf"\tan({angle}^\circ) = {round(np.tan(rad),3)}")

            elif topic == "Statistics":
                st.markdown("### 📊 Mean Calculation")

                data = st.text_input("Enter data (comma-separated)", "2,4,6,8")
                values = list(map(float, data.split(",")))

                mean = np.mean(values)

                st.latex(r"\bar{x}=\frac{\sum x}{n}")
                st.latex(rf"\bar{{x}}={mean}")

            elif topic == "Probability":
                st.markdown("### 🎲 Probability")

                favourable = st.number_input("Favourable outcomes", 1)
                total = st.number_input("Total outcomes", 6)

                prob = favourable / total

                st.latex(r"P(E)=\frac{n(E)}{n(S)}")
                st.latex(rf"P(E)={round(prob,3)}")

        except Exception as e:
            st.error("Invalid expression or input")
            st.caption(str(e))

# =====================================================
# OCR
# =====================================================
elif mode=="📷 OCR Question":
    st.title("📷 OCR Question")
    if not can_use_ocr(current_tier):
        st.warning("📷 Photo upload & OCR is a Learner/Premium feature. Upgrade from the sidebar to unlock it.")
    else:
        img_file = st.file_uploader("Upload image", type=["png","jpg","jpeg"])
        if img_file:
            img = Image.open(img_file)
            st.image(img, use_container_width=True)
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
    if not can_use_pdf(current_tier):
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
    st.metric("Solved", st.session_state.learner["solved"])
    st.metric("Marks", st.session_state.learner["Marks"])

# =====================================================
# FORMULA SHEET
# =====================================================
else:
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

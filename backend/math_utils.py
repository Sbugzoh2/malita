"""
Malita (Pty) Ltd — safe math expression parsing.

Shared by app.py (Streamlit) and api_server.py (FastAPI, used by the
native app) so both talk to sympy the exact same way.

We NEVER call sp.sympify()/eval() directly on raw user text. sp.sympify()
ultimately runs Python's eval() on the string, so a malicious user could
type something that isn't math at all and have it executed on the server.
Instead we use sympy's parse_expr() with:
  - global_dict locked down (no builtins, no arbitrary names)
  - local_dict containing ONLY the math symbols/functions we explicitly allow
"""

import re
import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

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

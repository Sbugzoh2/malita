"""
Malita (Pty) Ltd — LLM fallback for the AI Tutor.

The AI Tutor's primary solver is backend/solver.py's SymPy-based logic -
deterministic, free, and already handles every question type the app
advertises. This module is ONLY a fallback: app.py and api_server.py call
it exclusively from the `except` branch when SymPy's parser can't make
sense of the input at all (typically a free-form word problem or
phrasing outside what the regex/keyword rules expect). Most solves never
touch this file, and therefore never cost anything - see backend/tiers.py
for the Free-tier gate that keeps this an entirely paid-tier cost.

Uses Claude Haiku 4.5 rather than a larger model: concise Grade 12 CAPS
curriculum tutoring is well within its competence, and it's the cheapest
current Claude model (see the cost estimate delivered separately).
Requires ANTHROPIC_API_KEY to be set in the environment.
"""

import base64
import io
import json
import re

import matplotlib
matplotlib.use("Agg")  # headless - this module never runs inside a GUI
import matplotlib.pyplot as plt
import numpy as np
import sympy as sp

from .llm_client import get_client
from .math_utils import safe_parse, robust_axis_limits

LLM_MODEL = "claude-haiku-4-5"
# Explanation and mathematics are now separate steps (see SYSTEM_PROMPT),
# roughly doubling step count vs. one combined sentence-with-inline-math
# per step - a bigger budget keeps that from truncating mid-JSON.
MAX_OUTPUT_TOKENS = 1536

# app.py's render_steps() does a direct dict lookup with no fallback for
# an unrecognised "type" - a step type outside this set would crash the
# page rather than just render oddly, so any type the model invents gets
# coerced to "markdown" below instead of trusted as-is. "plot" is an
# internal-only pseudo-type: the model is allowed to emit it, but it never
# reaches a caller as-is - solve_with_llm renders it into a real "image"
# step (see _render_plot_step) before returning.
VALID_STEP_TYPES = {"markdown", "latex", "write", "info", "warning", "error", "success", "caption", "plot"}


# Deliberately short - see the module docstring on prompt caching (it's
# skipped here since a prefix this size wouldn't clear the ~1024-token
# minimum cacheable length anyway; revisit if this grows to include
# curriculum reference material).
SYSTEM_PROMPT = """You are Malita, a patient Grade 12 (Matric) tutor for South African CAPS-curriculum learners, covering both Mathematics and Physical Sciences.

A learner has asked a question - for Mathematics, this is usually one the app's built-in solver could not parse (a word problem or unusual phrasing); for Physical Sciences, every question comes to you directly since there is no separate deterministic solver. Solve it yourself, showing the working step by step, the way a good tutor would on a whiteboard. For Physical Sciences, use the subject's own conventions: correct SI units in every step, the appropriate formula (kinematics, Newton's laws, circuits, stoichiometry, equilibrium, etc.) named or shown before it's used, and round numerical answers sensibly (2 decimal places is typical unless the question asks otherwise).

When a unit needs \\cdot between symbols, wrap EACH unit in its own \\text{}, e.g. \\text{m}\\cdot\\text{s}^{-2} - never write \\cdot directly against a bare letter (m\\cdotps^{-2} is not a valid command and renders as broken text, not a dot). A unit with no \\cdot needed can stay in one \\text{}, e.g. \\text{m/s}.

Respond with ONLY a raw JSON array - your entire response must start with [ and end with ]. Do NOT wrap it in a ```json code fence or any other markdown, and do NOT include any prose before or after it.

Each element is a step object shaped exactly like: {"type": "markdown", "content": "..."}

Keep explanation and mathematics visually separate, like a worked solution written on paper - a brief note on one line, the equation it produces on the next:
- A "markdown" step is a SHORT label or note only - a few words (e.g. "Factorise:", "Domain restrictions:", "Check both solutions:"), never a full explanatory sentence or paragraph. Let the mathematics do the talking - don't narrate what you're about to do or why in prose.
- Only write a fuller sentence when a step is genuinely non-obvious and needs it, or when the learner's question explicitly asks for an explanation or reason - not as the default style.
- Immediately after any markdown step that leads into an equation, expression, or result, add a SEPARATE step with "type": "latex" holding just that expression (plain LaTeX, no $ delimiters - e.g. "content": "x^2 - 5x + 6 = 0", not "$x^2 - 5x + 6 = 0$").
- Never combine a note and its equation into a single step - always two steps, markdown then latex.

Use "type": "success" for exactly one final step stating the final answer, wrapped in single-dollar delimiters, e.g. {"type": "success", "content": "$x = 5$"}.
Keep it concise: 4-8 steps is typical (note + equation pairs, plus the final success step).

If, and only if, the question explicitly asks you to sketch, draw, or plot a graph/function, include ONE extra step shaped like {"type": "plot", "content": "x**2 - 4"} at the point where the sketch belongs. "content" must be ONLY plottable expression(s) in terms of x, using Python/SymPy syntax (** for powers, sin/cos/tan/exp/log/sqrt/pi as needed) - Malita renders the actual image itself from this, so never describe the graph in words instead of (or in addition to) giving this step; never use "type": "plot" for anything that isn't a real function to graph.

- To sketch MORE THAN ONE function on the SAME axes (e.g. "sketch f and g on the same system of axes"), separate the expressions with "|" in one single plot step - never one plot step per function. Example content: "cos(3*x)|sin(x)".
- CAPS trig graphs (Mathematics) are always in DEGREES, never radians - whenever the question gives an explicit domain for x (e.g. "for x ∈ [-90°;180°]"), append it to the content as "@lo,hi" using plain numbers (no ° symbol), e.g. a domain of x ∈ [-90°;180°] becomes the suffix "@-90,180". Only add "@lo,hi" when the question actually states a domain - omit it otherwise.
- Putting it together, "sketch f(x)=cos3x and g(x)=sinx for x∈[-90°;180°]" becomes exactly: {"type": "plot", "content": "cos(3*x)|sin(x)@-90,180"}.
- NEVER write a plot step's content as Python/matplotlib code. "content" is ALWAYS just the bare expression(s)-and-domain string shown above - it is NEVER a script with import/linspace/plt.plot/semicolons/newlines in it, even for a two-function degree-domain question like the one above. WRONG: {"type": "plot", "content": "import numpy as np; x = np.linspace(-90, 180, 1000); f = np.cos(np.radians(3*x)); ..."}. RIGHT: {"type": "plot", "content": "cos(3*x)|sin(x)@-90,180"}.

Example of a complete, correct response:
[{"type": "markdown", "content": "Let x = number of years."}, {"type": "markdown", "content": "Set up the equation:"}, {"type": "latex", "content": "5000(1.08)^x = 10000"}, {"type": "markdown", "content": "Solve using logarithms:"}, {"type": "latex", "content": "x = \\log_{1.08}(2) \\approx 9.01"}, {"type": "success", "content": "$x \\approx 9.01 \\text{ years}$"}]

Example including a sketch:
[{"type": "markdown", "content": "Complete the square:"}, {"type": "latex", "content": "y = 4 - x^2, \\quad \\text{turning point } (0, 4)"}, {"type": "plot", "content": "4 - x**2"}, {"type": "markdown", "content": "x-intercepts (set y = 0):"}, {"type": "latex", "content": "4 - x^2 = 0 \\implies x = \\pm 2"}, {"type": "success", "content": "$x = -2$ and $x = 2$"}]

Example including a two-function degree-domain sketch:
[{"type": "markdown", "content": "Sketch both graphs:"}, {"type": "plot", "content": "cos(3*x)|sin(x)@-90,180"}, {"type": "markdown", "content": "Intersections from part (a):"}, {"type": "success", "content": "$x = -67.5\\degree, -45\\degree, 22.5\\degree, 112.5\\degree, 180\\degree$"}]"""


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_json_fence(text: str) -> str:
    """The system prompt asks for a bare JSON array, but the model
    sometimes wraps it in a markdown code fence anyway - strip a
    leading/trailing ``` or ```json fence if present, so a
    well-formed-but-fenced response still parses instead of falling
    back to being shown as one raw, unrendered block."""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text


_PLOT_COLORS = ["#2563eb", "#dc2626", "#059669"]

# Despite SYSTEM_PROMPT spelling out the "expr1|expr2@lo,hi" format with a
# worked example, the model occasionally ignores it anyway for exactly the
# case that format exists for (multi-function, degree-domain questions)
# and emits a full matplotlib script as the plot step's content instead -
# e.g. "import numpy as np; x = np.linspace(-90, 180, 1000); f =
# np.cos(np.radians(3*x)); g = np.sin(np.radians(x)); plt.plot(...)".
# Rather than losing the sketch to the "couldn't render" fallback whenever
# that happens, recover the intended expressions/domain straight out of
# the script's own linspace() and assignment lines.
_SCRIPT_LINSPACE_RE = re.compile(r"linspace\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)")
_SCRIPT_DEGREE_ASSIGN_RE = re.compile(
    r"=\s*np\.(sin|cos|tan)\(\s*np\.radians\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*\)"
)
_SCRIPT_RADIAN_ASSIGN_RE = re.compile(r"=\s*np\.(sin|cos|tan)\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


def _salvage_script_plot(content: str) -> str | None:
    """Best-effort recovery for the script-instead-of-expression failure
    mode described above. Returns a normal "expr1|expr2@lo,hi"-shaped
    string if it can find recognisable plotted expressions in the script,
    or None if there's nothing to salvage (the caller's original error is
    then what the learner sees, same as before this existed)."""
    domain_match = _SCRIPT_LINSPACE_RE.search(content)
    domain = (domain_match.group(1), domain_match.group(2)) if domain_match else None

    # Prefer the "np.radians(...)" form - it tells us the script intended
    # a degree domain, which is also the only form that can pair up
    # correctly with a plain-number linspace() domain (CAPS degree
    # questions) rather than a radian one (e.g. np.linspace(-np.pi/2, ...),
    # which _SCRIPT_LINSPACE_RE's plain-number pattern won't match anyway).
    matches = _SCRIPT_DEGREE_ASSIGN_RE.findall(content)
    if not matches:
        matches = _SCRIPT_RADIAN_ASSIGN_RE.findall(content)
        domain = None  # a radian-form expression needs a radian domain, which we can't recover from a stripped script reliably - fall back to _render_plot_step's own default instead of guessing wrong

    if not matches:
        return None

    exprs = list(dict.fromkeys(f"{fn}({inner.strip()})" for fn, inner in matches))
    result = "|".join(exprs)
    if domain:
        result += f"@{domain[0]},{domain[1]}"
    return result


def _render_plot_step(content: str) -> dict:
    """Actually sketches one or more single-variable expressions via SymPy
    + matplotlib and returns it as the same base64 PNG data-URI "image"
    step shape backend/solver.py's StepRecorder.pyplot() produces. The LLM
    can only describe what to plot, never generate real image bytes
    itself - this is what lets the AI fallback genuinely draw the graph a
    question asks for, instead of only explaining what the learner would
    need to sketch by hand. Never eval()s the model's text: parsing goes
    through the same sandboxed safe_parse() every user-typed expression in
    this app uses.

    "content" holds one expression, or several separated by "|" to sketch
    on the same axes (see SYSTEM_PROMPT), with an optional "@lo,hi" domain
    suffix. CAPS trig graphs are always in degrees, so a given domain is
    always treated as degrees - the x-axis is drawn in degrees and each
    expression is evaluated at np.radians(xs) accordingly."""
    content = content.strip()
    if any(tell in content for tell in ("import ", "plt.", ";", "\n")):
        salvaged = _salvage_script_plot(content)
        if salvaged:
            content = salvaged
        # else: fall through and let the normal parse below fail/raise as
        # it always did - _resolve_plot_steps' fallback message still
        # shows the learner's *original* question content, not this.

    domain = None
    if "@" in content:
        content, _, domain_str = content.rpartition("@")
        try:
            lo, hi = (float(v) for v in domain_str.split(","))
            domain = (lo, hi)
        except ValueError:
            domain = None

    raw_exprs = [e.strip() for e in content.split("|") if e.strip()]
    if not raw_exprs:
        raise ValueError("No expression to plot.")

    x = sp.symbols("x")
    cleaned_list = []
    fns = []
    for raw in raw_exprs:
        cleaned = raw.replace("^", "**")
        cleaned = re.sub(r"^[yf]\s*(\(\s*x\s*\))?\s*=\s*", "", cleaned, flags=re.IGNORECASE)
        expr = safe_parse(cleaned, {"x": x})
        cleaned_list.append(cleaned)
        fns.append(sp.lambdify(x, expr, "numpy"))

    is_trig = any(f in c.lower() for c in cleaned_list for f in ("sin", "cos", "tan", "sec", "csc"))
    degree_mode = domain is not None
    if domain is not None:
        x_min, x_max = domain
    elif is_trig:
        x_min, x_max = -2 * np.pi, 2 * np.pi
    else:
        x_min, x_max = -10, 10

    xs = np.linspace(x_min, x_max, 1000)
    eval_xs = np.radians(xs) if degree_mode else xs

    fig, ax = plt.subplots(figsize=(6, 4))
    all_ys = []
    for cleaned, f, color in zip(cleaned_list, fns, _PLOT_COLORS * (len(fns) // len(_PLOT_COLORS) + 1)):
        with np.errstate(all="ignore"):
            ys = np.asarray(f(eval_xs), dtype=float)
        ys = np.where(np.isfinite(ys) & (np.abs(ys) < 1e4), ys, np.nan)
        all_ys.append(ys)
        ax.plot(xs, ys, linewidth=2, color=color, label=f"y = {cleaned}")

    y_lo, y_hi = robust_axis_limits(np.concatenate(all_ys), fallback=(-1.5, 1.5) if is_trig else (-10, 10))
    ax.set_ylim(y_lo, y_hi)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_xlabel("x (degrees)" if degree_mode else "x")
    ax.set_ylabel("y")
    if len(cleaned_list) > 1:
        ax.legend()
        ax.set_title("Sketch of the given functions")
    else:
        ax.set_title(f"y = {cleaned_list[0]}")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return {"type": "image", "content": f"data:image/png;base64,{encoded}"}


def _resolve_plot_steps(steps: list) -> list:
    """Replaces every {"type": "plot", ...} step the model emitted with a
    real rendered image - or, if that expression can't be parsed/plotted,
    a markdown note saying so, rather than silently dropping the sketch or
    crashing the whole solve over one bad expression."""
    resolved = []
    for s in steps:
        if s["type"] != "plot":
            resolved.append(s)
            continue
        try:
            resolved.append(_render_plot_step(s["content"]))
        except Exception:
            resolved.append({
                "type": "warning",
                "content": f"Couldn't render a sketch for \"{s['content']}\" automatically - work through it on paper using the steps above.",
            })
    return resolved


def solve_with_llm(question: str, topic: str = "", paper: str = "", subject: str = "", max_tokens: int = MAX_OUTPUT_TOKENS):
    """Returns a list of step dicts in the same {"type", "content"} shape
    backend/solver.py's StepRecorder produces, so callers can render the
    result exactly like a normal SymPy solve. Raises on any API failure -
    callers should catch that and fall back to their normal error
    message, the same as an unparseable SymPy input would."""
    client = get_client()
    context_bits = [
        b for b in (
            f"Subject: {subject}." if subject else "",
            f"Paper: {paper}." if paper else "",
            f"Topic: {topic}." if topic else "",
        ) if b
    ]
    context = (" ".join(context_bits) + "\n") if context_bits else ""
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"{context}Question: {question}"}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    try:
        steps = json.loads(_strip_json_fence(raw))
        if not isinstance(steps, list) or not steps:
            raise ValueError("empty or non-list response")
        steps = [
            {
                "type": s.get("type") if s.get("type") in VALID_STEP_TYPES else "markdown",
                "content": str(s.get("content", "")),
            }
            for s in steps
        ]
        return _resolve_plot_steps(steps)
    except (json.JSONDecodeError, ValueError, AttributeError):
        # The model didn't return clean JSON this time - show the raw
        # text as a single step rather than losing the explanation.
        return [{"type": "markdown", "content": raw}]


def solve_full_paper(paper_text: str, paper_title: str = ""):
    """Runs every question detected in a past exam paper's extracted text
    through the LLM fallback, one at a time - powers the Past Papers
    Library's "Solve with AI" action. A single question failing doesn't
    take down the rest of the batch; it's recorded as an error step instead
    of propagating, the same way solve_with_llm's own JSON-parse fallback
    degrades gracefully rather than raising."""
    from .pdf_extract import split_into_questions

    questions = split_into_questions(paper_text)
    results = []
    for q in questions:
        prompt_text = (
            f"{q['text']}\n\n(This question may have multiple sub-parts, e.g. "
            f"{q['number']}.1, {q['number']}.2 - work through each sub-part in turn.)"
        )
        try:
            steps = solve_with_llm(prompt_text, paper=paper_title, max_tokens=3072)
        except Exception as e:
            steps = [{"type": "error", "content": f"Couldn't solve this question: {e}"}]
        results.append({"number": q["number"], "text": q["text"], "steps": steps})
    return results

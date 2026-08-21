"""
Malita (Pty) Ltd — LLM-assisted OCR for photographed maths questions.

backend/ocr.py's Tesseract pipeline is the free, default path for every
photo. This module is a paid-tier assist that gets called two ways:
  1. Automatically, only when Tesseract returns nothing at all (a clean,
     unambiguous failure signal - see app.py / api_server.py).
  2. On demand, via a "Not right? Try AI reading instead" button/endpoint,
     for the more common case Tesseract can't self-detect: it read
     *something*, but read it wrong (a misread digit, a garbled fraction).
     A learner looking at their own photo can judge that far better than
     any heuristic can, so that's a manual action, not automatic.

Uses Claude Haiku 4.5 (see backend/llm_tutor.py for the same reasoning)
and downsizes the photo before sending it - vision token cost scales
with image size, and a phone photo at full resolution (often 3000px+ on
the long edge) is far more detail than reading a single expression
needs. Resizing to 1024px keeps a single read to roughly 1200 input +
50-100 output tokens - well under a cent even before Free-tier
gating (see backend/tiers.py's llm_fallback_enabled) rules it out for
non-paying learners entirely.
"""

import base64
import io
import json

from PIL import Image

from .llm_client import get_client
from .llm_tutor import VALID_STEP_TYPES, _resolve_plot_steps, _strip_json_fence

LLM_MODEL = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 200
MAX_DIMENSION = 1024

# Solving a photo (as opposed to just transcribing one) needs far more
# output budget - a photo often has several sub-questions (1.1.1-1.1.4,
# 1.2, ...), each with its own multi-step solution.
SOLVE_MAX_OUTPUT_TOKENS = 4096

SYSTEM_PROMPT = """You transcribe a single photographed South African Grade 12 (CAPS) mathematics question or expression into plain-text keyboard notation, exactly as a learner would type it into a calculator or search box.

Rules:
- Use ^ for exponents (e.g. x^2), * for multiplication where it's ambiguous, / for fractions, sqrt(...) for square roots.
- Preserve the expression or question exactly as written - do not solve it, simplify it, or add commentary.
- If it's a word problem, transcribe the full text of the problem.
- Reply with ONLY the transcribed text. No explanation, no markdown formatting, no code fences, no quotation marks around it."""


SOLVE_SYSTEM_PROMPT = """You are Malita, a patient Grade 12 (Matric) mathematics tutor for South African CAPS-curriculum learners.

A learner has photographed one or more mathematics questions - there may be several distinct questions or sub-parts in the photo (e.g. 1.1.1, 1.1.2, 1.1.3, 1.2, or entirely separate questions). Read every one of them and solve each fully, step by step, the way a good tutor would on a whiteboard.

Respond with ONLY a raw JSON array - your entire response must start with [ and end with ]. Do NOT wrap it in a ```json code fence or any other markdown, and do NOT include any prose before or after it.

Each element represents ONE question or sub-part, shaped exactly like:
{"number": "1.1.1", "steps": [{"type": "markdown", "content": "..."}, ...]}

"number" should match the question's own numbering as shown in the photo (e.g. "1.1.1", "2", "(a)") - if the photo has no explicit numbering, use "1", "2", "3" in order.

Each entry in "steps" is a step object shaped exactly like: {"type": "markdown", "content": "..."}

Keep explanation and mathematics visually separate, like a worked solution written on paper - explanation on one line, the equation it produces on the next:
- A "markdown" step is short, plain-language prose ONLY - never embed $...$ math inside it.
- Immediately after any markdown step that leads into an equation, expression, or result, add a SEPARATE step with "type": "latex" holding just that expression (plain LaTeX, no $ delimiters - e.g. "content": "x^2 - 5x + 6 = 0", not "$x^2 - 5x + 6 = 0$").
- Never combine a sentence of explanation and its equation into a single step - always two steps, markdown then latex.

Use "type": "success" for exactly one final step per question, stating its final answer, wrapped in single-dollar delimiters, e.g. {"type": "success", "content": "$x = 5$"}.
If a question asks you to sketch, draw, or plot a graph/function, include ONE extra step shaped like {"type": "plot", "content": "x**2 - 4"} at the point where the sketch belongs, using Python/SymPy syntax (** for powers) - Malita renders the actual image itself from this expression.
Keep each question's steps concise: 4-8 steps is typical (explanation + equation pairs, plus the final success step).

Example of a complete, correct response for a photo with two sub-questions:
[{"number": "1.1", "steps": [{"type": "markdown", "content": "Let x be the number of years."}, {"type": "markdown", "content": "Set up the equation:"}, {"type": "latex", "content": "5000(1.08)^x = 10000"}, {"type": "success", "content": "$x \\approx 9.01$"}]}, {"number": "1.2", "steps": [{"type": "markdown", "content": "Factorise the quadratic:"}, {"type": "latex", "content": "(x-2)(x-3)=0"}, {"type": "success", "content": "$x = 2$ or $x = 3$"}]}]"""


def _resize_for_upload(image_bytes: bytes) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    width, height = img.size
    longest = max(width, height)
    if longest > MAX_DIMENSION:
        scale = MAX_DIMENSION / longest
        img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def read_math_photo(image_bytes: bytes) -> str:
    """Returns the transcribed expression/question as plain text, in the
    same keyboard-notation style backend/ocr.py's clean_for_sympy()
    produces, so callers can treat the result identically either way.
    Raises on any API failure - callers should catch that and fall back
    to whatever the Tesseract pass already produced (even if empty)."""
    resized_bytes, media_type = _resize_for_upload(image_bytes)
    encoded = base64.standard_b64encode(resized_bytes).decode("utf-8")

    client = get_client()
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": encoded},
                },
                {"type": "text", "text": "Transcribe the maths in this photo."},
            ],
        }],
    )
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    return raw


def solve_photo_with_llm(image_bytes: bytes):
    """Reads every question/sub-part in a photographed maths problem and
    solves each one fully, in a single vision call - this is the OCR
    screen's primary path (Tesseract proved too unreliable to trust as a
    default; see app.py/api_server.py). Returns a list of {"number",
    "steps"} dicts, the photo-native twin of
    backend.llm_tutor.solve_full_paper()'s per-question shape. Raises on
    any API failure - callers should show their normal error message."""
    resized_bytes, media_type = _resize_for_upload(image_bytes)
    encoded = base64.standard_b64encode(resized_bytes).decode("utf-8")

    client = get_client()
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=SOLVE_MAX_OUTPUT_TOKENS,
        system=SOLVE_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": encoded},
                },
                {"type": "text", "text": "Read and solve every question in this photo."},
            ],
        }],
    )
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    try:
        questions = json.loads(_strip_json_fence(raw))
        if not isinstance(questions, list) or not questions:
            raise ValueError("empty or non-list response")
        result = []
        for q in questions:
            steps = q.get("steps") if isinstance(q, dict) else None
            if not isinstance(steps, list):
                continue
            coerced = [
                {
                    "type": s.get("type") if s.get("type") in VALID_STEP_TYPES else "markdown",
                    "content": str(s.get("content", "")),
                }
                for s in steps
            ]
            result.append({
                "number": str(q.get("number", len(result) + 1)),
                "steps": _resolve_plot_steps(coerced),
            })
        if not result:
            raise ValueError("no valid questions parsed")
        return result
    except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
        # The model didn't return clean JSON this time - show the raw
        # text as a single step rather than losing the explanation.
        return [{"number": "1", "steps": [{"type": "markdown", "content": raw}]}]

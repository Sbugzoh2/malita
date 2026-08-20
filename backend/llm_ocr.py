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

from PIL import Image

from .llm_client import get_client

LLM_MODEL = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 200
MAX_DIMENSION = 1024

SYSTEM_PROMPT = """You transcribe a single photographed South African Grade 12 (CAPS) mathematics question or expression into plain-text keyboard notation, exactly as a learner would type it into a calculator or search box.

Rules:
- Use ^ for exponents (e.g. x^2), * for multiplication where it's ambiguous, / for fractions, sqrt(...) for square roots.
- Preserve the expression or question exactly as written - do not solve it, simplify it, or add commentary.
- If it's a word problem, transcribe the full text of the problem.
- Reply with ONLY the transcribed text. No explanation, no markdown formatting, no code fences, no quotation marks around it."""


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

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

import json
import re

from .llm_client import get_client

LLM_MODEL = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 1024

# app.py's render_steps() does a direct dict lookup with no fallback for
# an unrecognised "type" - a step type outside this set would crash the
# page rather than just render oddly, so any type the model invents gets
# coerced to "markdown" below instead of trusted as-is.
VALID_STEP_TYPES = {"markdown", "latex", "write", "info", "warning", "error", "success", "caption"}


# Deliberately short - see the module docstring on prompt caching (it's
# skipped here since a prefix this size wouldn't clear the ~1024-token
# minimum cacheable length anyway; revisit if this grows to include
# curriculum reference material).
SYSTEM_PROMPT = """You are Malita, a patient Grade 12 (Matric) mathematics tutor for South African CAPS-curriculum learners.

A learner has asked a question the app's built-in solver could not parse - likely a word problem or unusual phrasing. Solve it yourself and explain it step by step, the way a good tutor would on a whiteboard.

Respond with ONLY a raw JSON array - your entire response must start with [ and end with ]. Do NOT wrap it in a ```json code fence or any other markdown, and do NOT include any prose before or after it.

Each element is a step object shaped exactly like: {"type": "markdown", "content": "..."}
"content" may include inline LaTeX using single-dollar delimiters, e.g. "Solve for $x$: $x^2 - 5x + 6 = 0$".
Use "type": "success" for exactly one final step stating the final answer clearly.
Keep it concise: 3-6 steps is typical.

Example of a complete, correct response:
[{"type": "markdown", "content": "Let $x$ be the number of years."}, {"type": "success", "content": "$x = 5$"}]"""


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_json_fence(text: str) -> str:
    """The system prompt asks for a bare JSON array, but the model
    sometimes wraps it in a markdown code fence anyway - strip a
    leading/trailing ``` or ```json fence if present, so a
    well-formed-but-fenced response still parses instead of falling
    back to being shown as one raw, unrendered block."""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text


def solve_with_llm(question: str, topic: str = "", paper: str = ""):
    """Returns a list of step dicts in the same {"type", "content"} shape
    backend/solver.py's StepRecorder produces, so callers can render the
    result exactly like a normal SymPy solve. Raises on any API failure -
    callers should catch that and fall back to their normal error
    message, the same as an unparseable SymPy input would."""
    client = get_client()
    context = f"Paper: {paper}. Topic: {topic}.\n" if topic else ""
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"{context}Question: {question}"}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    try:
        steps = json.loads(_strip_json_fence(raw))
        if not isinstance(steps, list) or not steps:
            raise ValueError("empty or non-list response")
        return [
            {
                "type": s.get("type") if s.get("type") in VALID_STEP_TYPES else "markdown",
                "content": str(s.get("content", "")),
            }
            for s in steps
        ]
    except (json.JSONDecodeError, ValueError, AttributeError):
        # The model didn't return clean JSON this time - show the raw
        # text as a single step rather than losing the explanation.
        return [{"type": "markdown", "content": raw}]

"""
Malita (Pty) Ltd — AI Teacher: live-style narrated lessons for the
Super Premium tier.

Distinct from backend/llm_tutor.py's AI Tutor fallback (which answers one
specific question a learner already has) - this generates a full
structured CAPS lesson on whatever topic a learner asks for, meant to be
read aloud step by step like a real class, not just solved. Reuses
llm_tutor.py's JSON-fence stripping and plot-rendering (same sandboxed
safe_parse() as every other math input in this app - never eval()s
anything from the model or the learner).

Requires ANTHROPIC_API_KEY, same as backend/llm_tutor.py.
"""

import json

from .llm_client import get_client
from .llm_tutor import _strip_json_fence, _render_plot_step, VALID_STEP_TYPES

LLM_MODEL = "claude-haiku-4-5"
# A full lesson runs far longer than a single-question solve (intro,
# several worked examples, a graph, a recap) - needs real headroom so a
# 15-20 step lesson doesn't truncate mid-JSON.
MAX_OUTPUT_TOKENS = 4096

SYSTEM_PROMPT = """You are Malita's AI Teacher - a patient, engaging Grade 12 (Matric) teacher delivering a live-style class to a South African CAPS-curriculum learner, on whichever Mathematics or Physical Sciences topic they ask for.

This is a LESSON, not a quick answer to one question: teach the topic properly, the way a good teacher would in front of a class - a warm intro, the core idea explained simply, one or two fully worked examples, and a short recap at the end. Assume the learner knows the prerequisites for their grade but nothing about this specific topic yet.

Respond with ONLY a raw JSON array - your entire response must start with [ and end with ]. Do NOT wrap it in a ```json code fence or any other markdown, and do NOT include any prose before or after it.

Each element is a step object shaped exactly like: {"type": "markdown", "content": "...", "narration": "..."}

Every step has BOTH:
- "content": what's shown on screen - short markdown-style text, or (for a "latex" step) plain LaTeX with no $ delimiters, e.g. "x^2 - 5x + 6 = 0".
- "narration": what gets READ ALOUD for that same step, in plain spoken English - a full natural sentence, never containing LaTeX, markdown symbols (**, #), or symbols a voice can't pronounce (write "x squared minus five x plus six equals zero", not "x^2-5x+6=0"). Keep narration warm and teacherly, like you're actually speaking to the learner, not just narrating text on a screen.

Step types, same idea as a worked solution but paced like a lesson:
- "markdown" for a short spoken label/transition ("Let's start with the basics.", "Now let's try an example together.") - narration here can be a slightly fuller version of the same sentence.
- "latex" immediately after any markdown step that leads into an equation/expression - content is bare LaTeX, narration is that equation spoken in words.
- "info" for a definition or key fact worth calling out.
- "success" for exactly one step at the very end, a short encouraging recap of what was covered.
- "plot" ONLY when a graph genuinely helps teach the topic - content is a plottable expression in terms of x (SymPy/Python syntax), e.g. "x**2 - 4"; for MORE THAN ONE function on the same axes separate with "|", e.g. "cos(3*x)|sin(x)"; CAPS trig graphs are always in degrees, so if a domain matters append "@lo,hi" in degrees, e.g. "cos(3*x)|sin(x)@-90,180" - narration describes what the graph shows in words.

Keep it a genuine lesson: roughly 12-20 steps (intro, explanation, 1-2 worked examples with full working, recap) - thorough but not padded, and CAPS-accurate for the learner's grade.

Example (topic: "factorising trinomials", Mathematics):
[{"type": "markdown", "content": "Welcome! Today we're learning how to factorise trinomials.", "narration": "Welcome! Today we're learning how to factorise trinomials."}, {"type": "info", "content": "A trinomial has three terms, like x squared plus bx plus c.", "narration": "A trinomial is an expression with three terms, something like x squared, plus b x, plus c."}, {"type": "markdown", "content": "Let's factorise an example together:", "narration": "Let's factorise an example together."}, {"type": "latex", "content": "x^2 + 5x + 6", "narration": "x squared, plus five x, plus six."}, {"type": "markdown", "content": "We need two numbers that multiply to 6 and add to 5: 2 and 3.", "narration": "We need two numbers that multiply to give six, and add up to give five. Those numbers are two and three."}, {"type": "latex", "content": "(x+2)(x+3)", "narration": "So it factorises to x plus two, times x plus three."}, {"type": "success", "content": "Great work! You now know how to factorise a trinomial by finding two numbers that multiply and add correctly.", "narration": "Great work! You now know how to factorise a trinomial by finding two numbers that multiply and add correctly."}]"""


def generate_lesson(subject: str, topic: str) -> list:
    """Returns a list of {"type", "content", "narration"} step dicts for a
    full lesson on `topic` within `subject`. Raises on any API failure or
    unparsable response - callers should show their normal error message,
    same convention as backend/llm_tutor.py.solve_with_llm."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("Please tell me what you'd like a lesson on.")

    client = get_client()
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Subject: {subject}.\nTopic: {topic}"}],
    )
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    steps = json.loads(_strip_json_fence(raw))
    if not isinstance(steps, list) or not steps:
        raise ValueError("Malita's AI Teacher didn't return a lesson - please try again.")

    resolved = []
    for s in steps:
        step_type = s.get("type") if s.get("type") in VALID_STEP_TYPES else "markdown"
        content = str(s.get("content", ""))
        narration = str(s.get("narration", "")) or content

        if step_type == "plot":
            try:
                image_step = _render_plot_step(content)
                resolved.append({**image_step, "narration": narration})
            except Exception:
                resolved.append({
                    "type": "warning",
                    "content": f"Couldn't render a sketch for \"{content}\" automatically.",
                    "narration": "",
                })
            continue

        resolved.append({"type": step_type, "content": content, "narration": narration})

    return resolved

"""
Malita (Pty) Ltd — shared Anthropic client singleton.

Split out of backend/llm_tutor.py so backend/llm_ocr.py can reuse the
same lazily-created client rather than each module managing its own.
Requires ANTHROPIC_API_KEY to be set in the environment.
"""

import anthropic

_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

"""
Malita (Pty) Ltd — PDF text extraction for past papers.

Moved out of app.py for the same reason as backend/ocr.py: both the
Streamlit app and api_server.py need identical extraction behaviour.
"""

import re

import fitz  # PyMuPDF


def extract_pdf_text(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "".join(page.get_text() for page in doc)


_QUESTION_HEADING_RE = re.compile(r"QUESTION\s+(\d+)", re.IGNORECASE)


def split_into_questions(text: str) -> list:
    """Splits a whole exam paper's extracted text into individual questions,
    using the "QUESTION <n>" headings every SA NSC paper uses. Front matter
    before the first heading (cover page, instructions) is discarded.

    Continuation headers ("QUESTION 3 (continued)", printed at the top of
    every page a multi-page question spills onto) are deliberately not
    treated as new question boundaries - only a genuine heading starts a
    new question."""
    boundaries = []
    for m in _QUESTION_HEADING_RE.finditer(text):
        lookahead = text[m.end():m.end() + 20].lower()
        if "continu" in lookahead:
            continue
        boundaries.append(m)

    questions = []
    for i, m in enumerate(boundaries):
        start = m.start()
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        questions.append({"number": m.group(1), "text": text[start:end].strip()})
    return questions

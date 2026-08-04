"""
Malita (Pty) Ltd — PDF text extraction for past papers.

Moved out of app.py for the same reason as backend/ocr.py: both the
Streamlit app and api_server.py need identical extraction behaviour.
"""

import fitz  # PyMuPDF


def extract_pdf_text(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "".join(page.get_text() for page in doc)

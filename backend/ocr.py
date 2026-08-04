"""
Malita (Pty) Ltd — OCR for photographed/scanned maths questions.

Moved out of app.py so both the Streamlit app and api_server.py (used by
the native app's camera/upload flow) call the exact same recognition
code - identical to the reasoning behind backend/solver.py.
"""

import re
import numpy as np
import cv2
import pytesseract


def preprocess_image(pil_image):
    """Upscale + adaptively threshold before OCR. Tesseract badly misreads
    the tiny superscript exponents typical of maths photos (e.g. dropping
    or misreading the "2"/"6" in y=x^2-4x^6) unless the text is reasonably
    large and the threshold is tuned per-image rather than a fixed cutoff."""
    img = np.array(pil_image.convert("L"))

    # Scale up small images — tiny exponents are the single biggest cause
    # of OCR misreads on maths photos.
    img = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    # Otsu's method picks the threshold from each image's own brightness
    # distribution instead of a fixed cutoff, which holds up far better
    # across photos taken in different lighting than a flat "150".
    _, img_bin = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return img_bin


# Restrict recognition to characters that actually appear in maths
# expressions, so Tesseract can't "correct" a faint digit into an
# unrelated symbol (e.g. misreading a small "6" as "®"). No space in the
# whitelist — spaces are stripped afterwards anyway, and a literal space
# here would get split into a separate command-line argument.
_OCR_WHITELIST = (
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "+-*/=()[]{}.,^<>≤≥√π"
)
_TESSERACT_CONFIG = f"--psm 6 -c tessedit_char_whitelist={_OCR_WHITELIST}"


def ocr_with_exponents(img):
    """Character-level OCR (not word-level) so superscript exponents get
    stitched into the right place in the output. This matters because
    Tesseract's word/line segmentation often puts a raised exponent into a
    DIFFERENT internal "line" than the baseline text it belongs to — a
    word-level pass then emits the exponents in the wrong order entirely
    (e.g. "26y=x-4x" instead of "y=x^2-4x^6"). Sorting individual
    characters by their horizontal position avoids that, and comparing
    each digit's vertical position only against the last ALPHANUMERIC
    baseline (not operators like "=", "-", which have unreliable vertical
    extents of their own) avoids false-positive exponents."""
    img_height = img.shape[0]
    boxes_str = pytesseract.image_to_boxes(img, config=_TESSERACT_CONFIG)

    chars = []
    for line in boxes_str.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        ch, left, bottom, _right, top = parts[0], int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
        # image_to_boxes uses a bottom-left origin; flip to top-left so
        # "smaller value = higher up the page", matching normal intuition.
        top_px = img_height - top
        bottom_px = img_height - bottom
        chars.append({"char": ch, "left": left, "bottom": bottom_px, "height": bottom_px - top_px})
    chars.sort(key=lambda c: c["left"])

    result = ""
    prev_char = ""
    prev_bottom, prev_height, have_baseline = 0, 0, False
    for c in chars:
        text = c["char"]
        is_alnum = text.isalnum()

        if is_alnum and text.isdigit() and have_baseline and c["bottom"] < prev_bottom - max(5, prev_height * 0.3):
            result += "^" + text
        elif prev_char and re.match(r"[a-zA-Z]", prev_char) and re.match(r"\d", text):
            result += "*" + text
        else:
            result += text

        prev_char = text
        if is_alnum:
            prev_bottom = c["bottom"]
            prev_height = c["height"]
            have_baseline = True
    return result.replace(" ", "").replace("\n", "")


def clean_for_sympy(text):
    text = re.sub(r"([a-zA-Z])(\d+)", r"\1^\2", text)
    text = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", text)
    return text

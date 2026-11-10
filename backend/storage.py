"""
Malita (Pty) Ltd — Supabase Storage integration.

Used for tutor-verification documents (ID photo, NSC/matric certificate)
that an admin needs to review by eye during manual vetting (see
backend/tutoring.py). Nothing here does any automated document
verification - it only stores the file and hands back a short-lived
signed URL so an admin can look at it; approving/rejecting a tutor is
still an entirely manual decision.

WHY SUPABASE STORAGE (not a local file write, not raw S3):
  - This app's hosting (Render) has no persistent local disk by default -
    a plain file write would get wiped on the next redeploy.
  - Supabase Storage is S3-compatible object storage with a simple REST
    API, supports private buckets, and its free tier (1 GB storage, 50 MB
    per-file limit as of the plan in place when this was built) is far
    more than this feature needs - a handful of tutor applications a
    month, each a few MB.
  - It doesn't require migrating this app's own database to Supabase -
    storage and Postgres are independent Supabase services with their
    own credentials.

REQUIRED ENVIRONMENT VARIABLES (none of this works until these are set):
  SUPABASE_URL                 - e.g. https://xxxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY    - the SERVICE ROLE key (not the anon/public
                                  key - this backend uploads on a tutor
                                  applicant's behalf and must bypass
                                  per-user Row Level Security, so it needs
                                  the elevated key). Keep this secret -
                                  treat it like a database password, never
                                  ship it to a client app.
  SUPABASE_TUTOR_DOCS_BUCKET   - optional, defaults to "tutor-documents".
                                  Create this bucket in the Supabase
                                  dashboard (Storage -> New bucket) and
                                  leave it PRIVATE (not public) - these
                                  are ID photos and certificates.
"""

import os
import uuid

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TUTOR_DOCS_BUCKET = os.environ.get("SUPABASE_TUTOR_DOCS_BUCKET", "tutor-documents")


class StorageError(Exception):
    pass


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }


def upload_tutor_document(
    file_bytes: bytes, content_type: str, *, applicant_email: str, kind: str,
) -> str:
    """Uploads one tutor-verification document and returns its storage
    path (not a URL - the bucket is private, so viewing it later always
    goes through get_signed_url). `kind` is a short label like "id" or
    "matric_certificate", just used to make the stored path readable."""
    if not is_configured():
        raise StorageError(
            "Document storage isn't set up yet (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY "
            "missing) - please apply without attaching documents for now, or contact us."
        )
    email_slug = "".join(c if c.isalnum() else "-" for c in applicant_email.lower())
    ext = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}.get(content_type, "bin")
    path = f"{email_slug}-{uuid.uuid4().hex[:8]}/{kind}.{ext}"

    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_TUTOR_DOCS_BUCKET}/{path}"
    resp = requests.post(
        url, data=file_bytes,
        headers={**_headers(), "Content-Type": content_type},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise StorageError(f"Could not upload document (storage service returned {resp.status_code}).")
    return path


def get_signed_url(path: str, expires_in: int = 3600) -> str:
    """A short-lived (default 1 hour) URL an admin can open to view a
    private document - never a permanent/public link, since these are
    sensitive ID documents."""
    if not is_configured():
        raise StorageError("Document storage isn't set up yet (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY missing).")
    url = f"{SUPABASE_URL}/storage/v1/object/sign/{SUPABASE_TUTOR_DOCS_BUCKET}/{path}"
    resp = requests.post(url, json={"expiresIn": expires_in}, headers=_headers(), timeout=15)
    if resp.status_code != 200:
        raise StorageError(f"Could not generate a viewing link (storage service returned {resp.status_code}).")
    signed_path = resp.json().get("signedURL", "")
    if not signed_path:
        raise StorageError("Storage service didn't return a signed URL.")
    return f"{SUPABASE_URL}/storage/v1{signed_path}"

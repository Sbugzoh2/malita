"""
Malita (Pty) Ltd — one-off CLI to grant/revoke admin status.

Admins bypass the daily AI Tutor solve limit, unlock OCR + PDF (the paid
features) regardless of their subscription tier, and get a "Reset my daily
usage" button in the app sidebar for testing. There's no in-app UI for this
deliberately — it's a rare, high-trust action better done from the server
shell where you already need direct DB access.

Usage:
    python -m backend.set_admin you@example.com
    python -m backend.set_admin you@example.com --revoke
"""

import sys

from .db import get_session, User


def set_admin(email: str, admin: bool = True) -> None:
    email = email.strip().lower()
    with get_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"No account found for {email}.")
            return
        user.is_admin = admin
        print(f"{'Granted' if admin else 'Revoked'} admin access for {email} (user id {user.id}).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.set_admin you@example.com [--revoke]")
        sys.exit(1)
    set_admin(sys.argv[1], admin="--revoke" not in sys.argv)

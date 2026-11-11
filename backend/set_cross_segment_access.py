"""
Malita (Pty) Ltd — one-off CLI to grant/revoke an account's
cross_segment_access override.

Normally a learner account is EITHER "high_school" OR "higher_ed"
(account_type) - every account_type-gated screen (HomeScreen's tile list,
RootNavigator's registered screens, the web app's early-return for
higher_ed accounts, RequestTutorScreen/BrowseTutorsScreen's subject-vs-
module picker) assumes one or the other. cross_segment_access is a rare,
high-trust override that unlocks BOTH experiences for one specific
account, without changing that assumption for anyone else. There's no
in-app UI for this deliberately - same reasoning as backend/set_admin.py:
it's a rare, high-trust action better done from the server shell where
you already need direct DB access.

Usage:
    python -m backend.set_cross_segment_access you@example.com
    python -m backend.set_cross_segment_access you@example.com --revoke
"""

import sys

from .db import get_session, User


def set_cross_segment_access(email: str, enabled: bool = True) -> None:
    email = email.strip().lower()
    with get_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"No account found for {email}.")
            return
        user.cross_segment_access = enabled
        print(
            f"{'Granted' if enabled else 'Revoked'} cross_segment_access for {email} "
            f"(user id {user.id}, account_type={user.account_type})."
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m backend.set_cross_segment_access you@example.com [--revoke]")
        sys.exit(1)
    set_cross_segment_access(sys.argv[1], enabled="--revoke" not in sys.argv)

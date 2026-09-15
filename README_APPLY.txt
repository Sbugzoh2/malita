Malita — fix: reporter-outcome email was silently failing
===========================================================

Bug: when an admin ticked "Let the reporter know the outcome" (on Hide,
Delete, or Dismiss), nothing was actually emailed - even though the
admin-alert email (on a new report being filed) worked fine.

Root cause: in backend/collab.py's _notify_reporter_of_outcome(), the
User row was fetched inside a `with get_session() as db:` block, but
`reporter.email` was read AFTER that block had already closed and
committed. SQLAlchemy expires an object's attributes on commit, so
reading `.email` afterward raised DetachedInstanceError - which the
surrounding try/except silently swallowed (logged, not raised), so the
checkbox looked like it worked but no email ever went out.

Fix: read `reporter.email` while the session is still open (assign it to
a plain local variable before the `with` block exits), the same way
_notify_admins_of_report already did it correctly.

Verified live: reproduced the exact DetachedInstanceError in a local
server's logs before the fix, then confirmed after the fix that the
reporter-outcome email path completes cleanly with no exception (it logs
"send_email: not configured" only because this sandbox has no
SMTP/Brevo credentials - in your deployed environment, with those
already configured, this will now actually send).

How to apply
------------
1. Copy backend/collab.py into your local clone, overwriting the existing
   file (this is the same file from the previous "moderation controls"
   tarball, with just this one fix added on top - if you already applied
   that tarball, this file already includes those changes too, so
   there's nothing else to reconcile).

2. From your repo root:
     git add backend/collab.py
     git commit -m "Fix reporter-outcome email silently failing with DetachedInstanceError"
     git push -u origin claude/math-tutor-app-script-7ac98e

3. Nothing else to run - no new env vars, no migration.

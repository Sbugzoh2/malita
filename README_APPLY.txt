Malita — Collaboration Forum moderation controls
=================================================

Why this tarball exists: this Claude Code session still doesn't have GitHub
push access to Sbugzoh2/malita (the org hasn't installed the Claude GitHub
App yet), so the commit is already made locally but can't be pushed from
here. Apply it from your own machine with your own git identity instead.

What changed (already committed locally as one commit, message below):

1. backend/collab.py
   - report_content() now emails every admin user when a new report is
     filed (best-effort — logs and swallows failures, same pattern as the
     rest of the app's email sending; never blocks the report itself).
   - resolve_report(report_id, action, notify_reporter=False, note="")
     replaces the old resolve_report(report_id, hide_content: bool):
       action = "hide"   -> same as before, just sets is_hidden
       action = "delete" -> permanently deletes the content. Deleting a
                            question also deletes its answers; deleting a
                            top-level answer also deletes its direct
                            replies (replies are capped at one level deep,
                            so there's never a third level to worry about).
       action = "dismiss" -> no content change, just marks the report
                            resolved (same as before).
     notify_reporter=True emails the original reporter the outcome, with
     an optional admin note appended.

2. api_server.py
   - CollabResolveRequest is now {action: str, notify_reporter: bool = False,
     note: str = ""} instead of {hide: bool}.
   - POST /collab/reports/{id}/resolve passes all three through.

3. app.py
   - The admin moderation queue (inside "🤝 Collaboration Forum") now shows
     three buttons per report — Hide content / Delete content / Dismiss
     report — plus a "Let the reporter know the outcome" checkbox and an
     optional note text field.

4. mobile/src/api/client.ts
   - Added CollabReport type, fetchCollabReports(), resolveCollabReport().

5. mobile/src/screens/CollabScreen.tsx
   - Added a new admin-only "Moderation queue" section (mirrors the web
     one exactly — same three actions, same notify checkbox/note field).
     Only renders when me.is_admin is true. No new screen/route was
     needed — it lives right at the top of the existing Collab screen.

Tested before packaging (see the two test runs below for full detail):
  - A full backend/API test (register 3 users incl. one admin, create a
    question + top-level answer + a reply, report it, list/resolve via
    every action, confirm cascade delete removes the question AND its
    answer AND its reply, confirm hidden content is excluded from
    listings but not deleted, confirm a bogus action is rejected with
    400, confirm a non-admin gets 403 from the reports endpoints).
  - A live Streamlit + Playwright pass through the actual admin UI:
    expanded the moderation queue, ticked "notify reporter", typed a
    note, clicked Delete content, and confirmed the report and its
    question both disappeared from the queue/listing.
  - Confirmed (via server logs) that both the admin-notify and the
    reporter-notify code paths actually execute end-to-end (they log
    "not configured" only because this sandbox has no SMTP/Brevo
    credentials set — in production, with those already configured for
    password-reset emails, these will send real emails the same way).

No database migration is needed — no new columns were added this time
(CollabReport already had everything needed; is_hidden already existed on
CollabQuestion/CollabAnswer for the "hide" path, and "delete" just removes
rows outright).

How to apply
------------
1. Copy these files into your local clone, overwriting the existing ones:
     api_server.py
     app.py
     backend/collab.py
     mobile/src/api/client.ts
     mobile/src/screens/CollabScreen.tsx

2. From your repo root:
     git add api_server.py app.py backend/collab.py \
             mobile/src/api/client.ts mobile/src/screens/CollabScreen.tsx
     git commit -m "Add report-review moderation controls: admin email alerts, delete option, reporter outcome notice"
     git push -u origin claude/math-tutor-app-script-7ac98e

   (Use your own commit message if you'd rather — the one above matches
   what was committed in this session, minus its Co-Authored-By/session
   trailer, which you can drop or keep as you prefer.)

3. Nothing else to run — no new env vars, no new migrations. Your existing
   email setup (whatever gets password-reset emails delivered today) is
   reused automatically for both the admin-alert and reporter-notice
   emails.

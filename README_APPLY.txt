Overwrite these files with the ones in this folder:
  app.py
  api_server.py
  backend/db.py
  backend/collab.py
  mobile/src/api/client.ts
  mobile/src/screens/CollabQuestionDetailScreen.tsx

Then:
  git add app.py api_server.py backend/db.py backend/collab.py \
          mobile/src/api/client.ts mobile/src/screens/CollabQuestionDetailScreen.tsx
  git commit -m "Drop the @ from mentions; let authors edit their own posts"
  git push origin main

No manual SQL needed this time - the new is_edited column is
registered in the same self-healing _ensure_column check that already
runs on startup (the one added after the parent_id incident), so it
gets added automatically the next time the app starts. Still worth
double-checking your Supabase logs after this deploy to confirm it
picked up cleanly, given what happened last time.

Rebuild the mobile app via EAS afterward.

What changed:
1. The reply-tagging prefix no longer includes "@" - just the plain
   name now.
2. Question and answer authors can edit their own post after posting
   (checked server-side - a non-owner gets rejected). Edited content
   shows a plain "(edited)" marker. Web's edit form covers title+body;
   mobile's covers body only.

Verified end-to-end: a live server test confirming edit endpoints
reject a non-owner and accept the real owner, the migration path
against a simulated copy of the actual current production schema, and
the real web UI (edit form pre-fills correctly, "(edited)" appears
after saving, Edit only shows for content you actually own).

Overwrite these files in your repo with the ones in this folder:
  app.py
  api_server.py
  backend/db.py
  backend/tiers.py
  mobile/src/api/client.ts
  mobile/src/screens/HomeScreen.tsx
  mobile/src/navigation/RootNavigator.tsx

Add these NEW files:
  backend/collab.py
  mobile/src/screens/CollabScreen.tsx
  mobile/src/screens/CollabQuestionDetailScreen.tsx

Then:
  git add app.py api_server.py backend/db.py backend/collab.py backend/tiers.py \
          mobile/src/api/client.ts mobile/src/screens/HomeScreen.tsx \
          mobile/src/navigation/RootNavigator.tsx mobile/src/screens/CollabScreen.tsx \
          mobile/src/screens/CollabQuestionDetailScreen.tsx
  git commit -m "Add Collaborate: a Learner/Premium Q&A board"
  git push origin main

No manual DB migration needed - the new tables (collab_questions,
collab_answers, collab_reports) are created automatically the next
time init_db() runs (both app.py and api_server.py already call it on
startup).

Rebuild the mobile app via EAS afterward - this adds new screens and
navigation routes.

What this is (per your 3 decisions): an async Q&A board (not live
chat), restricted to Learner/Premium tiers, with reports going into a
manual admin review queue (no automated moderation). Learners post a
question tagged by subject/topic, others answer, and anyone can report
a question or answer - admins see a moderation queue (in the web app's
Collaborate page, and via GET /collab/reports on the API) where they
can hide the content or dismiss the report.

Tested end-to-end locally before sending: tier gating (free tier is
correctly blocked), posting a question, answering it, reporting an
answer, and an admin resolving that report by hiding the content -
confirmed the answer then disappears from the question. Also walked
through the actual web UI live (Playwright): posting a question,
viewing it, answering it, and seeing both report buttons render
correctly.

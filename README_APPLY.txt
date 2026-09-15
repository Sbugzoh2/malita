Overwrite these files with the ones in this folder:
  app.py
  api_server.py
  backend/db.py
  backend/collab.py
  mobile/src/api/client.ts
  mobile/src/screens/CollabScreen.tsx
  mobile/src/screens/CollabQuestionDetailScreen.tsx

Add this NEW file:
  mobile/src/latex/MixedMathText.tsx

Then:
  git add app.py api_server.py backend/db.py backend/collab.py \
          mobile/src/api/client.ts mobile/src/latex/MixedMathText.tsx \
          mobile/src/screens/CollabScreen.tsx mobile/src/screens/CollabQuestionDetailScreen.tsx
  git commit -m "Add math rendering and threaded @mention replies to Collaborate"
  git push origin main

No DB migration script needed - the new collab_answers.parent_id
column is added automatically by SQLAlchemy's create_all() the next
time init_db() runs, same as the original tables.

Rebuild the mobile app via EAS afterward - MixedMathText is a new file
these screens now import.

What this adds, on top of the Collaborate board from before:

1. Math rendering - on web, this needed almost no code: Streamlit
   already renders inline $...$ as a real equation (KaTeX) inside
   st.write/st.markdown. Both compose boxes (question and answer) now
   just have a caption teaching learners the $...$ convention. Mobile
   has no native equivalent, so this adds MixedMathText.tsx, which
   splits text on $...$ and renders the math parts through the
   existing LatexView component inline with the surrounding prose.

2. Threaded replies + @mentions - tapping/clicking "Reply" on any
   answer targets that answer specifically (capped at one level deep -
   replying to a reply automatically redirects onto the original
   top-level answer instead of growing a third level) and prefills the
   compose box with "@AnswererName " so it's clear who's being
   addressed, especially useful once an answer has multiple replies.
   Replies render indented with a "↳" marker under their parent
   answer, on both web and mobile.

Verified end-to-end before sending: a full question -> answer -> reply
-> reply-to-a-reply chain against a live server (confirmed the
reply-to-reply correctly collapses onto the top-level answer), and the
actual web UI in a real browser (math rendering, indentation, and the
"Replying to X" banner surviving an unrelated page rerun without going
blank - a real bug caught and fixed during that pass, along with a
second bug where the tip text's own literal "$...$" was being
misinterpreted as math by Streamlit).

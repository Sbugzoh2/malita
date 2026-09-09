Overwrite these 3 files with the ones in this folder:
  backend/email_util.py
  api_server.py
  app.py

Then:
  git add backend/email_util.py api_server.py app.py
  git commit -m "Send a real clickable reset link instead of relying on auto-linkify"
  git push origin main

What changed: both the web and mobile password-reset emails now send a
real HTML button (a genuine <a href> link), not just plain text. The
mobile email in particular now links straight to the web app's existing
password-reset page instead of emailing a bare code you had to copy and
paste into the app - the code is still included underneath the button
for anyone who'd rather type it in manually.

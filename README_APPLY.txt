Overwrite these files with the ones in this folder:
  app.py
  api_server.py
  mobile/src/navigation/RootNavigator.tsx
  mobile/src/screens/CollabScreen.tsx
  mobile/src/screens/HomeScreen.tsx

Then:
  git add app.py api_server.py mobile/src/navigation/RootNavigator.tsx \
          mobile/src/screens/CollabScreen.tsx mobile/src/screens/HomeScreen.tsx
  git commit -m "Fix nav crash on a stale session value; rename Collaborate -> Collaboration Forum"
  git push origin main

No DB migration needed for this one - just code. Rebuild mobile via
EAS afterward.

What this fixes: the ValueError crash happens whenever
st.session_state["nav_mode"] holds a value no longer in the current
_NAV_OPTIONS list - which is exactly what would have happened to
anyone who had "Collaborate" selected in their browser tab at the
moment this rename went live, and possibly explains the error you
hit. Fixed defensively: if the stored nav value doesn't match any
current option, it now resets to Home instead of crashing. Verified
directly by seeding that exact stale value into a test session with
Streamlit's own testing framework and confirming no exception.

Also renamed "Collaborate" -> "Collaboration Forum" everywhere it's
shown to users, on both web and mobile - same feature, same routes,
just the display name.

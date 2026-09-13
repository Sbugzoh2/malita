Overwrite these files in your repo with the ones in this folder:
  app.py
  api_server.py
  backend/practice.py
  mobile/src/api/client.ts
  mobile/src/screens/HomeScreen.tsx
  mobile/src/navigation/RootNavigator.tsx

Add this NEW file:
  mobile/src/screens/LearnerProfileScreen.tsx

Then:
  git add app.py api_server.py backend/practice.py mobile/src/api/client.ts \
          mobile/src/screens/HomeScreen.tsx mobile/src/navigation/RootNavigator.tsx \
          mobile/src/screens/LearnerProfileScreen.tsx
  git commit -m "Add Learner Profile to the mobile app"
  git push origin main

Rebuild the mobile app (EAS build) afterward to pick this up - it's a
new screen/navigation route, not something that updates via a simple
reload.

What this actually is: Learner Profile / Activity History only ever
existed on the web (Streamlit) app - the mobile app never had a
Learner Profile screen or a backend endpoint for it at all, so there
was nothing "removed." This adds it to mobile for the first time:
- New "Learner Profile" tile on the Home screen
- New screen: Subject picker, Questions Solved/Marks Earned stats,
  badge + progress bar, a per-topic breakdown, and Recent Activity -
  reading from the same solved_questions data the web version uses
- New GET /learner-profile API endpoint backing it

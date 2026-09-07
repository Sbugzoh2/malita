How to apply this update to your local malita clone
=====================================================

1. Copy these files into your local repo, overwriting the existing ones:
   - docs/privacy-policy.html   (new file)
   - docs/.nojekyll             (new file, fixes the GitHub Pages Jekyll build error)
   - mobile/src/screens/AITutorScreen.tsx   (overwrite existing file)

2. Delete this file (it's unused/orphaned, nothing references it anymore):
   - mobile/src/screens/SolvedPaperScreen.tsx

3. From your repo root, commit and push:
   git add docs/privacy-policy.html docs/.nojekyll mobile/src/screens/AITutorScreen.tsx
   git rm mobile/src/screens/SolvedPaperScreen.tsx
   git commit -m "Add privacy policy page, fix Pages Jekyll build, remove orphaned screen"
   git push origin main

4. Before using the privacy policy URL in Google Play Console, open
   docs/privacy-policy.html and fill in the two placeholders:
   - contact email (currently privacy@malita.app)
   - physical/postal address

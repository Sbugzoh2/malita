Malita — use the branded logo as the app's actual favicon
============================================================

You sent the Play Store feature graphic (MALITA title + the graduation
cap badge) and asked for that to become the app's logo/icon. Good news:
it mostly already is - mobile/assets/icon.png (the graduation cap on
blue) is already the mobile app icon, the Android adaptive icon, the PWA
home-screen icons, and the logo shown in the web app's own header. The
feature graphic's icon badge is literally a resized, rounded-corner copy
of that same file (see the make_feature_graphic.py script from earlier
in this session) - so nothing needed to change there.

The one real gap: the browser TAB favicon (what shows in the tab/bookmark
bar, distinct from the in-page header logo) was still a plain 🎓 emoji,
not this branded image. Fixed that, and added a matching favicon to the
GitHub Pages privacy policy page too, which had no favicon at all.

What changed
------------
1. app.py
   - st.set_page_config(..., page_icon="🎓") -> page_icon="assets/favicon.png"
     (assets/favicon.png already existed - a 48x48 copy of the same
     graduation-cap icon - it just wasn't wired up as the tab favicon.)

2. docs/privacy-policy.html
   - Added <link rel="icon" type="image/png" href="favicon.png" /> in <head>.

3. docs/favicon.png (new file)
   - Copy of assets/favicon.png, placed alongside the privacy policy page
     so the relative href resolves on GitHub Pages.

Verified live: ran the Streamlit app and used Playwright to confirm the
page actually serves <link rel="icon" href=".../favicon.png"> and that
URL returns a real 1KB PNG (not a 404) - the browser tab now shows the
graduation-cap icon instead of a generic Streamlit icon.

How to apply
------------
1. Copy these files into your local clone, overwriting where they exist:
     app.py
     docs/privacy-policy.html
     docs/favicon.png   (new file)

2. From your repo root:
     git add app.py docs/privacy-policy.html docs/favicon.png
     git commit -m "Use the branded graduation-cap icon as the app's favicon everywhere"
     git push -u origin claude/math-tutor-app-script-7ac98e

3. Nothing else to run - no new env vars, no migration, no mobile rebuild
   needed (the mobile app icon was already this logo).

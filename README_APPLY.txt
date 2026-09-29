Malita — AI Teacher: new Super Premium tier + narrated live-style lessons
===========================================================================

What this is
-------------
A brand new subscription tier, "Super Premium", that unlocks everything
Premium already has PLUS a new "AI Teacher": the learner types any topic
they want (in either subject, free text - "projectile motion", "chemical
equilibrium", whatever) and gets a full structured CAPS lesson - intro,
explanation, one or two worked examples, an optional graph, a recap -
read aloud step by step, like an actual live class, not just a quick
answer to one question.

Price: R199.99/month as a placeholder in backend/tiers.py - change the
one `"price_zar": 199.99` line to whatever you actually want to charge;
everything else (checkout, upgrade UI, mobile Subscription screen) reads
that value automatically, nothing else to touch.

How narration works (and why no new API cost)
-----------------------------------------------
Every lesson step carries both what's shown on screen and a separate
spoken-language version (no LaTeX, no markdown symbols - "x squared plus
five x" instead of "x^2+5x"). Reading it aloud is done entirely by the
DEVICE's own text-to-speech:
  - Web: the browser's built-in SpeechSynthesis API (zero cost, zero new
    dependency, works offline once the lesson is loaded)
  - Mobile: expo-speech, which uses the phone's own OS-level TTS engine
This avoids the exact network-blocking problem gTTS hit earlier - there's
no TTS service call at all, so there's nothing to fail or cost money per
minute.

What changed
-------------
Backend:
  - backend/tiers.py - new "super_premium" tier config +
    can_use_ai_teacher() gate function, same pattern as every other
    tier-gated feature in this app.
  - backend/ai_teacher.py (NEW FILE) - generates a lesson via Claude
    (reuses backend/llm_tutor.py's JSON-fence-stripping and plot
    rendering, including the multi-function/degree-domain graph support
    from the last delivery), returning a list of steps each with both
    "content" and "narration".
  - api_server.py - new POST /ai-teacher/lesson endpoint, gated the same
    way the Collaboration Forum endpoints already are.
  - IMPORTANT FIX while wiring this up: admin users were hardcoded to
    get "premium" as their effective tier in 8 places across app.py and
    api_server.py - meaning once Super Premium existed, admins would
    have been LOCKED OUT of their own new top-tier feature. Fixed by
    replacing the hardcoded "premium" string with TIER_ORDER[-1]
    everywhere, so admins always get whatever the actual highest tier
    is, even if you add a 5th tier later.
  - backend/db.py - the TIERS tuple now includes "super_premium" (a
    documentation-only tuple, not otherwise used, but kept accurate).

Web (app.py):
  - New "🧑‍🏫 AI Teacher" item in the sidebar nav and a new gold Home
    tile, matching the existing tile grid style exactly.
  - Subject picker + free-text topic box + "Start Lesson" button.
  - Once a lesson loads: "▶️ Read Aloud" / "⏹ Stop" buttons that narrate
    every step in order via the browser's SpeechSynthesis API - this
    keeps narrating even through an unrelated Streamlit rerun elsewhere
    on the page, since it's tied to the actual browser tab, not the
    component that created it (same technique the existing PWA
    install-prompt code already uses).
  - Gated with the same "upgrade from the sidebar" pattern as the
    Collaboration Forum.

Mobile:
  - mobile/src/screens/AITeacherScreen.tsx (NEW FILE) - subject picker,
    topic input, Start Lesson button, reuses AITutorScreen's exported
    StepView component to render the lesson exactly like an AI Tutor
    solve, plus Read Aloud/Stop buttons wired to expo-speech.
  - mobile/src/api/client.ts - LessonStep type + fetchAITeacherLesson().
  - mobile/src/navigation/RootNavigator.tsx - new screen registered.
  - mobile/src/screens/HomeScreen.tsx - new gold "AI Teacher" tile.
  - mobile/package.json - added "expo-speech": "~57.0.3" (matches the
    other expo-* package versions already pinned for Expo SDK 57).

Verified before packaging
---------------------------
- Full web flow via a live Streamlit server + Playwright: registered a
  Super Premium test user, opened AI Teacher, typed a topic, got back a
  rendered lesson (info box, LaTeX equations, success recap) with working
  Read Aloud/Stop buttons - screenshots below if you want to see them.
  Also registered a Premium (not Super Premium) user and confirmed they
  correctly see the upsell message instead. Also confirmed the sidebar's
  Upgrade dropdown automatically lists "Super Premium — R199.99/month"
  with a working upgrade button, with zero code changes needed beyond
  the tiers.py entry.
- Mobile: ran a full `npx tsc --noEmit` across the entire mobile app (not
  just the new file) - zero errors. Verified tsc actually catches errors
  first, by deliberately introducing and then reverting a type error, so
  the clean pass is a real signal, not a silently-skipped check.
- The actual "call Claude and generate a real lesson" path couldn't be
  exercised live in this sandbox (no ANTHROPIC_API_KEY available here),
  so the UI/rendering/narration tests above used a mocked lesson response
  standing in for that one call - the call itself is the same
  `client.messages.create(...)` pattern already proven working in
  backend/llm_tutor.py elsewhere in this app.

How to apply
------------
1. Copy these files into your local clone, overwriting where they exist:
     api_server.py
     app.py
     backend/db.py
     backend/tiers.py
     backend/ai_teacher.py                      (new file)
     mobile/package.json
     mobile/src/api/client.ts
     mobile/src/navigation/RootNavigator.tsx
     mobile/src/screens/HomeScreen.tsx
     mobile/src/screens/AITeacherScreen.tsx      (new file)

2. From your repo root:
     git add api_server.py app.py backend/db.py backend/tiers.py backend/ai_teacher.py \
             mobile/package.json mobile/src/api/client.ts \
             mobile/src/navigation/RootNavigator.tsx mobile/src/screens/HomeScreen.tsx \
             mobile/src/screens/AITeacherScreen.tsx
     git commit -m "Add AI Teacher: a new Super Premium tier with narrated live-style lessons"
     git push -u origin claude/math-tutor-app-script-7ac98e

3. In mobile/, run your usual install (npm install / npx expo install) to
   pull in the new expo-speech dependency before your next build.

4. No database migration needed - "tier" is just a free-text column
   already, no schema change required for the new "super_premium" value.

5. Before going live, decide on the real Super Premium price and update
   the one line in backend/tiers.py if R199.99 isn't right.

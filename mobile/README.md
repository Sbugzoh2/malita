# Malita — native app (React Native / Expo)

The native iOS/Android rewrite. Talks to `../api_server.py`, not to the
Streamlit app — see the repo root `README.md` section 8 for the overall
status and what's ported so far (currently: auth + the Algebra topic).

## Setup

```bash
cd mobile
npm install
```

## Run against a local API server

In one terminal, from the repo root:
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8002
```

In another terminal:
```bash
cd mobile
npm start          # then press `i` for iOS simulator, `a` for Android, `w` for web
```

By default the app points at `http://localhost:8002` (see `app.json`'s
`expo.extra.apiBaseUrl`). **Two things to change this for a real device:**

- **Physical phone via Expo Go**: `localhost` means the phone itself, not
  your computer — set `apiBaseUrl` to your computer's LAN IP instead
  (e.g. `http://192.168.1.23:8002`), and make sure the phone's on the same
  Wi-Fi.
- **Production build**: point `apiBaseUrl` at your deployed `api_server.py`
  (same hosting story as `webhook_server.py` — Render, Railway, etc).

## What works today

- Register / log in / log out (bearer token, persisted via AsyncStorage)
- Home screen with subject tiles
- AI Tutor → **Algebra** topic only, full step-by-step solving identical
  to the Streamlit app (same `backend/solver.py` code underneath)
- Daily free-tier usage limit is enforced and shown

## What's not built yet

Every other AI Tutor topic, OCR, PDF past papers, Practice Questions,
Learner Profile, Formula Sheet, subscriptions/payments, and forgot-password
email delivery (the API call exists but there's no "enter new password"
screen yet — only used via the web app's reset link today). LaTeX steps
are currently shown as raw math source in a monospace box rather than
fully typeset — a KaTeX-based renderer is a reasonable next improvement
once more topics are ported.

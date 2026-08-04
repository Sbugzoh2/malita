# Malita (Pty) Ltd — Matric Maths Master

AI-powered Grade 12 Mathematics tutor for South African learners, with
accounts, subscription tiers, and PayFast billing.

## What's in this folder

```
app.py                 The Streamlit app learners use (tutor, practice, OCR, PDF)
webhook_server.py       Tiny FastAPI service that receives PayFast payment webhooks
api_server.py           REST API for the React Native app (see "Native app" section below)
backend/
  db.py                 Database models (users, subscriptions, usage, webhook log)
  auth.py               Registration / login (bcrypt password hashing)
  tiers.py               Free / Learner / Premium tier definitions - edit prices here
  usage.py               Daily AI Tutor solve-limit tracking for the Free tier
  payfast.py             Checkout link builder + webhook signature verification
  math_utils.py          Safe SymPy expression parsing, shared by app.py and api_server.py
  solver.py               Pure math-solving logic (currently: Algebra), shared the same way
requirements.txt
packages.txt            OS packages needed on Linux hosting (Tesseract for OCR)
.env.example             Copy to .env and fill in your real values
```

## 1. Local setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Run the app:
```bash
streamlit run app.py
```

Run the webhook receiver (separate terminal — needed for payments to work):
```bash
uvicorn webhook_server:app --host 0.0.0.0 --port 8001
```

Run the native-app API (separate terminal — only needed once the React
Native app is in the picture; the Streamlit app above doesn't need it):
```bash
uvicorn api_server:app --host 0.0.0.0 --port 8002
```

The `.env.example` file already contains PayFast's published **Sandbox**
test credentials, so subscription upgrades will work locally out of the box
in test mode — no real money moves in Sandbox.

## 2. How the pieces fit together

- **app.py** is everything learners see: login/register, the AI Tutor,
  Practice Questions, OCR, PDF extraction, and the sidebar "Upgrade" panel.
- Streamlit can't reliably receive webhook POSTs (it's a single frontend,
  not a general backend), so **webhook_server.py** is a separate, tiny
  service that does exactly one job: listen for PayFast's payment
  notifications, verify them, and update the subscription in the database
  that app.py also reads from.
- Both processes share the same `DATABASE_URL`, so as long as they point at
  the same database, a payment confirmed by the webhook shows up instantly
  next time the learner's page in app.py reruns.

## 3. Before you accept real payments — test this exact flow

1. Register an account and confirm you land on the **Free** tier.
2. Use the AI Tutor 5 times and confirm the 6th is blocked with the upgrade
   message.
3. Click "Upgrade to Learner", complete a Sandbox payment on PayFast's test
   checkout, and confirm:
   - `webhook_server.py`'s terminal shows the ITN was received and verified.
   - Refreshing app.py shows you now on the Learner tier with OCR/PDF unlocked.
4. **Verify the signature against PayFast's own tool** before going live:
   PayFast's dashboard (Sandbox → Settings → "Signature validator") lets you
   paste a sample parameter set and see what signature *they* compute.
   Compare it against `backend/payfast.generate_signature()`'s output for
   the same inputs. PayFast's documentation has been inconsistent over the
   years about field ordering for outgoing signatures — this one manual
   check catches that before it costs you a failed payment in production.
5. Only once that all checks out, switch `PAYFAST_SANDBOX=false` and put in
   your real Merchant ID / Key / Passphrase from your live PayFast account.

## 4. Deployment — concrete step-by-step

This uses three free/cheap services that work well together: **Supabase**
(Postgres database), **Render** (the webhook service), and **Streamlit
Community Cloud** (the app itself). None of these require a credit card to
start, and you can move to a VPS later if you outgrow them.

### 4.1 Push this project to GitHub
Both Render and Streamlit Cloud deploy from a GitHub repo.
```bash
cd malita
git init
git add .
git commit -m "Malita launch v1"
# create a new repo on github.com, then:
git remote add origin https://github.com/<your-username>/malita.git
git branch -M main
git push -u origin main
```
`.env` is only a local template — never commit your real secrets. Add a
`.gitignore` with at least: `.env`, `*.db`, `__pycache__/`.

### 4.2 Database — Supabase
1. Create a free project at supabase.com.
2. Project Settings → Database → copy the connection string (URI format).
3. It looks like `postgresql://postgres:[password]@[host]:5432/postgres` —
   rewrite it for SQLAlchemy as:
   `postgresql+psycopg2://postgres:[password]@[host]:5432/postgres`
4. That's your `DATABASE_URL` for both services below.

### 4.3 Webhook service — Render
1. New → Web Service → connect your GitHub repo → Render will detect
   `render.yaml` automatically (included in this project).
2. Fill in the environment variables it asks for: `DATABASE_URL` (from
   Supabase), and your PayFast live `PAYFAST_MERCHANT_ID` /
   `PAYFAST_MERCHANT_KEY` / `PAYFAST_PASSPHRASE` (see section 5 below).
3. Deploy. Once live, note the URL Render gives you, e.g.
   `https://malita-payfast-webhook.onrender.com` — your real
   `notify_url` is `https://malita-payfast-webhook.onrender.com/payfast/notify`.
4. Visit `https://<your-render-url>/health` to confirm it's up.

### 4.4 The app — Streamlit Community Cloud
1. share.streamlit.io → New app → pick your GitHub repo → main file `app.py`.
2. In "Advanced settings" → Secrets, add (same values as your `.env`):
   ```
   DATABASE_URL = "postgresql+psycopg2://postgres:...@...supabase.co:5432/postgres"
   APP_BASE_URL = "https://<your-app-name>.streamlit.app"
   APP_WEBHOOK_URL = "https://malita-payfast-webhook.onrender.com/payfast/notify"
   PAYFAST_MERCHANT_ID = "..."
   PAYFAST_MERCHANT_KEY = "..."
   PAYFAST_PASSPHRASE = "..."
   PAYFAST_SANDBOX = "false"
   ```
3. Deploy. `packages.txt` is already included so Tesseract installs
   automatically for OCR.

At this point learners hit your Streamlit Cloud URL, sign up, and pay via
a checkout link that redirects to PayFast and notifies your Render service
— all three pieces talking through the shared Supabase database.

## 5. PayFast live setup

I can't create your PayFast account for you — it needs your own business
and banking details — but here's exactly what to do:

1. **Sign up / log in** at payfast.io as Malita (Pty) Ltd, and complete
   their merchant verification (company registration docs, bank account
   details — this is what lets them pay *you* out).
2. **Enable Recurring Billing** — this isn't on by default for every
   account; if you don't see a "Recurring Billing" or "Subscriptions"
   option in your dashboard, contact PayFast support and ask them to
   enable it. It requires a passphrase to be set (next step).
3. **Set a Salt Passphrase**: Dashboard → Settings → Account Information →
   "Salt Passphrase". Put the same value in `PAYFAST_PASSPHRASE` in Render
   and Streamlit Cloud's secrets.
4. **Copy your live Merchant ID and Merchant Key**: Dashboard → Settings →
   Integration. These replace the Sandbox test values (`10000100` /
   `46f0cd694581a`) everywhere in your deployed environment variables.
5. **Run PayFast's own signature validator** (Dashboard → Integration →
   there's a signature-testing tool) with a sample parameter set, and
   compare the signature it produces to what
   `backend/payfast.generate_signature()` produces for the identical
   input. This is the one manual check worth doing every time — PayFast's
   documentation has been genuinely inconsistent about field ordering
   across different doc pages, and this check catches a mismatch before a
   real learner's payment fails on it.
6. **Do one real payment yourself** first (small amount, your own card)
   through the live checkout end-to-end before telling anyone else the
   subscription is open, and confirm:
   - The webhook logs it (`webhook_events` table, or Render's logs).
   - Your own account flips to the paid tier in the app.
   - The money actually reflects in your PayFast dashboard (settlement to
     your bank takes a few business days, but the dashboard balance
     updates immediately).
7. Flip `PAYFAST_SANDBOX=false` in both Render and Streamlit Cloud (already
   set in `render.yaml`; set it in Streamlit Cloud's secrets too), and
   you're live.


## 6. Business / legal checklist for South Africa (not legal advice)

A few things worth sorting out before/around launch — I'm not a lawyer, so
treat this as a starting checklist to take to one, not a substitute:

- **CIPC registration** for Malita (Pty) Ltd, if not already finalised.
- **POPIA compliance**: you'll be holding learner names, emails, school
  names, and payment references. You'll want a privacy policy, a lawful
  basis for processing (consent at signup is simplest), and a way for
  users to request deletion of their data.
- **Terms of Service**: especially around subscription billing/cancellation
  (PayFast's recurring billing lets customers cancel from their own PayFast
  account too — make sure your ToS and support process account for that).
  Also consider what happens to `usage_logs`/history if someone deletes
  their account.
- **VAT**: if you cross the R1 million/year compulsory registration
  threshold (or want to register voluntarily earlier), you'll need to
  issue VAT invoices — PayFast's own dashboard can help itemise this.
- **School/institutional sales**: if you plan to sell seat licenses to
  schools rather than individual learners (often a much bigger and more
  stable revenue channel than direct-to-learner subscriptions), that's a
  different flow — bulk accounts, an invoice-based payment option, and a
  simple admin view for a teacher to see their class's usage. Happy to
  help build that next if it's part of your plan.

## 7. What's intentionally NOT built yet

Keeping this launch-ready without overbuilding — these are reasonable
next steps once you have real users:
- Password reset / "forgot password" email flow (currently: users must
  contact you to be manually reset in the DB).
- Email verification at signup.
- Admin dashboard (currently: `is_admin` column exists on `User` but no UI
  uses it yet).
- Automated handling of failed recurring payments beyond marking the
  subscription `past_due` (e.g. a dunning email sequence).

## 8. Native app (React Native) — status

The long-term goal is a real iOS/Android app (not just the installable
PWA the Streamlit site already supports). Streamlit can't serve a REST
API, so `api_server.py` + `backend/solver.py` / `backend/math_utils.py`
exist to give a native client something to talk to, without touching how
app.py works today.

**Done:** registration/login/logout via bearer tokens (`ApiToken` in
`backend/db.py`), `/me` (tier + daily usage), and `/solve` for the
**Algebra** topic — ported from app.py's AI Tutor so both surfaces run
the literal same solving code (see `backend/solver.py`'s `StepRecorder`
pattern: the solving logic doesn't know or care whether its output ends
up as a Streamlit widget or a JSON response).

**Not done yet:** every other AI Tutor topic (Sequences, Financial Maths,
Calculus, Functions & Graphs, Analytical Geometry, Trigonometry,
Statistics, Probability, Euclidean Geometry), OCR, PDF past-paper
extraction, Practice Questions, Learner Profile, Formula Sheet, and
subscriptions/payments in-app. `/solve` returns a `501` with a clear
message for any topic other than Algebra rather than a wrong or empty
answer — extend `SUPPORTED_SOLVE_TOPICS` in `api_server.py` as each
topic gets the same extraction treatment as Algebra.

The actual React Native project (Expo) lives alongside this repo once
scaffolded — it talks to `api_server.py` over plain HTTP(S), the same way
any REST client would.

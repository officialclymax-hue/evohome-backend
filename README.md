# EvoHome Backend - Deploy Instructions (step-by-step, beginner friendly)

This README explains, like "step-by-step for a 5 year old", how to get the backend live on Render and connect it to your Bolt frontend.

## Overview
1. Files in this repo:
   - `app/main.py` — the FastAPI server (APIs, admin auth, seed)
   - `admin_static/` — tiny admin dashboard (open at `/admin/`)
   - `requirements.txt`, `Dockerfile`
   - `.env.example` — environment variables to set in Render
2. We use Docker on Render. Render watches GitHub repo and redeploys on push.

---

## Step 1 — Update GitHub repository (copy/paste files)
1. Open your repository on GitHub (the screenshot shows `officialclymax-hue/evohome-backend`).
2. For each file above (list in README), click **Add file → Create new file**.
3. Paste the exact contents I provided for each file into the appropriate path:
   - Create folder `app/` then file `app/main.py` and paste the code.
   - Create folder `admin_static/` and add `index.html`, `app.js`, `styles.css`.
   - Add `requirements.txt` in the repo root.
   - Add `Dockerfile` in the root (replace existing if present).
   - Add `.env.example` in the root.
   - Add `README.md` in the root.
4. Commit each file (enter commit message "Add backend files").

**Tip**: GitHub's web UI shows "Create new file" (top right). For each file create the folder in the filename (e.g., `admin_static/index.html`).

---

## Step 2 — Add seed data (your JSON files)
1. In your repo create a folder called `seed_data/`.
2. For each JSON dataset (e.g., `homepage.json`, `services.json`, `blogs.json`, etc.) create a new file inside `seed_data/`. You already have full JSON content (from previous ChatGPT output). Paste each JSON into its file and commit.
   - Example: create `seed_data/homepage.json` and paste the `homepage.json` content.

3. Commit all seed JSON files.

---

## Step 3 — Render environment variables (this is very important)
1. Go to your Render dashboard → select your service (the backend).
2. Click **Environment** (or **Settings → Environment**).
3. Add variables from `.env.example` with real values:
   - `DATABASE_URL` — **use Supabase Postgres connection string** (from Supabase project → Database → Connection info). It looks like: `postgresql://postgres:password@db.<project>.supabase.co:5432/postgres`
   - `SUPABASE_URL` and `SUPABASE_KEY` — from Supabase → Settings → API. Use service role key or anon key (service role recommended for uploads but secure).
   - `SUPABASE_BUCKET` — e.g. `public`
   - `ADMIN_EMAIL` = owner email
   - `ADMIN_PASSWORD` = a strong password you choose
   - `JWT_SECRET` = long random secret
   - `FRONTEND_ORIGINS` = `https://evohome-improvements-gm0u.bolt.host`
   - SMTP variables (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`) if you want lead emails to actually send; otherwise the backend will log leads (safe fallback).
4. Save environment variables.

---

## Step 4 — Render: Docker & Deploy
You already used Docker before. Render will detect `Dockerfile` and deploy with Docker.
1. In Render service, confirm **Environment** uses Docker.
2. Click **Manual Deploy → Deploy latest commit** (or push a new commit to GitHub to trigger automatic deploy).
3. Watch the deploy logs. If successful, you’ll see the container start and a public URL like: `https://evohome-backend.onrender.com`.

---

## Step 5 — Seed the content (one time)
1. Open the admin dashboard in your browser:
   - `https://<your-backend-host>/admin/`
   - Login with `ADMIN_EMAIL` and `ADMIN_PASSWORD` you set in Render env.
2. Run the seed:
   - Click `Run /seed` button (it calls the backend `/seed` endpoint).
   - Or open `https://<your-backend-host>/seed` to run it (you must be admin and include token header if required).
   - The backend will read files in `seed_data/*.json` and store them in the DB.

---

## Step 6 — Test endpoints
- Open `https://<your-backend-host>/docs` for API docs and to test endpoints.
- Check `GET /content/homepage`, `GET /content/header` etc.
- Test lead form (POST `/lead`) — this will save lead to DB and attempt to send email if SMTP configured.

---

## Step 7 — Connect Bolt frontend (super easy)
1. In your Bolt frontend code, replace hard-coded content fetches (if any) to call the backend endpoints:
   - Example: to get homepage content call `GET https://<your-backend-host>/content/homepage`
   - For services listing `GET https://<your-backend-host>/services`
   - For gallery list `GET https://<your-backend-host>/gallery`
2. If the Bolt project is static and you cannot edit code:
   - Option A: Rebuild the site in Bolt to fetch JSON from the backend (recommended).
   - Option B: Use server-side rewriting or CMS features in Bolt (Bolt support) to call the endpoints.

---

## Notes & Limitations (important)
- Rate limiter is in-memory. If you scale to multiple containers or multiple processes, use Redis or a central rate-limiter.
- Supabase upload uses the Storage REST attempt — if upload fails, the backend stores image in `/uploads` and serves it under `/static/uploads/`. On Render this is ephemeral; for production use Supabase storage with an admin/service role key.
- Admin login uses the `ADMIN_EMAIL` and `ADMIN_PASSWORD` environment variables. For stronger security use hashed passwords and user records.

---

## If something goes wrong
- Check Render logs (Service → Logs). Errors will show why a deploy fails.
- If pydantic or other packages cause wheel/build errors, ensure Docker image matches Python version in `requirements.txt` (the Dockerfile uses Python 3.11 which matches tested wheels).

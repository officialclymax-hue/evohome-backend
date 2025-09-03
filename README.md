
# EvoHome Backend (FastAPI + Supabase + Render)

Production-ready FastAPI backend for the EvoHome Smart Lead-Gen Website.

## Features
- FastAPI with auto Swagger docs at `/docs`
- CORS enabled for your Bolt frontend domain
- Pydantic validation, structured logging
- Rate limiting for POST endpoints (SlowAPI)
- Supabase for PostgreSQL (via supabase-py) and Storage for images
- Endpoints:
  - `GET /health`
  - `POST /lead`
  - `POST /admin/login` (basic demo auth)
  - CRUD with image upload:
    - `/gallery`
    - `/services`
    - `/blogs`
  - `POST /chatbot` (dummy reply)

## Quick Start (Render Free Tier)

### 1) Prepare Supabase
1. Create a new Supabase project.
2. In Table Editor, create these tables with default uuid PK `id`, and `created_at` & `updated_at` (timestamptz) columns:

**leads**
- id uuid pk default `gen_random_uuid()`
- name text
- email text
- phone text
- message text
- created_at timestamptz default `now()`

**gallery / services**
- id uuid pk default `gen_random_uuid()`
- title text
- description text
- image_url text
- created_at timestamptz default `now()`
- updated_at timestamptz nullable

**blogs**
- same as gallery + `content text`

3. In Storage create (or let the app auto-create) a bucket named `evohome-media` and set it to Public.
4. Go to Project Settings → API and copy:
   - Project URL → `SUPABASE_URL`
   - service_role key → `SUPABASE_SERVICE_KEY` (server only)
   - Optionally anon key → `SUPABASE_ANON_KEY`

Note: The backend uses the service key on the server to perform CRUD securely.

### 2) Deploy to Render
1. Push this folder to a GitHub repo or upload as a Render Web Service.
2. On Render, create a Web Service:
   - Runtime: Python 3.11
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
   - Environment: Add variables from `.env.example` (do not commit real secrets).

### 3) CORS
Ensure `FRONTEND_ORIGIN` equals your Bolt site: `https://evohome-improvements-gm0u.bolt.host`

### 4) Connect Frontend
On your Bolt frontend, call the API using your Render URL.

Example JavaScript (lead submission):

```javascript
const API_BASE = 'https://YOUR-RENDER-SERVICE.onrender.com';

async function submitLead(form) {
  const res = await fetch(`${API_BASE}/lead`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: form.name.value,
      email: form.email.value,
      phone: form.phone.value,
      message: form.message.value,
    })
  });
  if (!res.ok) throw new Error('Lead failed');
  return res.json();
}
```

### 5) Image Upload (CRUD)
Send multipart/form-data for POST `/gallery` etc:

```bash
curl -X POST "$API_BASE/gallery"   -F "title=Kitchen Refurb"   -F "description=Before & after"   -F "image=@/path/to/photo.jpg"
```

Update with optional new image:

```bash
curl -X PUT "$API_BASE/gallery/<id>"   -F "title=Updated Title"   -F "image=@/path/to/new.jpg"
```

### 6) Admin Login
Add `ADMIN_EMAIL` and `ADMIN_PASSWORD` in Render env. Then:

```bash
curl -X POST "$API_BASE/admin/login"   -H "Content-Type: application/json"   -d '{"email":"you@example.com","password":"supersecret"}'
```

Response includes a simple token you can store if you want to gate admin UI.

### 7) Rate Limiting
- Default: `10/minute` on all POST endpoints.
- Configure via `RATE_LIMIT_POST` env var (e.g., `5/minute`).

### 8) Health & Docs
- Health: `GET /health`
- Swagger UI: `GET /docs`

## Project Structure
```
.
├── app
│   └── main.py
├── requirements.txt
├── .env.example
└── README.md
```

## Notes
- This backend talks to Supabase tables via the supabase-py client — no direct SQL setup required.
- Storage uploads go to the configured public bucket and return a public URL that is saved to the DB.
- If you need role-based or authenticated CRUD, extend `/admin/login` to verify tokens on write ops.


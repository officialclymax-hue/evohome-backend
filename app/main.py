# app/main.py
# EvoHome FastAPI backend (fixed & complete)
# - Admin login with JWT at /auth/login (no collision with /admin static)
# - CRUD for content singletons + services/blogs/gallery collections
# - Seed from seed_data/*.json
# - Image upload (Supabase if configured; otherwise /uploads)
# - Lead email (SMTP if configured; else logs)
# - CORS + simple rate limiting + /docs

import os
import json
import pathlib
import smtplib
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import requests
from fastapi import (
    FastAPI, HTTPException, Depends, UploadFile, File, Request, Body, Response
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, JSON as SAJSON, DateTime
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ---------------------------
# Environment / config
# ---------------------------
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS") or os.getenv("FRONTEND_ORIGIN") \
    or "https://evohome-improvements-gm0u.bolt.host,http://localhost:8000"
ALLOWED_ORIGINS = [s.strip() for s in FRONTEND_ORIGINS.split(",") if s.strip()]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
# Accept either SUPABASE_KEY or SUPABASE_SERVICE_KEY (service key recommended)
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or ""
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", os.getenv("SUPABASE_STORAGE_BUCKET", "public"))

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
JWT_SECRET = os.getenv("JWT_SECRET", "replace-me")
JWT_ALGO = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "240"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", os.getenv("SMTP_FROM", "no-reply@evohomeimprovements.co.uk"))
LEADS_TO_EMAIL = os.getenv("LEADS_TO_EMAIL", os.getenv("LEAD_NOTIFY_EMAIL", "office@evohomeimprovements.co.uk"))

UPLOADS_DIR = pathlib.Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# rate limit (simple, in-memory)
RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))
_RATE_BUCKET: Dict[str, List[datetime]] = {}

# ---------------------------
# App + CORS
# ---------------------------
app = FastAPI(title="EvoHome Backend", version="1.0.0", docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve admin static files (UI lives here)
if pathlib.Path("admin_static").exists():
    app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")

# Serve local uploads
if UPLOADS_DIR.exists():
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ---------------------------
# Database
# ---------------------------
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Content(Base):
    __tablename__ = "content"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(200), unique=True, index=True)
    data = Column(SAJSON, nullable=False)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(100))
    postcode = Column(String(50))
    service = Column(String(200))
    message = Column(Text)
    source = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

class ServiceItem(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(200), unique=True, index=True)
    name = Column(String(300))
    category = Column(String(200))
    data = Column(SAJSON)

class BlogPost(Base):
    __tablename__ = "blogs"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(200), unique=True, index=True)
    title = Column(String(400))
    data = Column(SAJSON)

class GalleryItem(Base):
    __tablename__ = "gallery"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(400))
    category = Column(String(200))
    data = Column(SAJSON)

Base.metadata.create_all(bind=engine)

# ---------------------------
# Schemas
# ---------------------------
class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class LeadSchema(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = ""
    postcode: Optional[str] = ""
    service: Optional[str] = ""
    message: Optional[str] = ""
    source: Optional[str] = "website"

# ---------------------------
# Helpers
# ---------------------------
def db_sess():
    return SessionLocal()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)

def verify_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        return None

def require_admin(request: Request):
    auth = request.headers.get("authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload or payload.get("sub") != "admin":
        raise HTTPException(status_code=401, detail="Invalid token")
    return True

def rate_limiter(request: Request):
    if request.method in {"POST", "PUT", "DELETE"}:
        ip = request.client.host if request.client else "0.0.0.0"
        key = f"{ip}:{request.url.path}"
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=RATE_LIMIT_WINDOW_SEC)
        old = [t for t in _RATE_BUCKET.get(key, []) if t > window_start]
        if len(old) >= RATE_LIMIT_MAX:
            raise HTTPException(429, "Too many requests; slow down.")
        old.append(now)
        _RATE_BUCKET[key] = old

@app.middleware("http")
async def _rl_middleware(request: Request, call_next):
    try:
        rate_limiter(request)
    except HTTPException as e:
        return Response(status_code=e.status_code, content=e.detail)
    return await call_next(request)

# ---------------------------
# Auth
# ---------------------------
@app.post("/auth/login")
def auth_login(body: AdminLogin = Body(...)):
    if body.email.lower() != ADMIN_EMAIL.lower() or body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": "admin", "email": ADMIN_EMAIL})
    return {"access_token": token, "token_type": "bearer"}

# ---------------------------
# Health
# ---------------------------
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# ---------------------------
# Singletons (Page content)
#   Admin UI expects:
#   - GET /content/{key} -> raw JSON document
#   - POST /content/{key} (admin) -> body = raw JSON to store
# ---------------------------
@app.get("/content/{key}")
def get_content(key: str):
    db = db_sess()
    row = db.query(Content).filter(Content.key == key).first()
    db.close()
    if not row:
        raise HTTPException(404, "Not found")
    return row.data

@app.post("/content/{key}", dependencies=[Depends(require_admin)])
def save_content(key: str, body: Dict[str, Any] = Body(...)):
    db = db_sess()
    row = db.query(Content).filter(Content.key == key).first()
    if row:
        row.data = body
    else:
        row = Content(key=key, data=body)
        db.add(row)
    db.commit()
    db.close()
    return {"ok": True}

# ---------------------------
# Collections: Services
#   Admin UI:
#   - GET /services -> array
#   - POST /services (admin) -> either array (replace all) OR single object (upsert by slug)
# ---------------------------
@app.get("/services")
def list_services():
    db = db_sess()
    items = db.query(ServiceItem).all()
    out = [i.data or {"slug": i.slug, "name": i.name, "category": i.category} for i in items]
    db.close()
    return out

@app.post("/services", dependencies=[Depends(require_admin)])
def save_services(body: Any = Body(...)):
    db = db_sess()
    # If array: replace all
    if isinstance(body, list):
        db.query(ServiceItem).delete()
        for o in body:
            slug = (o or {}).get("slug")
            if not slug:
                continue
            db.add(ServiceItem(slug=slug, name=o.get("name",""), category=o.get("category",""), data=o))
        db.commit()
        db.close()
        return {"ok": True, "count": len(body)}
    # If object: upsert by slug
    if isinstance(body, dict):
        slug = body.get("slug")
        if not slug:
            raise HTTPException(400, "slug required")
        row = db.query(ServiceItem).filter(ServiceItem.slug == slug).first()
        if row:
            row.name = body.get("name", row.name)
            row.category = body.get("category", row.category)
            row.data = body
        else:
            db.add(ServiceItem(slug=slug, name=body.get("name",""), category=body.get("category",""), data=body))
        db.commit()
        db.close()
        return {"ok": True}
    raise HTTPException(400, "Invalid body")

# ---------------------------
# Collections: Blogs
# ---------------------------
@app.get("/blogs")
def list_blogs():
    db = db_sess()
    items = db.query(BlogPost).all()
    out = [i.data or {"slug": i.slug, "title": i.title} for i in items]
    db.close()
    return out

@app.post("/blogs", dependencies=[Depends(require_admin)])
def save_blogs(body: Any = Body(...)):
    db = db_sess()
    if isinstance(body, list):
        db.query(BlogPost).delete()
        for o in body:
            slug = (o or {}).get("slug")
            if not slug:
                continue
            db.add(BlogPost(slug=slug, title=o.get("title",""), data=o))
        db.commit(); db.close()
        return {"ok": True, "count": len(body)}
    if isinstance(body, dict):
        slug = body.get("slug")
        if not slug:
            raise HTTPException(400, "slug required")
        row = db.query(BlogPost).filter(BlogPost.slug == slug).first()
        if row:
            row.title = body.get("title", row.title)
            row.data = body
        else:
            db.add(BlogPost(slug=slug, title=body.get("title",""), data=body))
        db.commit(); db.close()
        return {"ok": True}
    raise HTTPException(400, "Invalid body")

# ---------------------------
# Collections: Gallery
# ---------------------------
@app.get("/gallery")
def list_gallery():
    db = db_sess()
    items = db.query(GalleryItem).all()
    out = [i.data or {"title": i.title, "category": i.category} for i in items]
    db.close()
    return out

@app.post("/gallery", dependencies=[Depends(require_admin)])
def save_gallery(body: Any = Body(...)):
    db = db_sess()
    if isinstance(body, list):
        db.query(GalleryItem).delete()
        for o in body:
            db.add(GalleryItem(title=o.get("title",""), category=o.get("category",""), data=o))
        db.commit(); db.close()
        return {"ok": True, "count": len(body)}
    if isinstance(body, dict):
        db.add(GalleryItem(title=body.get("title",""), category=body.get("category",""), data=body))
        db.commit(); db.close()
        return {"ok": True}
    raise HTTPException(400, "Invalid body")

# ---------------------------
# Seed from /seed_data
# ---------------------------
@app.post("/seed", dependencies=[Depends(require_admin)])
def seed():
    base = pathlib.Path("seed_data")
    if not base.exists():
        raise HTTPException(404, "seed_data folder not found")

    db = db_sess()

    # singletons: every json file except these arrays
    array_names = {"services", "blogs", "gallery"}
    for f in base.glob("*.json"):
        name = f.stem
        data = json.loads(f.read_text(encoding="utf-8"))
        if name in array_names:
            continue
        row = db.query(Content).filter(Content.key == name).first()
        if row: row.data = data
        else: db.add(Content(key=name, data=data))

    # arrays
    def load_array(name: str):
        path = base / f"{name}.json"
        if not path.exists():
            return
        arr = json.loads(path.read_text(encoding="utf-8"))
        if name == "services":
            db.query(ServiceItem).delete()
            for o in arr:
                db.add(ServiceItem(slug=o.get("slug",""), name=o.get("name",""), category=o.get("category",""), data=o))
        elif name == "blogs":
            db.query(BlogPost).delete()
            for o in arr:
                db.add(BlogPost(slug=o.get("slug",""), title=o.get("title",""), data=o))
        elif name == "gallery":
            db.query(GalleryItem).delete()
            for o in arr:
                db.add(GalleryItem(title=o.get("title",""), category=o.get("category",""), data=o))

    load_array("services")
    load_array("blogs")
    load_array("gallery")

    db.commit()
    db.close()
    return {"ok": True}

# ---------------------------
# Uploads
# ---------------------------
@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()
    ext = pathlib.Path(file.filename).suffix or ".bin"
    key = f"{uuid.uuid4().hex}{ext}"
    ctype = file.content_type or "application/octet-stream"

    # Try Supabase (if configured)
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_BUCKET:
        try:
            url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_BUCKET}/{key}"
            headers = {
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": ctype,
                "x-upsert": "true"
            }
            r = requests.post(url, headers=headers, data=content, timeout=30)
            if r.status_code in (200, 201):
                # Public URL (bucket must be public)
                public_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{SUPABASE_BUCKET}/{key}"
                return {"url": public_url, "provider": "supabase"}
        except Exception as e:
            print("[Supabase upload failed]", e)

    # Fallback: local
    dest = UPLOADS_DIR / key
    dest.write_bytes(content)
    return {"url": f"/uploads/{key}", "provider": "local"}

# ---------------------------
# Leads
# ---------------------------
@app.post("/lead")
def create_lead(lead: LeadSchema):
    db = db_sess()
    db.add(Lead(
        name=lead.name,
        email=str(lead.email),
        phone=lead.phone or "",
        postcode=lead.postcode or "",
        service=lead.service or "",
        message=lead.message or "",
        source=lead.source or "website"
    ))
    db.commit()
    db.close()

    # email (best-effort)
    try:
        if SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM and LEADS_TO_EMAIL:
            from email.message import EmailMessage
            msg = EmailMessage()
            msg["From"] = EMAIL_FROM
            msg["To"] = LEADS_TO_EMAIL
            msg["Subject"] = f"New Lead: {lead.name} ({lead.service or 'General'})"
            body = f"""
            Name: {lead.name}
            Email: {lead.email}
            Phone: {lead.phone}
            Postcode: {lead.postcode}
            Service: {lead.service}
            Source: {lead.source}
            Message:
            {lead.message}
            """
            msg.set_content(body)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        else:
            print("[Lead email] SMTP not fully configured; lead saved only.")
    except Exception as e:
        print("[Lead email failed]", e)

    return {"ok": True, "message": "Lead received."}

# ---------------------------
# Root
# ---------------------------
@app.get("/")
def root():
    return {"detail": "EvoHome backend running", "docs": "/docs", "admin": "/admin"}

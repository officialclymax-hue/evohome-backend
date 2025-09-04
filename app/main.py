# app/main.py
# EvoHome FastAPI backend (single-file main server)
# - CRUD for services, blogs, gallery
# - Generic content drawers (homepage, header, footer, seo, request-quote, chatbot, forms, coverage)
# - /lead endpoint that saves lead and attempts to send email to office@evohomeimprovements.co.uk
# - /admin/login returns JWT (basic)
# - image upload: tries Supabase storage if SUPABASE_* env vars are set; otherwise saves to /uploads
# - simple in-memory rate limiter for POST endpoints (not distributed; okay for demo)
# - docs available at /docs

import os
import time
import json
import pathlib
import smtplib
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from fastapi import (
    FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
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
import requests

# ---------------------------
# Environment / config
# ---------------------------
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "https://evohome-improvements-gm0u.bolt.host")
# allow multiple origins comma separated
ALLOWED_ORIGINS = [s.strip() for s in FRONTEND_ORIGINS.split(",") if s.strip()]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "public")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")  # replace in Render settings!
JWT_SECRET = os.getenv("JWT_SECRET", "replace-me-with-a-strong-secret")
JWT_ALGO = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "240"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@evohomeimprovements.co.uk")
LEADS_TO_EMAIL = os.getenv("LEADS_TO_EMAIL", "office@evohomeimprovements.co.uk")

UPLOADS_DIR = pathlib.Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------
# App + CORS
# ---------------------------
app = FastAPI(title="EvoHome Backend (FastAPI)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve admin static files under /admin/
app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")

# Serve uploaded files (fallback) under /static/uploads/
app.mount("/static/uploads", StaticFiles(directory="uploads"), name="uploads")

# ---------------------------
# Database (SQLAlchemy)
# ---------------------------
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Generic content table (keyed by name)
class Content(Base):
    __tablename__ = "content"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(200), unique=True, index=True)  # e.g. "homepage", "header", "seo"
    data = Column(SAJSON, nullable=False)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(100))
    message = Column(Text)
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
# Pydantic Schemas
# ---------------------------
class LeadSchema(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = ""
    message: Optional[str] = ""

class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class ContentSchema(BaseModel):
    key: str
    data: dict

class ServiceSchema(BaseModel):
    slug: str
    name: str
    category: Optional[str] = ""
    data: Optional[dict] = {}

class BlogSchema(BaseModel):
    slug: str
    title: str
    data: Optional[dict] = {}

class GallerySchema(BaseModel):
    title: str
    category: Optional[str] = ""
    data: Optional[dict] = {}

# ---------------------------
# Simple in-memory rate limiter
# ---------------------------
# NOTE (5 y/o): This is a tiny lock that counts requests from each IP.
# It's stored in memory and resets itself after a minute/hour. Works for demo.
RATE_STORE: Dict[str, List[float]] = {}
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))  # POSTs per minute per IP
def rate_limit(request: Request):
    if request.method != "POST":
        return
    ip = request.client.host
    now = time.time()
    window = 60
    lst = RATE_STORE.get(ip, [])
    # keep only last window
    lst = [ts for ts in lst if now - ts < window]
    if len(lst) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Too many requests - slow down")
    lst.append(now)
    RATE_STORE[ip] = lst

# ---------------------------
# Auth helpers (very basic)
# ---------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return payload
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

# ---------------------------
# Supabase upload helper (fallback available)
# ---------------------------
def upload_to_supabase(file_bytes: bytes, remote_path: str, filename: str) -> Optional[str]:
    """
    Try to upload using Supabase Storage REST API.
    Returns public URL on success or None on failure.
    """
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        # Upload endpoint: POST {SUPABASE_URL}/storage/v1/object/{bucket}
        # We'll send multipart form file with name= file contents
        url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{remote_path}"
        # Some Supabase instances expect POST to /object/{bucket} path without file name; if that fails
        # we fallback to a generic upload API using bucket only:
        basic_upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}"
        headers = {"Authorization": f"Bearer {SUPABASE_KEY}"}
        files = {"file": (filename, file_bytes)}
        # Try direct bucket path first
        resp = requests.post(basic_upload_url, headers=headers, files=files, timeout=30)
        if resp.ok:
            public = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{remote_path or filename}"
            return public
        # fallback: try the remote_path url variant
        resp = requests.post(url, headers=headers, files=files, timeout=30)
        if resp.ok:
            public = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{remote_path or filename}"
            return public
        app.logger and app.logger.error("Supabase upload failed: %s" % resp.text)
    except Exception as e:
        print("Supabase upload error:", e)
    return None

# ---------------------------
# Utility DB helpers
# ---------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# Basic endpoints + admin
# ---------------------------

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/admin/login")
def admin_login(payload: AdminLogin):
    # Very small, simple check against env var username+password.
    if payload.email.lower() != ADMIN_EMAIL.lower() or payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": "admin", "email": ADMIN_EMAIL})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/lead", status_code=201)
def create_lead(lead: LeadSchema, request: Request):
    rate_limit(request)
    db = next(get_db())
    db_lead = Lead(name=lead.name, email=lead.email, phone=lead.phone, message=lead.message)
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)

    # Try to send email via SMTP if configured
    subject = f"New lead from {lead.name}"
    body = f"Name: {lead.name}\nEmail: {lead.email}\nPhone: {lead.phone}\n\nMessage:\n{lead.message}\n\nReceived: {db_lead.created_at}"
    try:
        if SMTP_HOST and SMTP_USER and SMTP_PASS:
            s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            msg = f"From: {EMAIL_FROM}\r\nTo: {LEADS_TO_EMAIL}\r\nSubject: {subject}\r\n\r\n{body}"
            s.sendmail(EMAIL_FROM, [LEADS_TO_EMAIL], msg.encode("utf8"))
            s.quit()
        else:
            # fallback: log (Render logs visible to you)
            print("EMAIL (not sent - SMTP not configured):", subject, body)
    except Exception as e:
        print("Error sending lead email:", e, traceback.format_exc())

    return {"detail": "Lead received", "id": db_lead.id}

@app.post("/chatbot")
def chatbot(payload: dict, request: Request):
    rate_limit(request)
    # very simple - echo + dummy reply
    msg = payload.get("message", "")
    return {"reply": f"EvoBot: I received your message '{msg}'. An agent will follow up soon."}

# ---------------------------
# Generic content CRUD (homepage, header, footer, seo, request-quote, chatbot, forms, coverage)
# ---------------------------

@app.get("/content/{key}")
def get_content(key: str):
    db = next(get_db())
    item = db.query(Content).filter(Content.key == key).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item.data

@app.post("/content/{key}", summary="Create or replace a content object (admin only)")
def set_content(key: str, payload: dict, request: Request):
    require_admin(request)
    db = next(get_db())
    item = db.query(Content).filter(Content.key == key).first()
    if item:
        item.data = payload
    else:
        item = Content(key=key, data=payload)
        db.add(item)
    db.commit()
    return {"detail": "saved", "key": key}

@app.delete("/content/{key}")
def delete_content(key: str, request: Request):
    require_admin(request)
    db = next(get_db())
    item = db.query(Content).filter(Content.key == key).first()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(item)
    db.commit()
    return {"detail": "deleted"}

# ---------------------------
# Services CRUD
# ---------------------------
@app.post("/services", summary="Create a service (admin)")
def create_service(payload: ServiceSchema, request: Request):
    require_admin(request)
    db = next(get_db())
    s = ServiceItem(slug=payload.slug, name=payload.name, category=payload.category, data=payload.data or {})
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "slug": s.slug}

@app.get("/services", summary="List services")
def list_services():
    db = next(get_db())
    rows = db.query(ServiceItem).all()
    return [{"id": r.id, "slug": r.slug, "name": r.name, "category": r.category, "data": r.data} for r in rows]

@app.get("/services/{slug}")
def get_service(slug: str):
    db = next(get_db())
    r = db.query(ServiceItem).filter(ServiceItem.slug == slug).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": r.id, "slug": r.slug, "name": r.name, "category": r.category, "data": r.data}

@app.put("/services/{slug}", summary="Update service (admin)")
def update_service(slug: str, payload: ServiceSchema, request: Request):
    require_admin(request)
    db = next(get_db())
    r = db.query(ServiceItem).filter(ServiceItem.slug == slug).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    r.slug = payload.slug
    r.name = payload.name
    r.category = payload.category
    r.data = payload.data or r.data
    db.commit()
    return {"detail": "updated"}

@app.delete("/services/{slug}", summary="Delete service (admin)")
def delete_service(slug: str, request: Request):
    require_admin(request)
    db = next(get_db())
    r = db.query(ServiceItem).filter(ServiceItem.slug == slug).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"detail": "deleted"}

# ---------------------------
# Blogs CRUD
# ---------------------------
@app.post("/blogs", summary="Create blog (admin)")
def create_blog(payload: BlogSchema, request: Request):
    require_admin(request)
    db = next(get_db())
    b = BlogPost(slug=payload.slug, title=payload.title, data=payload.data or {})
    db.add(b)
    db.commit()
    db.refresh(b)
    return {"id": b.id, "slug": b.slug}

@app.get("/blogs")
def list_blogs():
    db = next(get_db())
    rows = db.query(BlogPost).all()
    return [{"id": r.id, "slug": r.slug, "title": r.title, "data": r.data} for r in rows]

@app.get("/blogs/{slug}")
def get_blog(slug: str):
    db = next(get_db())
    r = db.query(BlogPost).filter(BlogPost.slug == slug).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": r.id, "slug": r.slug, "title": r.title, "data": r.data}

@app.put("/blogs/{slug}")
def update_blog(slug: str, payload: BlogSchema, request: Request):
    require_admin(request)
    db = next(get_db())
    r = db.query(BlogPost).filter(BlogPost.slug == slug).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    r.slug = payload.slug
    r.title = payload.title
    r.data = payload.data or r.data
    db.commit()
    return {"detail": "updated"}

@app.delete("/blogs/{slug}")
def delete_blog(slug: str, request: Request):
    require_admin(request)
    db = next(get_db())
    r = db.query(BlogPost).filter(BlogPost.slug == slug).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"detail": "deleted"}

# ---------------------------
# Gallery CRUD
# ---------------------------
@app.post("/gallery", summary="Create gallery item (admin)")
def create_gallery(payload: GallerySchema, request: Request):
    require_admin(request)
    db = next(get_db())
    g = GalleryItem(title=payload.title, category=payload.category, data=payload.data or {})
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id}

@app.get("/gallery")
def list_gallery():
    db = next(get_db())
    rows = db.query(GalleryItem).all()
    return [{"id": r.id, "title": r.title, "category": r.category, "data": r.data} for r in rows]

@app.get("/gallery/{item_id}")
def get_gallery_item(item_id: int):
    db = next(get_db())
    r = db.query(GalleryItem).filter(GalleryItem.id == item_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": r.id, "title": r.title, "category": r.category, "data": r.data}

@app.put("/gallery/{item_id}")
def update_gallery(item_id: int, payload: GallerySchema, request: Request):
    require_admin(request)
    db = next(get_db())
    r = db.query(GalleryItem).filter(GalleryItem.id == item_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    r.title = payload.title
    r.category = payload.category
    r.data = payload.data or r.data
    db.commit()
    return {"detail": "updated"}

@app.delete("/gallery/{item_id}")
def delete_gallery(item_id: int, request: Request):
    require_admin(request)
    db = next(get_db())
    r = db.query(GalleryItem).filter(GalleryItem.id == item_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(r)
    db.commit()
    return {"detail": "deleted"}

# ---------------------------
# Image upload endpoint
# ---------------------------
@app.post("/upload-image")
def upload_image(file: UploadFile = File(...), request: Request = None):
    # Admin and non-admin both can upload if desired; for safety require admin
    require_admin(request)
    content = file.file.read()
    filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
    # Try Supabase first
    remote_path = filename
    public_url = None
    try:
        public_url = upload_to_supabase(content, remote_path, filename)
    except Exception as e:
        print("Supabase upload exception:", e)
    # fallback: save locally to /uploads
    if not public_url:
        path = UPLOADS_DIR / filename
        with open(path, "wb") as f:
            f.write(content)
        public_url = f"/static/uploads/{filename}"
    return {"url": public_url, "filename": filename}

# ---------------------------
# Seed endpoint - loads JSON files from seed_data/
# ---------------------------
@app.post("/seed")
def seed_all(request: Request):
    require_admin(request)
    seed_dir = pathlib.Path("seed_data")
    if not seed_dir.exists():
        return {"detail": "No seed_data directory found. Upload JSON files into seed_data/"}
    db = next(get_db())
    files = list(seed_dir.glob("*.json"))
    inserted = []
    for f in files:
        key = f.stem  # e.g. homepage.json -> homepage
        try:
            data = json.loads(f.read_text(encoding="utf8"))
        except Exception as e:
            print("Seed read error", f, e)
            continue
        existing = db.query(Content).filter(Content.key == key).first()
        if existing:
            existing.data = data
        else:
            new = Content(key=key, data=data)
            db.add(new)
        db.commit()
        inserted.append(key)
    return {"inserted": inserted}

# ---------------------------
# Simple root
# ---------------------------
@app.get("/")
def root():
    return {"detail": "EvoHome backend running. Open /docs for API docs or /admin for dashboard."}

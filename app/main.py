# app/main.py
# EvoHome FastAPI backend (simple JSON CMS – no drag/drop)
# - Auth (JWT) + minimal in-memory rate limit
# - Content singletons (header, homepage, about, contact, footer, coverage,
#   seo, forms, request-quote, chatbot, floating-buttons, etc.)
# - Collections: services, blogs, gallery (bulk replace or upsert one)
# - Lead form -> DB + SMTP email
# - Image upload (Supabase Storage if configured, else /uploads)
# - Seed from seed_data/ (singletons + arrays)
# - Admin static at /admin
# - Swagger at /docs

import os
import json
import time
import pathlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.sqlite import JSON as SAJSON  # works for sqlite; postgres will store as text
from sqlalchemy.orm import sessionmaker, declarative_base
import smtplib
import requests

# -------------------------
# Env
# -------------------------
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "https://evohome-improvements-gm0u.bolt.host").split(",")
DATABASE_URL      = os.getenv("DATABASE_URL", "sqlite:///./local.db")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY      = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET   = os.getenv("SUPABASE_BUCKET", "public")

ADMIN_EMAIL       = os.getenv("ADMIN_EMAIL", "office@evohomeimprovements.co.uk")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "Improvements247!")
JWT_SECRET        = os.getenv("JWT_SECRET", "replace-this-with-a-long-random-string")
JWT_ALGO          = "HS256"
JWT_EXPIRE_MIN    = int(os.getenv("JWT_EXPIRE_MINUTES", "360"))

SMTP_HOST         = os.getenv("SMTP_HOST", "")
SMTP_PORT         = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER         = os.getenv("SMTP_USER", "")
SMTP_PASS         = os.getenv("SMTP_PASS", "")
EMAIL_FROM        = os.getenv("EMAIL_FROM", "no-reply@evohomeimprovements.co.uk")
LEADS_TO_EMAIL    = os.getenv("LEADS_TO_EMAIL", "office@evohomeimprovements.co.uk")

UPLOADS_DIR = pathlib.Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------
# App + CORS + static
# -------------------------
app = FastAPI(title="EvoHome Backend", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in FRONTEND_ORIGINS if o.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")
app.mount("/static/uploads", StaticFiles(directory="uploads"), name="uploads")

# -------------------------
# DB
# -------------------------
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Content(Base):
    __tablename__ = "content"
    id = Column(Integer, primary_key=True)
    key = Column(String(200), unique=True, index=True)
    data = Column(SAJSON, nullable=False)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(100))
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class ServiceItem(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True)
    slug = Column(String(200), unique=True, index=True)
    name = Column(String(300))
    category = Column(String(200))
    data = Column(SAJSON)

class BlogPost(Base):
    __tablename__ = "blogs"
    id = Column(Integer, primary_key=True)
    slug = Column(String(200), unique=True, index=True)
    title = Column(String(400))
    data = Column(SAJSON)

class GalleryItem(Base):
    __tablename__ = "gallery"
    id = Column(Integer, primary_key=True)
    title = Column(String(400))
    category = Column(String(200))
    data = Column(SAJSON)

Base.metadata.create_all(bind=engine)

# -------------------------
# Schemas
# -------------------------
class AdminLogin(BaseModel):
    email: EmailStr
    password: str

class LeadSchema(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = ""
    message: Optional[str] = ""

# -------------------------
# Auth helpers
# -------------------------
def create_access_token(payload: dict, minutes: int = JWT_EXPIRE_MIN) -> str:
    to_encode = payload.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=minutes)
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError:
        return None

def require_admin(request: Request):
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth.split(" ", 1)[1].strip()
    payload = decode_token(token)
    if not payload or payload.get("sub") != "admin":
        raise HTTPException(401, "Invalid token")
    return True

# -------------------------
# Rate limit (simple in-memory)
# -------------------------
RATE_BUCKET: Dict[str, List[float]] = {}
POST_LIMIT_COUNT = int(os.getenv("RATE_LIMIT_COUNT", "30"))
POST_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))

def rate_limited(ip: str):
    now = time.time()
    bucket = RATE_BUCKET.setdefault(ip, [])
    # drop old
    while bucket and now - bucket[0] > POST_LIMIT_WINDOW:
        bucket.pop(0)
    if len(bucket) >= POST_LIMIT_COUNT:
        return True
    bucket.append(now)
    return False

# -------------------------
# Auth
# -------------------------
@app.post("/auth/login")
def auth_login(body: AdminLogin):
    if body.email.lower() != ADMIN_EMAIL.lower() or body.password != ADMIN_PASSWORD:
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": "admin", "email": ADMIN_EMAIL})
    return {"access_token": token, "token_type": "bearer"}

# -------------------------
# Health
# -------------------------
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# -------------------------
# Content (singletons)
# -------------------------
@app.get("/content/{key}")
def get_content(key: str):
    db = SessionLocal()
    try:
        obj = db.query(Content).filter(Content.key == key).first()
        if not obj:
            raise HTTPException(404, "Not found")
        return obj.data
    finally:
        db.close()

@app.post("/content/{key}")
def save_content(key: str, request: Request):
    require_admin(request)
    body = None
    try:
        body = json.loads((await request.body()).decode("utf-8")) if hasattr(request, "body") else None
    except Exception:
        body = None
    if body is None:
        try:
            body = request.json()
        except Exception:
            pass
    if body is None or isinstance(body, (str, int, float, list)) is False and not isinstance(body, dict):
        # Try normal FastAPI way
        body = (request.state._json if hasattr(request.state, "_json") else None) or {}
    db = SessionLocal()
    try:
        obj = db.query(Content).filter(Content.key == key).first()
        if obj:
            obj.data = body
        else:
            obj = Content(key=key, data=body)
            db.add(obj)
        db.commit()
        return {"ok": True, "key": key}
    finally:
        db.close()

# -------------------------
# Collections helpers
# -------------------------
def _replace_collection(db, model, items: List[dict], unique: str):
    # wipe + insert clean
    db.query(model).delete()
    for o in items:
        if not isinstance(o, dict):
            continue
        fields = {}
        if unique == "slug":
            fields["slug"] = o.get("slug") or o.get("id") or f"{int(time.time()*1000)}"
        if model is GalleryItem:
            fields["title"] = o.get("title") or ""
            fields["category"] = o.get("category") or ""
            fields["data"] = o
        elif model is BlogPost:
            fields["title"] = o.get("title") or ""
            fields["data"] = o
        elif model is ServiceItem:
            fields["name"] = o.get("name") or ""
            fields["category"] = o.get("category") or ""
            fields["data"] = o
        db.add(model(**fields))
    db.commit()

def _upsert_one(db, model, unique_field: str, payload: dict):
    if model is ServiceItem:
        keyval = payload.get("slug")
    elif model is BlogPost:
        keyval = payload.get("slug")
    else:
        keyval = payload.get("title")
    if not keyval:
        raise HTTPException(400, f"Missing unique field for {model.__tablename__}")
    obj = db.query(model).filter(getattr(model, unique_field)==keyval).first()
    if obj:
        # update
        if model is ServiceItem:
            obj.name = payload.get("name", obj.name)
            obj.category = payload.get("category", obj.category)
            obj.data = payload
        elif model is BlogPost:
            obj.title = payload.get("title", obj.title)
            obj.data = payload
        else:
            obj.title = payload.get("title", obj.title)
            obj.category = payload.get("category", obj.category)
            obj.data = payload
    else:
        if model is ServiceItem:
            obj = ServiceItem(slug=keyval, name=payload.get("name",""), category=payload.get("category",""), data=payload)
        elif model is BlogPost:
            obj = BlogPost(slug=keyval, title=payload.get("title",""), data=payload)
        else:
            obj = GalleryItem(title=payload.get("title",""), category=payload.get("category",""), data=payload)
        db.add(obj)
    db.commit()

# -------------------------
# Services
# -------------------------
@app.get("/services")
def list_services():
    db = SessionLocal()
    try:
        rows = db.query(ServiceItem).all()
        return [r.data for r in rows]
    finally:
        db.close()

@app.get("/services/{slug}")
def get_service(slug: str):
    db = SessionLocal()
    try:
        r = db.query(ServiceItem).filter(ServiceItem.slug==slug).first()
        if not r: raise HTTPException(404, "Not found")
        return r.data
    finally:
        db.close()

@app.post("/services")
async def save_services(request: Request):
    require_admin(request)
    body = await request.json()
    db = SessionLocal()
    try:
        if isinstance(body, list):
            _replace_collection(db, ServiceItem, body, "slug")
            return {"ok": True, "replaced": len(body)}
        elif isinstance(body, dict):
            _upsert_one(db, ServiceItem, "slug", body)
            return {"ok": True, "upserted": body.get("slug")}
        else:
            raise HTTPException(400, "Send a list (replace all) or an object (upsert one).")
    finally:
        db.close()

# -------------------------
# Blogs
# -------------------------
@app.get("/blogs")
def list_blogs():
    db = SessionLocal()
    try:
        rows = db.query(BlogPost).all()
        return [r.data for r in rows]
    finally:
        db.close()

@app.get("/blogs/{slug}")
def get_blog(slug: str):
    db = SessionLocal()
    try:
        r = db.query(BlogPost).filter(BlogPost.slug==slug).first()
        if not r: raise HTTPException(404, "Not found")
        return r.data
    finally:
        db.close()

@app.post("/blogs")
async def save_blogs(request: Request):
    require_admin(request)
    body = await request.json()
    db = SessionLocal()
    try:
        if isinstance(body, list):
            _replace_collection(db, BlogPost, body, "slug")
            return {"ok": True, "replaced": len(body)}
        elif isinstance(body, dict):
            _upsert_one(db, BlogPost, "slug", body)
            return {"ok": True, "upserted": body.get("slug")}
        else:
            raise HTTPException(400, "Send a list (replace all) or an object (upsert one).")
    finally:
        db.close()

# -------------------------
# Gallery
# -------------------------
@app.get("/gallery")
def list_gallery():
    db = SessionLocal()
    try:
        rows = db.query(GalleryItem).all()
        return [r.data for r in rows]
    finally:
        db.close()

@app.post("/gallery")
async def save_gallery(request: Request):
    require_admin(request)
    body = await request.json()
    db = SessionLocal()
    try:
        if isinstance(body, list):
            _replace_collection(db, GalleryItem, body, "title")
            return {"ok": True, "replaced": len(body)}
        elif isinstance(body, dict):
            _upsert_one(db, GalleryItem, "title", body)
            return {"ok": True, "upserted": body.get("title")}
        else:
            raise HTTPException(400, "Send a list (replace all) or an object (upsert one).")
    finally:
        db.close()

# -------------------------
# Upload
# -------------------------
@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...), request: Request = None):
    require_admin(request)
    data = await file.read()
    filename = f"{int(time.time())}_{file.filename}"
    # Supabase
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{filename}"
            r = requests.post(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": file.content_type or "application/octet-stream",
                    "x-upsert": "true"
                },
                timeout=30
            )
            if 200 <= r.status_code < 300:
                public = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"
                return {"url": public}
        except Exception:
            pass
    # Fallback local
    (UPLOADS_DIR / filename).write_bytes(data)
    return {"url": f"/static/uploads/{filename}"}

# -------------------------
# Lead
# -------------------------
@app.post("/lead")
async def create_lead(body: LeadSchema, request: Request):
    ip = request.client.host if request and request.client else "unknown"
    if rate_limited(ip):
        raise HTTPException(429, "Too many requests")
    db = SessionLocal()
    try:
        lead = Lead(name=body.name, email=str(body.email), phone=body.phone or "", message=body.message or "")
        db.add(lead); db.commit()
    finally:
        db.close()
    # Email (best-effort)
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            msg = f"From: {EMAIL_FROM}\r\nTo: {LEADS_TO_EMAIL}\r\nSubject: New Website Lead\r\n\r\n" \
                  f"Name: {body.name}\nEmail: {body.email}\nPhone: {body.phone}\nMessage:\n{body.message}\n"
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(EMAIL_FROM, [LEADS_TO_EMAIL], msg.encode("utf-8"))
        except Exception:
            # swallow email errors (lead still stored)
            pass
    return {"ok": True}

# -------------------------
# Seed + Debug
# -------------------------
def _read_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/debug/seed-files")
def debug_seed_files():
    root = pathlib.Path("seed_data")
    if not root.exists():
        return {"used_folder": False, "singletons": [], "arrays": [], "errors": ["seed_data folder not found"]}
    singletons = []
    arrays = []
    errors = []
    for f in root.glob("*.json"):
        try:
            data = _read_json(f)
            if isinstance(data, list):
                arrays.append({"name": f.stem, "count": len(data)})
            else:
                singletons.append(f.stem)
        except Exception as e:
            errors.append(f"{f.name}: {e}")
    return {"used_folder": True, "singletons": singletons, "arrays": arrays, "errors": errors}

@app.post("/seed")
async def seed(request: Request):
    require_admin(request)
    root = pathlib.Path("seed_data")
    report = {"used_folder": False, "bootstrapped": False, "singletons": [], "arrays": [], "errors": []}
    if not root.exists():
        return report
    report["used_folder"] = True
    db = SessionLocal()
    try:
        # singletons = any *.json with dict
        for f in root.glob("*.json"):
            try:
                data = _read_json(f)
                if isinstance(data, list):
                    continue
                key = f.stem
                obj = db.query(Content).filter(Content.key==key).first()
                if obj: obj.data = data
                else: db.add(Content(key=key, data=data))
                db.commit()
                report["singletons"].append(key)
            except Exception as e:
                report["errors"].append(f"{f.name}: {e}")

        # arrays we know: services/blogs/gallery
        def load_array(name, model, unique):
            p = root / f"{name}.json"
            if not p.exists(): return
            try:
                items = _read_json(p)
                if not isinstance(items, list):
                    raise Exception("Array file must be a JSON array")
                _replace_collection(db, model, items, unique)
                report["arrays"].append({"name": name, "count": len(items)})
            except Exception as e:
                report["errors"].append(f"{name}.json: {e}")

        load_array("services", ServiceItem, "slug")
        load_array("blogs", BlogPost, "slug")
        load_array("gallery", GalleryItem, "title")
    finally:
        db.close()
    return report

# -------------------------
# Root
# -------------------------
@app.get("/")
def root():
    return {"detail": "EvoHome backend running"}

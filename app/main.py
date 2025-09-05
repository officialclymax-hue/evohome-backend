# app/main.py — EvoHome Backend (pages + block builder + existing CMS)
import os, json, pathlib, smtplib, uuid, re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request, Body, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import create_engine, Column, Integer, String, Text, JSON as SAJSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# -------- Env
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS") or os.getenv("FRONTEND_ORIGIN") or "*"
ALLOWED_ORIGINS = [s.strip() for s in FRONTEND_ORIGINS.split(",") if s.strip()]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
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

UPLOADS_DIR = pathlib.Path("uploads"); UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW_SEC", "60"))
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "20"))
_RATE_BUCKET: Dict[str, List[datetime]] = {}

# -------- App
app = FastAPI(title="EvoHome Backend", version="1.1.0", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if pathlib.Path("admin_static").exists():
    app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")
if UPLOADS_DIR.exists():
    app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# -------- DB
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Content(Base):
    __tablename__ = "content"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(200), unique=True, index=True)
    data = Column(SAJSON, nullable=False)

class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200)); email = Column(String(200))
    phone = Column(String(100)); postcode = Column(String(50))
    service = Column(String(200)); message = Column(Text)
    source = Column(String(100)); created_at = Column(DateTime, default=datetime.utcnow)

class ServiceItem(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(200), unique=True, index=True)
    name = Column(String(300)); category = Column(String(200))
    data = Column(SAJSON)

class BlogPost(Base):
    __tablename__ = "blogs"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(200), unique=True, index=True)
    title = Column(String(400)); data = Column(SAJSON)

class GalleryItem(Base):
    __tablename__ = "gallery"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(400)); category = Column(String(200))
    data = Column(SAJSON)

Base.metadata.create_all(bind=engine)

# -------- Schemas
class AdminLogin(BaseModel): email: EmailStr; password: str
class LeadSchema(BaseModel):
    name: str; email: EmailStr
    phone: Optional[str] = ""; postcode: Optional[str] = ""; service: Optional[str] = ""
    message: Optional[str] = ""; source: Optional[str] = "website"

# -------- Helpers
def db_sess(): return SessionLocal()
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy(); expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire}); return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)
def verify_token(token: str):
    try: return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError: return None
def _is_admin(request: Request):
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer "):
        payload = verify_token(auth.split(" ",1)[1])
        if payload and payload.get("sub")=="admin": return True
    token = request.query_params.get("token")
    if token:
        payload = verify_token(token)
        if payload and payload.get("sub")=="admin": return True
    return False
def require_admin(request: Request):
    if not _is_admin(request): raise HTTPException(401, "Invalid or missing admin token")
    return True

def rate_limiter(request: Request):
    if request.method in {"POST","PUT","DELETE"}:
        now=datetime.utcnow()
        ip = request.client.host if request.client else "0.0.0.0"; key=f"{ip}:{request.url.path}"
        win=now-timedelta(seconds=RATE_LIMIT_WINDOW_SEC)
        kept=[t for t in _RATE_BUCKET.get(key,[]) if t>win]
        if len(kept)>=RATE_LIMIT_MAX: raise HTTPException(429, "Too many requests; slow down.")
        kept.append(now); _RATE_BUCKET[key]=kept

@app.middleware("http")
async def _rl_mw(request: Request, call_next):
    try: rate_limiter(request)
    except HTTPException as e: return Response(status_code=e.status_code, content=e.detail)
    return await call_next(request)

def slugify(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or uuid.uuid4().hex[:8]

# -------- Auth
@app.post("/auth/login")
def auth_login(body: AdminLogin = Body(...)):
    if body.email.lower()!=ADMIN_EMAIL.lower() or body.password!=ADMIN_PASSWORD:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": create_access_token({"sub":"admin","email":ADMIN_EMAIL}), "token_type":"bearer"}

# -------- Health
@app.get("/health")
def health(): return {"status":"ok","time":datetime.utcnow().isoformat()}

# -------- Singletons
@app.get("/content/{key}")
def get_content(key: str):
    db=db_sess(); row=db.query(Content).filter(Content.key==key).first(); db.close()
    if not row: raise HTTPException(404, "Not found")
    return row.data

@app.post("/content/{key}", dependencies=[Depends(require_admin)])
def save_content(key: str, body: Dict[str,Any]=Body(...)):
    db=db_sess(); row=db.query(Content).filter(Content.key==key).first()
    if row: row.data=body
    else: db.add(Content(key=key, data=body))
    db.commit(); db.close(); return {"ok":True}

# -------- Collections (services/blogs/gallery)
@app.get("/services")
def list_services():
    db=db_sess(); items=db.query(ServiceItem).all()
    out=[i.data or {"slug":i.slug,"name":i.name,"category":i.category} for i in items]
    db.close(); return out

@app.post("/services", dependencies=[Depends(require_admin)])
def save_services(body: Any = Body(...)):
    db=db_sess()
    if isinstance(body, list):
        db.query(ServiceItem).delete()
        for o in body:
            o=o or{}
            slug=o.get("slug") or slugify(o.get("name",""))
            db.add(ServiceItem(slug=slug,name=o.get("name",""),category=o.get("category",""),data=o))
        db.commit(); db.close(); return {"ok":True,"count":len(body)}
    if isinstance(body, dict):
        slug=body.get("slug") or slugify(body.get("name",""))
        row=db.query(ServiceItem).filter(ServiceItem.slug==slug).first()
        if row:
            row.name=body.get("name",row.name); row.category=body.get("category",row.category); row.data=body
        else:
            db.add(ServiceItem(slug=slug,name=body.get("name",""),category=body.get("category",""),data=body))
        db.commit(); db.close(); return {"ok":True}
    raise HTTPException(400,"Invalid body")

@app.get("/blogs")
def list_blogs():
    db=db_sess(); items=db.query(BlogPost).all()
    out=[i.data or {"slug":i.slug,"title":i.title} for i in items]
    db.close(); return out

@app.post("/blogs", dependencies=[Depends(require_admin)])
def save_blogs(body: Any = Body(...)):
    db=db_sess()
    if isinstance(body, list):
        db.query(BlogPost).delete()
        for o in body:
            o=o or{}
            slug=o.get("slug") or slugify(o.get("title",""))
            db.add(BlogPost(slug=slug,title=o.get("title",""),data=o))
        db.commit(); db.close(); return {"ok":True,"count":len(body)}
    if isinstance(body, dict):
        slug=body.get("slug") or slugify(body.get("title",""))
        row=db.query(BlogPost).filter(BlogPost.slug==slug).first()
        if row: row.title=body.get("title",row.title); row.data=body
        else: db.add(BlogPost(slug=slug,title=body.get("title",""),data=body))
        db.commit(); db.close(); return {"ok":True}
    raise HTTPException(400,"Invalid body")

@app.get("/gallery")
def list_gallery():
    db=db_sess(); items=db.query(GalleryItem).all()
    out=[i.data or {"title":i.title,"category":i.category} for i in items]
    db.close(); return out

@app.post("/gallery", dependencies=[Depends(require_admin)])
def save_gallery(body: Any = Body(...)):
    db=db_sess()
    if isinstance(body, list):
        db.query(GalleryItem).delete()
        for o in body:
            db.add(GalleryItem(title=o.get("title",""),category=o.get("category",""),data=o))
        db.commit(); db.close(); return {"ok":True,"count":len(body)}
    if isinstance(body, dict):
        db.add(GalleryItem(title=body.get("title",""),category=body.get("category",""),data=body))
        db.commit(); db.close(); return {"ok":True}
    raise HTTPException(400,"Invalid body")

# -------- Page Builder (blocks)
BLOCK_DEFS = {
    # simple content blocks
    "hero": {
        "label":"Hero",
        "fields":{
            "title":{"type":"text","label":"Title"},
            "subtitle":{"type":"textarea","label":"Subtitle"},
            "ctaLabel":{"type":"text","label":"Button label"},
            "ctaHref":{"type":"text","label":"Button link"},
            "images":{"type":"images","label":"Images"}
        }
    },
    "text": {
        "label":"Text",
        "fields":{"html":{"type":"textarea","label":"HTML / text"}}
    },
    "image": {
        "label":"Image",
        "fields":{"src":{"type":"image","label":"Image URL"},"alt":{"type":"text","label":"Alt"}}
    },
    "columns": {
        "label":"Columns (2)",
        "fields":{
            "left":{"type":"textarea","label":"Left HTML"},
            "right":{"type":"textarea","label":"Right HTML"}
        }
    },
    "cta": {
        "label":"CTA Banner",
        "fields":{
            "text":{"type":"text","label":"Text"},
            "button":{"type":"text","label":"Button label"},
            "href":{"type":"text","label":"Link"},
            "images":{"type":"images","label":"Background images"}
        }
    },
    "serviceCards": {
        "label":"Service Cards",
        "fields":{
            "heading":{"type":"text","label":"Heading"},
            "items":{"type":"list","label":"Cards (from /services)", "item":"serviceRef"}
        }
    },
    "features": {
        "label":"Features list",
        "fields":{
            "heading":{"type":"text","label":"Heading"},
            "items":{"type":"list","label":"Items (text)", "item":"text"}
        }
    },
    "faq": {
        "label":"FAQ",
        "fields":{
            "items":{"type":"list","label":"Q&As","item":"qa"} # {q,a}
        }
    },
    "testimonials":{
        "label":"Testimonials",
        "fields":{
            "items":{"type":"list","item":"testimonial"} # {quote,author,role,image?}
        }
    },
    "galleryStrip":{
        "label":"Gallery Strip",
        "fields":{"count":{"type":"number","label":"How many?"},"category":{"type":"text","label":"Category filter"}}
    },
    "spacer": {"label":"Spacer","fields":{"size":{"type":"number","label":"Height (px)"}}},
    "divider":{"label":"Divider","fields":{}},
    "map":{"label":"Map (iframe)","fields":{"src":{"type":"text","label":"Embed URL"}}},
    "video":{"label":"Video (iframe)","fields":{"src":{"type":"text","label":"Embed URL"}}},
    "form":{"label":"Lead Form","fields":{"heading":{"type":"text","label":"Heading"}}}
}

def _page_key(slug:str)->str: return f"page:{slug}"

@app.get("/blocks/definitions")
def blocks_definitions(): return BLOCK_DEFS

@app.get("/pages")
def list_pages():
    db=db_sess(); keys=[r.key for r in db.query(Content.key).all()]; db.close()
    pages=[k.split("page:",1)[1] for k in keys if k.startswith("page:")]
    return {"pages": pages}

@app.get("/pages/{slug}")
def get_page(slug: str):
    db=db_sess(); row=db.query(Content).filter(Content.key==_page_key(slug)).first(); db.close()
    if not row: return {"slug": slug, "blocks": []}
    data = row.data or {}
    return {"slug": slug, "blocks": data.get("blocks", [])}

@app.post("/pages/{slug}", dependencies=[Depends(require_admin)])
def save_page(slug: str, body: Dict[str,Any]=Body(...)):
    if "blocks" not in body or not isinstance(body["blocks"], list):
        raise HTTPException(400, "Body must have 'blocks': []")
    db=db_sess()
    row=db.query(Content).filter(Content.key==_page_key(slug)).first()
    if row: row.data = {"blocks": body["blocks"]}
    else: db.add(Content(key=_page_key(slug), data={"blocks": body["blocks"]}))
    db.commit(); db.close(); return {"ok": True}

# -------- Upload
@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()
    ext = pathlib.Path(file.filename).suffix or ".bin"; key = f"{uuid.uuid4().hex}{ext}"
    ctype = file.content_type or "application/octet-stream"
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_BUCKET:
        try:
            url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{SUPABASE_BUCKET}/{key}"
            headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": ctype, "x-upsert": "true"}
            r = requests.post(url, headers=headers, data=content, timeout=30)
            if r.status_code in (200,201):
                public = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{SUPABASE_BUCKET}/{key}"
                return {"url": public, "provider":"supabase"}
        except Exception as e:
            print("[Supabase upload failed]", e)
    dest = UPLOADS_DIR / key; dest.write_bytes(content)
    return {"url": f"/uploads/{key}", "provider":"local"}

# -------- Lead
@app.post("/lead")
def create_lead(lead: LeadSchema):
    db=db_sess()
    db.add(Lead(name=lead.name,email=str(lead.email),phone=lead.phone or "",postcode=lead.postcode or "",
                service=lead.service or "",message=lead.message or "",source=lead.source or "website"))
    db.commit(); db.close()
    try:
        if SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM and LEADS_TO_EMAIL:
            from email.message import EmailMessage
            msg=EmailMessage(); msg["From"]=EMAIL_FROM; msg["To"]=LEADS_TO_EMAIL
            msg["Subject"]=f"New Lead: {lead.name} ({lead.service or 'General'})"
            msg.set_content(f"Name: {lead.name}\nEmail: {lead.email}\nPhone: {lead.phone}\nPostcode: {lead.postcode}\nService: {lead.service}\nSource: {lead.source}\n\n{lead.message}")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s: s.starttls(); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
        else: print("[Lead email] SMTP not configured; lead saved only.")
    except Exception as e: print("[Lead email failed]", e)
    return {"ok": True, "message": "Lead received."}

# -------- Root
@app.get("/")
def root(): return {"detail":"EvoHome backend running","docs":"/docs","admin":"/admin"}

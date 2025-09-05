# app/main.py
# EvoHome FastAPI backend (seed with report + debug + owner-friendly CMS support)

import os, json, pathlib, smtplib, uuid
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

# ---------- Env ----------
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS") or os.getenv("FRONTEND_ORIGIN") \
    or "https://evohome-improvements-gm0u.bolt.host,http://localhost:8000"
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

# ---------- App ----------
app = FastAPI(title="EvoHome Backend", version="1.0.2", docs_url="/docs", redoc_url="/redoc")
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

# ---------- DB ----------
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

# ---------- Schemas ----------
class AdminLogin(BaseModel): email: EmailStr; password: str
class LeadSchema(BaseModel):
    name: str; email: EmailStr
    phone: Optional[str] = ""; postcode: Optional[str] = ""; service: Optional[str] = ""
    message: Optional[str] = ""; source: Optional[str] = "website"

# ---------- Helpers ----------
def db_sess(): return SessionLocal()
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy(); expire = datetime.utcnow() + (expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire}); return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGO)
def verify_token(token: str):
    try: return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except JWTError: return None
def require_admin(request: Request):
    auth = request.headers.get("authorization") or ""
    if not auth.startswith("Bearer "): raise HTTPException(401, "Missing token")
    payload = verify_token(auth.split(" ",1)[1])
    if not payload or payload.get("sub")!="admin": raise HTTPException(401, "Invalid token")
    return True
def rate_limiter(request: Request):
    if request.method in {"POST","PUT","DELETE"}:
        ip = request.client.host if request.client else "0.0.0.0"; key=f"{ip}:{request.url.path}"
        now=datetime.utcnow(); win=now-timedelta(seconds=RATE_LIMIT_WINDOW_SEC)
        kept=[t for t in _RATE_BUCKET.get(key,[]) if t>win]
        if len(kept)>=RATE_LIMIT_MAX: raise HTTPException(429, "Too many requests; slow down.")
        kept.append(now); _RATE_BUCKET[key]=kept

@app.middleware("http")
async def _rl_mw(request: Request, call_next):
    try: rate_limiter(request)
    except HTTPException as e: return Response(status_code=e.status_code, content=e.detail)
    return await call_next(request)

# ---------- Auth ----------
@app.post("/auth/login")
def auth_login(body: AdminLogin = Body(...)):
    if body.email.lower()!=ADMIN_EMAIL.lower() or body.password!=ADMIN_PASSWORD:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": create_access_token({"sub":"admin","email":ADMIN_EMAIL}), "token_type":"bearer"}

# ---------- Health ----------
@app.get("/health")
def health(): return {"status":"ok","time":datetime.utcnow().isoformat()}

# ---------- Singletons ----------
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

# ---------- Services ----------
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
            o = o or {}
            slug = o.get("slug")
            if not slug:
                continue
            db.add(ServiceItem(slug=slug, name=o.get("name",""), category=o.get("category",""), data=o))
        db.commit(); db.close(); return {"ok":True,"count":len(body)}
    if isinstance(body, dict):
        slug = body.get("slug")
        if not slug: raise HTTPException(400,"slug required")
        row=db.query(ServiceItem).filter(ServiceItem.slug==slug).first()
        if row:
            row.name = body.get("name", row.name)
            row.category = body.get("category", row.category)
            row.data = body
        else:
            db.add(ServiceItem(slug=slug, name=body.get("name",""), category=body.get("category",""), data=body))
        db.commit(); db.close(); return {"ok":True}
    raise HTTPException(400,"Invalid body")

# ---------- Blogs ----------
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
            o = o or {}
            slug = o.get("slug")
            if not slug:
                continue
            db.add(BlogPost(slug=slug, title=o.get("title",""), data=o))
        db.commit(); db.close(); return {"ok":True,"count":len(body)}
    if isinstance(body, dict):
        slug = body.get("slug")
        if not slug: raise HTTPException(400,"slug required")
        row=db.query(BlogPost).filter(BlogPost.slug==slug).first()
        if row:
            row.title = body.get("title", row.title)
            row.data = body
        else:
            db.add(BlogPost(slug=slug, title=body.get("title",""), data=body))
        db.commit(); db.close(); return {"ok":True}
    raise HTTPException(400,"Invalid body")

# ---------- Gallery ----------
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
            db.add(GalleryItem(title=o.get("title",""), category=o.get("category",""), data=o))
        db.commit(); db.close(); return {"ok":True,"count":len(body)}
    if isinstance(body, dict):
        db.add(GalleryItem(title=body.get("title",""), category=body.get("category",""), data=body))
        db.commit(); db.close(); return {"ok":True}
    raise HTTPException(400,"Invalid body")

# ---------- Seed (reads seed_data/ if present; else bootstraps defaults) ----------
def _defaults():
    return {
      "singletons": {
        "homepage": {
          "seo": {"title":"EvoHome Improvements","description":"Home improvements made simple.","keywords":"home, solar, windows"},
          "hero":{"title":"WELCOME TO EVOHOME IMPROVEMENTS","subtitle":"Vetted specialists. Expert advice. Complete protection.","primaryCta":{"label":"Request Free Quote","href":"/request-quote"},"images":[]}
        },
        "header": {
          "logo":{"images":[],"alt":"EvoHome"},"brand":"EvoHome Improvements",
          "navigation":[{"label":"Home","href":"/"},{"label":"Services","href":"/services"},{"label":"Request Quote","href":"/request-quote","isPrimary":True}],
          "phone":"0333 004 0195","ctaButtons":[{"label":"Request Free Quote","href":"/request-quote"},{"label":"Call","href":"tel:03330040195"}]
        },
        "footer": {
          "company":{"name":"EvoHome Improvements Ltd","companyNumber":"14881322","images":[]},
          "contact":{"phone":"0333 004 0195","email":"office@evohomeimprovements.co.uk","images":[]},
          "coverageAreas":{"primary":["Hampshire","Surrey","Sussex","Dorset","Wiltshire"],"images":[]},
          "copyright":"© {{year}} EvoHome Improvements Ltd. All rights reserved."
        }
      },
      "arrays": {
        "services":[
          {"slug":"solar-power","name":"Solar Power","category":"renewable","images":["https://images.pexels.com/photos/9875441/pexels-photo-9875441.jpeg"]},
          {"slug":"windows-doors","name":"Windows & Doors","category":"improvements","images":["https://images.pexels.com/photos/1571460/pexels-photo-1571460.jpeg"]}
        ],
        "blogs":[
          {"slug":"complete-guide-solar-power-uk-homes-2025","title":"The Complete Guide to Solar Power for UK Homes in 2025","image":"https://images.pexels.com/photos/9875441/pexels-photo-9875441.jpeg","excerpt":"Savings, grants and how it works.","date":"2025-01-15","author":"EvoHome Team","category":"Solar Power","images":["https://images.pexels.com/photos/9875441/pexels-photo-9875441.jpeg"]}
        ],
        "gallery":[
          {"slug":"g-solar-1","title":"Residential Solar Installation","category":"Solar Power","src":"https://images.pexels.com/photos/9875441/pexels-photo-9875441.jpeg","images":["https://images.pexels.com/photos/9875441/pexels-photo-9875441.jpeg"],"alt":"Solar on a roof"}
        ]
      }
    }

@app.post("/seed", dependencies=[Depends(require_admin)])
def seed():
    report = {"used_folder": False, "bootstrapped": False, "singletons": [], "arrays": [], "errors": []}
    base = pathlib.Path("seed_data")
    db = db_sess()
    try:
        if base.exists():
            report["used_folder"] = True
            array_names = {"services","blogs","gallery"}
            for f in base.glob("*.json"):
                name = f.stem
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception as e:
                    report["errors"].append(f"{f.name}: {e}")
                    continue
                if name in array_names:
                    continue
                row = db.query(Content).filter(Content.key==name).first()
                if row: row.data = data
                else: db.add(Content(key=name, data=data))
                report["singletons"].append(name)

            def load_array(name, model):
                p = base / f"{name}.json"
                if not p.exists(): return
                try: arr = json.loads(p.read_text(encoding="utf-8"))
                except Exception as e:
                    report["errors"].append(f"{p.name}: {e}"); return
                db.query(model).delete()
                if name=="services":
                    for o in arr:
                        db.add(ServiceItem(slug=o.get("slug",""),name=o.get("name",""),category=o.get("category",""),data=o))
                elif name=="blogs":
                    for o in arr:
                        db.add(BlogPost(slug=o.get("slug",""),title=o.get("title",""),data=o))
                elif name=="gallery":
                    for o in arr:
                        db.add(GalleryItem(title=o.get("title",""),category=o.get("category",""),data=o))
                report["arrays"].append({"name": name, "count": len(arr)})

            load_array("services", ServiceItem)
            load_array("blogs", BlogPost)
            load_array("gallery", GalleryItem)
        else:
            defs = _defaults(); report["bootstrapped"]=True
            for k,v in defs["singletons"].items():
                row = db.query(Content).filter(Content.key==k).first()
                if row: row.data = v
                else: db.add(Content(key=k, data=v))
                report["singletons"].append(k)
            db.query(ServiceItem).delete()
            for o in defs["arrays"]["services"]:
                db.add(ServiceItem(slug=o["slug"], name=o["name"], category=o.get("category",""), data=o))
            db.query(BlogPost).delete()
            for o in defs["arrays"]["blogs"]:
                db.add(BlogPost(slug=o["slug"], title=o["title"], data=o))
            db.query(GalleryItem).delete()
            for o in defs["arrays"]["gallery"]:
                db.add(GalleryItem(title=o["title"], category=o.get("category",""), data=o))
            report["arrays"] = [{"name":"services","count":len(defs['arrays']['services'])},
                                {"name":"blogs","count":len(defs['arrays']['blogs'])},
                                {"name":"gallery","count":len(defs['arrays']['gallery'])}]
        db.commit()
    except Exception as e:
        db.rollback(); report["errors"].append(str(e))
    finally:
        db.close()
    return {"ok": len(report["errors"])==0, "report": report}

# ---------- Debug ----------
@app.get("/debug/seed-files", dependencies=[Depends(require_admin)])
def debug_seed_files():
    base = pathlib.Path("seed_data")
    if not base.exists(): return {"exists": False, "files": []}
    files = [{"name": f.name, "size": f.stat().st_size} for f in base.glob("*.json")]
    return {"exists": True, "files": files}

@app.get("/debug/seed-validate", dependencies=[Depends(require_admin)])
def debug_seed_validate():
    base = pathlib.Path("seed_data")
    if not base.exists(): return {"exists": False, "results": []}
    results=[]
    for f in base.glob("*.json"):
        try: json.loads(f.read_text(encoding="utf-8")); results.append({"name": f.name, "valid": True})
        except Exception as e: results.append({"name": f.name, "valid": False, "error": str(e)})
    return {"exists": True, "results": results}

# ---------- Upload ----------
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

# ---------- Lead ----------
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

# ---------- Root ----------
@app.get("/")
def root(): return {"detail":"EvoHome backend running","docs":"/docs","admin":"/admin"}

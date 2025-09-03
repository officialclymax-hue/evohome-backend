import os
import logging
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, constr
from dotenv import load_dotenv

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles

from supabase import create_client, Client

# load env
load_dotenv()

# logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("evohome")

# env vars
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "evohome-media")

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://evohome-improvements-gm0u.bolt.host")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALG = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "120"))

RATE_LIMIT_POST = os.getenv("RATE_LIMIT_POST", "10/minute")
LEAD_NOTIFY_EMAIL = os.getenv("LEAD_NOTIFY_EMAIL", "office@evohomeimprovements.co.uk")

# SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@evohomeimprovements.co.uk")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

# Supabase client
SUPABASE_KEY = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.warning("Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY on Render.")

# app
app = FastAPI(title="EvoHome Backend", version="1.1.0", docs_url="/docs", redoc_url="/redoc")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[])

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except RateLimitExceeded:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
        )

app.state.limiter = limiter

# Security
bearer = HTTPBearer()

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        sub = payload.get("sub")
        if not sub or sub.lower() != ADMIN_EMAIL.lower():
            raise HTTPException(status_code=401, detail="Unauthorized admin")
        return sub
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Schemas
class LeadIn(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    email: EmailStr
    phone: constr(strip_whitespace=True, min_length=5, max_length=30)
    message: constr(strip_whitespace=True, min_length=1, max_length=2000)

class LeadOut(BaseModel):
    id: str
    created_at: Optional[str] = None

class AdminLoginIn(BaseModel):
    email: EmailStr
    password: constr(min_length=6, max_length=200)

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str

class ItemBase(BaseModel):
    title: constr(strip_whitespace=True, min_length=1, max_length=200)
    description: Optional[constr(strip_whitespace=True, max_length=2000)] = None

class BlogBase(ItemBase):
    content: Optional[constr(strip_whitespace=True, max_length=20000)] = None

class ItemOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# helpers
def create_token(subject: str) -> TokenOut:
    now = datetime.utcnow()
    exp = now + timedelta(minutes=JWT_EXPIRES_MINUTES)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return TokenOut(access_token=token, expires_at=exp.isoformat() + "Z")

def require_supabase():
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase is not configured")
    return supabase

def upload_to_storage(file: UploadFile, folder: str) -> str:
    client = require_supabase()
    ext = os.path.splitext(file.filename or "")[1].lower()
    key = f"{folder}/{uuid4().hex}{ext or '.bin'}"
    data = file.file.read()
    file.file.seek(0)
    try:
        client.storage.create_bucket(SUPABASE_STORAGE_BUCKET, public=True)
    except Exception:
        pass
    res = client.storage.from_(SUPABASE_STORAGE_BUCKET).upload(file=data, path=key, file_options={"contentType": file.content_type or "application/octet-stream"})
    public_url = client.storage.from_(SUPABASE_STORAGE_BUCKET).get_public_url(key)
    return public_url

def insert_row(table: str, payload: dict) -> dict:
    client = require_supabase()
    resp = client.table(table).insert(payload).execute()
    if resp.data is None or len(resp.data) == 0:
        raise HTTPException(status_code=500, detail=f"Failed to insert into {table}")
    return resp.data[0]

def update_row(table: str, item_id: str, payload: dict) -> dict:
    client = require_supabase()
    resp = client.table(table).update(payload).eq("id", item_id).execute()
    if resp.data is None or len(resp.data) == 0:
        raise HTTPException(status_code=404, detail=f"{table} item not found")
    return resp.data[0]

def delete_row(table: str, item_id: str) -> dict:
    client = require_supabase()
    resp = client.table(table).delete().eq("id", item_id).execute()
    if resp.data is None or len(resp.data) == 0:
        raise HTTPException(status_code=404, detail=f"{table} item not found")
    return resp.data[0]

def get_row(table: str, item_id: str) -> dict:
    client = require_supabase()
    resp = client.table(table).select("*").eq("id", item_id).single().execute()
    if resp.data is None:
        raise HTTPException(status_code=404, detail=f"{table} item not found")
    return resp.data

def list_rows(table: str, limit: int = 100) -> List[dict]:
    client = require_supabase()
    resp = client.table(table).select("*").order("created_at", desc=True).limit(limit).execute()
    return resp.data or []

def send_email(subject: str, body: str, to_emails: List[str]) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured. Skipping email.")
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = ", ".join(to_emails)
        msg.set_content(body)
        if SMTP_USE_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        logger.info("Email sent to %s", to_emails)
        return True
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return False

# routes
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}

@app.post("/lead", response_model=LeadOut)
@limiter.limit(RATE_LIMIT_POST)
def create_lead(payload: LeadIn, request: Request):
    logger.info("New lead from %s <%s>", payload.name, payload.email)
    row = insert_row("leads", {
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "message": payload.message,
    })
    # Send email to office
    subject = f"New EvoHome lead from {payload.name}"
    body = f"Name: {payload.name}\nEmail: {payload.email}\nPhone: {payload.phone}\n\nMessage:\n{payload.message}\n\nSaved at: {row.get('created_at')}"
    try:
        send_email(subject, body, [LEAD_NOTIFY_EMAIL])
    except Exception as e:
        logger.error("Error sending lead email: %s", e)
    return {"id": row.get("id"), "created_at": row.get("created_at")}

@app.post("/admin/login", response_model=TokenOut)
@limiter.limit(RATE_LIMIT_POST)
def admin_login(body: AdminLoginIn, request: Request):
    if body.email.lower() != ADMIN_EMAIL.lower() or body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_token(subject=body.email.lower())

# public reads
@app.get("/gallery", response_model=List[ItemOut])
def gallery_list(limit: int = 100):
    return list_rows("gallery", limit=limit)

@app.get("/gallery/{item_id}", response_model=ItemOut)
def gallery_get(item_id: str):
    return get_row("gallery", item_id)

# admin writes - gallery
@app.post("/gallery", response_model=ItemOut)
@limiter.limit(RATE_LIMIT_POST)
def gallery_create(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    image: UploadFile = File(...),
    admin: str = Depends(require_admin),
):
    image_url = upload_to_storage(image, folder="gallery")
    row = insert_row("gallery", {
        "title": title,
        "description": description,
        "image_url": image_url,
    })
    return row

@app.put("/gallery/{item_id}", response_model=ItemOut)
def gallery_update(
    item_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: str = Depends(require_admin),
):
    payload = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if image is not None:
        payload["image_url"] = upload_to_storage(image, folder="gallery")
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    return update_row("gallery", item_id, payload)

@app.delete("/gallery/{item_id}")
def gallery_delete(item_id: str, admin: str = Depends(require_admin)):
    delete_row("gallery", item_id)
    return {"status": "deleted"}

# services
@app.get("/services", response_model=List[ItemOut])
def services_list(limit: int = 100):
    return list_rows("services", limit=limit)

@app.get("/services/{item_id}", response_model=ItemOut)
def services_get(item_id: str):
    return get_row("services", item_id)

@app.post("/services", response_model=ItemOut)
@limiter.limit(RATE_LIMIT_POST)
def services_create(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: str = Depends(require_admin),
):
    image_url = upload_to_storage(image, folder="services") if image else None
    row = insert_row("services", {
        "title": title,
        "description": description,
        "image_url": image_url,
    })
    return row

@app.put("/services/{item_id}", response_model=ItemOut)
def services_update(
    item_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: str = Depends(require_admin),
):
    payload = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if image is not None:
        payload["image_url"] = upload_to_storage(image, folder="services")
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    return update_row("services", item_id, payload)

@app.delete("/services/{item_id}")
def services_delete(item_id: str, admin: str = Depends(require_admin)):
    delete_row("services", item_id)
    return {"status": "deleted"}

# blogs
@app.get("/blogs", response_model=List[ItemOut])
def blogs_list(limit: int = 100):
    return list_rows("blogs", limit=limit)

@app.get("/blogs/{item_id}", response_model=ItemOut)
def blogs_get(item_id: str):
    return get_row("blogs", item_id)

@app.post("/blogs", response_model=ItemOut)
@limiter.limit(RATE_LIMIT_POST)
def blogs_create(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: str = Depends(require_admin),
):
    image_url = upload_to_storage(image, folder="blogs") if image else None
    row = insert_row("blogs", {
        "title": title,
        "description": description,
        "content": content,
        "image_url": image_url,
    })
    return row

@app.put("/blogs/{item_id}", response_model=ItemOut)
def blogs_update(
    item_id: str,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    admin: str = Depends(require_admin),
):
    payload = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if content is not None:
        payload["content"] = content
    if image is not None:
        payload["image_url"] = upload_to_storage(image, folder="blogs")
    payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
    return update_row("blogs", item_id, payload)

@app.delete("/blogs/{item_id}")
def blogs_delete(item_id: str, admin: str = Depends(require_admin)):
    delete_row("blogs", item_id)
    return {"status": "deleted"}

# chatbot
class ChatIn(BaseModel):
    message: constr(strip_whitespace=True, min_length=1, max_length=4000)

class ChatOut(BaseModel):
    reply: str

@app.post("/chatbot", response_model=ChatOut)
@limiter.limit(RATE_LIMIT_POST)
def chatbot(body: ChatIn, request: Request):
    reply = f"Thanks for your message: '{body.message}'. Our team will follow up shortly."
    return {"reply": reply}

# mount admin static UI
app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")

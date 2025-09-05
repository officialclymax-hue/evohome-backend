# app/main.py
# EvoHome FastAPI backend
# - CRUD for services, blogs, gallery, content
# - Lead form email
# - Admin login with JWT
# - Image upload
# - Seed JSON
# - Ready for Render deployment

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
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "*")
ALLOWED_ORIGINS = [s.strip() for s in FRONTEND_ORIGINS.split(",") if s.strip()]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "public")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
JWT_SECRET = os.getenv("JWT_SECRET", "replace-me")
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
app = FastAPI(title="EvoHome Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve admin static files
app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")

# Serve uploads
app.mount("/static/uploads", StaticFiles(directory="uploads"), name="uploads")

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
# Schemas
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
# Auth helpers
# ---------------------------
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

# ---------------------------
# Admin login (fixed)
# ---------------------------
@app.post("/admin/login")
async def admin_login(request: Request):
    try:
        data = await request.json()
        email = data.get("email")
        password = data.get("password")
    except:
        email = request.form().get("email")
        password = request.form().get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Missing email or password")

    if email.lower() != ADMIN_EMAIL.lower() or password != ADMIN_PASSWORD:
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
# Other routes (lead, content, services, blogs, gallery, uploads, seed)
# ---------------------------
# keep all your CRUD + seed endpoints unchanged here...
# (copy them from your current file under here, no edits needed)

# ---------------------------
# Root
# ---------------------------
@app.get("/")
def root():
    return {"detail": "EvoHome backend running"}

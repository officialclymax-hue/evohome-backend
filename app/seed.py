# app/seed.py
# run this script from the container if you want (not needed for Render web)
import os, json, pathlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import Base, Content, DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

def seed_dir(dirname="seed_data"):
    p = pathlib.Path(dirname)
    if not p.exists():
        print("No seed_data directory")
        return
    db = SessionLocal()
    for f in p.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf8"))
        except Exception as e:
            print("Skipping", f.name, "error", e)
            continue
        key = f.stem
        existing = db.query(Content).filter(Content.key==key).first()
        if existing:
            existing.data = data
        else:
            db.add(Content(key=key, data=data))
        db.commit()
        print("Seeded", key)
    db.close()

if __name__ == "__main__":
    seed_dir()

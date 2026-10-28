import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()  # lê o .env da pasta de onde o uvicorn é iniciado

# shortcut: sqlite como fallback de dev, em produção defina DATABASE_URL (Postgres)
URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        yield db

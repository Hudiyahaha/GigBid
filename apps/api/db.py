"""Application database (Postgres in docker, SQLite locally). Every user-owned row carries user_id and every
query in apps/api filters by it (tenant scoping, E4)."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[2]


def _url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if not url or (url.startswith("postgresql") and os.getenv("GIGBID_LOCAL_SQLITE") == "1"):
        p = ROOT / "data" / "processed" / "gigbid.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{p.as_posix()}"
    return url


ENGINE = create_engine(_url(), pool_pre_ping=True, future=True,
                       connect_args={"check_same_thread": False} if _url().startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def now() -> float:
    return time.time()


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), default="")
    persona: Mapped[str] = mapped_column(String(64), default="")          # ai_ml | fullstack | data | own
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[float] = mapped_column(Float, default=now)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    hourly_floor: Mapped[float] = mapped_column(Float, default=40)
    min_project: Mapped[float] = mapped_column(Float, default=300)
    weekly_connects_budget: Mapped[int] = mapped_column(Integer, default=80)
    autonomy: Mapped[str] = mapped_column(String(32), default="suggest")    # suggest | auto_skip_low_fit
    marketplace_mode: Mapped[str] = mapped_column(String(32), default="gigsim")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)               # categories, min budget, exclude words
    strategy: Mapped[str] = mapped_column(String(32), default="evidence_first")


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(String(255))
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_run: Mapped[float] = mapped_column(Float, default=0)
    last_tick: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class OAuthToken(Base):
    """Marketplace credentials, encrypted at rest (Fernet). Never logged, never returned by the API."""
    __tablename__ = "oauth_tokens"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))                       # gigsim | upwork
    ciphertext: Mapped[str] = mapped_column(Text)
    updated: Mapped[float] = mapped_column(Float, default=now)


class InboxJob(Base):
    """One row per (user, job): what Scout queued and what the bid graph concluded."""
    __tablename__ = "inbox_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)       # dedup key
    title: Mapped[str] = mapped_column(String(512))
    job: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="queued")      # queued|analysing|skipped|watch|awaiting_approval|submitted|rejected|needs_attention|dead_letter|duplicate
    thread_id: Mapped[str] = mapped_column(String(128), default="")
    fit: Mapped[float] = mapped_column(Float, default=0)
    risk: Mapped[float] = mapped_column(Float, default=0)
    action: Mapped[str] = mapped_column(String(16), default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    connects_cost: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    duplicate_of: Mapped[str] = mapped_column(String(64), default="")
    created: Mapped[float] = mapped_column(Float, default=now)
    updated: Mapped[float] = mapped_column(Float, default=now)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)          # = trace id
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    graph: Mapped[str] = mapped_column(String(32))                          # bid | conversation
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    ref: Mapped[str] = mapped_column(String(128), default="")               # job_id or marketplace thread id
    status: Mapped[str] = mapped_column(String(32), default="running")
    started: Mapped[float] = mapped_column(Float, default=now)
    finished: Mapped[float] = mapped_column(Float, default=0)
    latency_s: Mapped[float] = mapped_column(Float, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd: Mapped[float] = mapped_column(Float, default=0)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    events: Mapped[list] = mapped_column(JSON, default=list)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(32))                           # proposal | message
    ref: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending")     # pending|approved|edited|rejected|sent|failed
    decision: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[float] = mapped_column(Float, default=now)
    decided: Mapped[float] = mapped_column(Float, default=0)


class Edit(Base):
    """Raw user edits to drafts (diffs). NOT memory: the promotion rule decides what becomes memory."""
    __tablename__ = "edits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[str] = mapped_column(Text)
    after: Mapped[str] = mapped_column(Text)
    ops: Mapped[list] = mapped_column(JSON, default=list)
    created: Mapped[float] = mapped_column(Float, default=now)


class Outcome(Base):
    __tablename__ = "outcomes"
    __table_args__ = (UniqueConstraint("user_id", "proposal_id", "stage"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    proposal_id: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(64), default="")
    stage: Mapped[str] = mapped_column(String(32))                          # submitted|viewed|replied|interview|hired|lost
    strategy: Mapped[str] = mapped_column(String(32), default="")
    connects: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[float] = mapped_column(Float, default=now)


class Submission(Base):
    """Exactly-once ledger for external writes: one row per idempotency key."""
    __tablename__ = "submissions"
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    operation: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[float] = mapped_column(Float, default=now)


def init_db() -> None:
    Base.metadata.create_all(ENGINE)


@contextmanager
def session() -> Session:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

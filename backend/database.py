"""
PostgreSQL storage for PROSE-MEET (research-grade persistence).

Set DATABASE_URL in .env, e.g.:
  postgresql://user:password@localhost:5432/prose_meet
"""
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# PostgreSQL-specific: JSONB for efficient querying of result payload
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

DATABASE_URL = os.getenv("DATABASE_URL")


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    """Saved meeting: transcript, summary, highlights, speakers (result as JSONB)."""
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(nullable=False, default="meeting")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(timezone.utc))
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)

    def to_list_item(self):
        created = self.created_at
        if created is None:
            created_str = ""
        else:
            created_str = created.isoformat()
            if created_str.endswith("+00:00"):
                created_str = created_str.replace("+00:00", "Z")
        result = self.result or {}
        return {
            "id": str(self.id),
            "filename": self.filename,
            "created_at": created_str,
            "duration_seconds": result.get("duration_seconds"),
        }


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL must be set to use PostgreSQL storage")
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=os.getenv("SQL_ECHO", "").lower() in ("1", "true"),
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.orm import sessionmaker
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def session_scope():
    """Provide a transactional scope for a series of operations."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Create tables if they do not exist. Call once at app startup."""
    Base.metadata.create_all(bind=get_engine())


def save_meeting_to_db(meeting_id: str, result: dict, filename: str = None):
    """Insert or replace a completed meeting (id can be UUID string)."""
    try:
        uid = uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id
    except (ValueError, TypeError):
        uid = uuid.uuid4()
    with session_scope() as session:
        existing = session.get(Meeting, uid)
        if existing:
            existing.filename = filename or existing.filename
            existing.result = result
            existing.created_at = datetime.now(timezone.utc)
        else:
            session.add(Meeting(
                id=uid,
                filename=filename or "meeting",
                result=result,
            ))
    return uid


def list_meetings_from_db():
    """Return all meetings sorted by created_at descending."""
    with session_scope() as session:
        stmt = select(Meeting).order_by(Meeting.created_at.desc())
        rows = session.scalars(stmt).all()
        return [r.to_list_item() for r in rows]


def get_meeting_result_from_db(meeting_id: str):
    """Load meeting result by id. Returns None if not found. Ensures filename is on result."""
    try:
        uid = uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id
    except (ValueError, TypeError):
        return None
    with session_scope() as session:
        row = session.get(Meeting, uid)
        if not row:
            return None
        result = row.result or {}
        if "filename" not in result:
            result = {**result, "filename": row.filename or "meeting"}
        return result


def delete_meeting_from_db(meeting_id: str):
    """Delete meeting row by id. Returns True if a row was removed."""
    try:
        uid = uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id
    except (ValueError, TypeError):
        return False
    with session_scope() as session:
        row = session.get(Meeting, uid)
        if not row:
            return False
        session.delete(row)
        return True

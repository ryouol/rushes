import uuid
from datetime import UTC, datetime

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSONB, list: JSONB}


class Record:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(default=now)


class Tenant(Record):
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)


class User(SQLAlchemyBaseUserTableUUID, Base):
    name: Mapped[str] = mapped_column(String(120), default="")


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass


class GoogleIdentity(Base):
    __tablename__ = "google_identity"
    subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), unique=True
    )
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempt"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(43))
    verifier: Mapped[str] = mapped_column(String(43))
    destination: Mapped[str] = mapped_column(String(2048))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Logout revokes an explicit linking attempt as well as its initiating session.
    link_session_token: Mapped[str | None] = mapped_column(
        String(43), ForeignKey("accesstoken.token", ondelete="CASCADE"), index=True
    )


class Workspace(Record, Base):
    __tablename__ = "workspace"
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    balance_milli: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (CheckConstraint("balance_milli >= 0"),)


class Membership(Record, Base):
    __tablename__ = "membership"
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="editor")
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        CheckConstraint("role IN ('owner', 'editor', 'viewer')"),
    )


class Project(Tenant, Base):
    __tablename__ = "project"
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(default="")


class Asset(Tenant, Base):
    __tablename__ = "asset"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_root: Mapped[str]
    relative_path: Mapped[str]
    source_kind: Mapped[str] = mapped_column(default="indexed")
    import_relative_path: Mapped[str] = mapped_column(default="")
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("asset.id"))
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    source_size: Mapped[int] = mapped_column(BigInteger, default=0)
    source_mtime_ns: Mapped[int] = mapped_column(BigInteger, default=0)
    duration_us: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(default="queued")
    error: Mapped[str | None]
    proxy_path: Mapped[str | None]
    thumbnail_path: Mapped[str | None]
    __table_args__ = (UniqueConstraint("project_id", "source_root", "relative_path"),)


class MediaTimeline(Tenant, Base):
    __tablename__ = "media_timeline"
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id"), index=True)
    kind: Mapped[str] = mapped_column(default="source")
    details: Mapped[dict]
    mapping: Mapped[dict] = mapped_column(default=dict)
    __table_args__ = (UniqueConstraint("asset_id", "kind"),)


class Shot(Tenant, Base):
    __tablename__ = "shot"
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id"), index=True)
    start_us: Mapped[int] = mapped_column(BigInteger)
    end_us: Mapped[int] = mapped_column(BigInteger)
    producer: Mapped[str] = mapped_column(default="scenedetect-content-v1")
    __table_args__ = (
        CheckConstraint("start_us >= 0 AND end_us > start_us"),
        UniqueConstraint("asset_id", "start_us", "end_us"),
    )


class AnalysisRun(Tenant, Base):
    __tablename__ = "analysis_run"
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id"), index=True)
    operation_key: Mapped[str] = mapped_column(unique=True)
    model: Mapped[str]
    prompt_version: Mapped[str]
    preprocessing_version: Mapped[str]
    schema_version: Mapped[str]
    transcript_version: Mapped[str]
    sampling: Mapped[dict]
    status: Mapped[str] = mapped_column(default="queued")


class AnalysisWindow(Tenant, Base):
    __tablename__ = "analysis_window"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_run.id"), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id"), index=True)
    start_us: Mapped[int] = mapped_column(BigInteger)
    end_us: Mapped[int] = mapped_column(BigInteger)
    cache_key: Mapped[str] = mapped_column(unique=True)
    state: Mapped[str] = mapped_column(default="pending")
    raw_response: Mapped[dict | None]
    input_snapshot: Mapped[dict | None]
    provider_file: Mapped[str | None]
    provider_file_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_file_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]
    attempts: Mapped[int] = mapped_column(default=0)
    __table_args__ = (CheckConstraint("start_us >= 0 AND end_us > start_us"),)


class Observation(Tenant, Base):
    __tablename__ = "observation"
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id"), index=True)
    timeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_timeline.id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_run.id"))
    window_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_window.id"))
    operation_key: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str]
    start_us: Mapped[int] = mapped_column(BigInteger)
    end_us: Mapped[int] = mapped_column(BigInteger)
    proposed_start_us: Mapped[int] = mapped_column(BigInteger)
    proposed_end_us: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str]
    attributes: Mapped[dict] = mapped_column(default=dict)
    evidence: Mapped[list] = mapped_column(default=list)
    producer: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    preprocessing_version: Mapped[str]
    review_status: Mapped[str] = mapped_column(default="unreviewed")
    uncertainty: Mapped[str] = mapped_column(default="approximate")
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        CheckConstraint("start_us >= 0 AND end_us > start_us"),
        CheckConstraint("proposed_start_us >= 0 AND proposed_end_us > proposed_start_us"),
        Index("observation_asset_time", "asset_id", "start_us"),
    )


class ObservationRevision(Tenant, Base):
    __tablename__ = "observation_revision"
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observation.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    version: Mapped[int]
    before: Mapped[dict]
    after: Mapped[dict]
    __table_args__ = (UniqueConstraint("observation_id", "version"),)


class Embedding(Tenant, Base):
    __tablename__ = "embedding"
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("observation.id"), index=True)
    model: Mapped[str]
    dimension: Mapped[int]
    text_hash: Mapped[str]
    vector: Mapped[list[float]] = mapped_column(Vector())
    __table_args__ = (UniqueConstraint("observation_id", "model"),)


class Collection(Tenant, Base):
    __tablename__ = "collection"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    instructions: Mapped[str] = mapped_column(default="")
    saved_query: Mapped[str | None]


class CollectionItem(Tenant, Base):
    __tablename__ = "collection_item"
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection.id"), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("asset.id"))
    start_us: Mapped[int | None] = mapped_column(BigInteger)
    end_us: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(default="")
    position: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        CheckConstraint(
            "(start_us IS NULL AND end_us IS NULL) OR (start_us IS NOT NULL AND end_us IS NOT NULL AND start_us >= 0 AND end_us > start_us)"
        ),
    )


class Job(Tenant, Base):
    __tablename__ = "job"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("asset.id"))
    kind: Mapped[str]
    state: Mapped[str] = mapped_column(default="queued")
    stage: Mapped[str] = mapped_column(default="Waiting for worker")
    progress: Mapped[int] = mapped_column(default=0)
    workflow_id: Mapped[str] = mapped_column(unique=True)
    payload: Mapped[dict] = mapped_column(default=dict)
    error: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)


class ProcessingEvent(Tenant, Base):
    __tablename__ = "processing_event"
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"), index=True)
    kind: Mapped[str]
    message: Mapped[str]


class Export(Tenant, Base):
    __tablename__ = "export"
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job.id"), unique=True)
    kind: Mapped[str]
    name: Mapped[str]
    plan: Mapped[dict]
    state: Mapped[str] = mapped_column(default="queued")
    output_path: Mapped[str | None]
    provenance: Mapped[dict] = mapped_column(default=dict)


class Reservation(Tenant, Base):
    __tablename__ = "reservation"
    operation_key: Mapped[str] = mapped_column(unique=True)
    amount_milli: Mapped[int] = mapped_column(BigInteger)
    settled_milli: Mapped[int] = mapped_column(BigInteger, default=0)
    cycle: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(default="reserved")
    __table_args__ = (
        CheckConstraint(
            "amount_milli >= 0 AND settled_milli >= 0 AND settled_milli <= amount_milli"
        ),
    )


class LedgerEntry(Tenant, Base):
    __tablename__ = "ledger_entry"
    operation_key: Mapped[str] = mapped_column(unique=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reservation.id"))
    kind: Mapped[str]
    delta_milli: Mapped[int] = mapped_column(BigInteger)
    balance_milli: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str]


class Usage(Tenant, Base):
    __tablename__ = "usage"
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("asset.id"))
    operation_key: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str]
    model: Mapped[str | None]
    duration_us: Mapped[int] = mapped_column(BigInteger, default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    attempts: Mapped[int] = mapped_column(default=1)
    provider_outcome: Mapped[str] = mapped_column(default="confirmed")


TENANT_TABLES = [
    table.name
    for table in Base.metadata.sorted_tables
    if table.name
    not in {"user", "accesstoken", "google_identity", "oauth_attempt", "workspace", "membership"}
]

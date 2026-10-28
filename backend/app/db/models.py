from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.naming import column_name, table_name


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = table_name("user")
    __table_args__ = (
        UniqueConstraint(
            column_name("user_key"),
            name="uq_t_user_f_user_key",
        ),
    )

    id: Mapped[int] = mapped_column(
        column_name("id"),
        BigInteger,
        Identity(),
        primary_key=True,
    )
    user_key: Mapped[str] = mapped_column(
        column_name("user_key"), String(36), index=True
    )
    username: Mapped[str] = mapped_column(
        column_name("username"), String(100), unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(column_name("display_name"), String(100))
    role: Mapped[str] = mapped_column(column_name("role"), String(20), index=True)
    password_hash: Mapped[str] = mapped_column(column_name("password_hash"), Text)
    is_active: Mapped[bool] = mapped_column(
        column_name("is_active"), Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        column_name("created_at"), DateTime(timezone=True)
    )


class DataDictionaryRow(Base):
    __tablename__ = table_name("data_dictionary")
    __table_args__ = (
        UniqueConstraint(
            column_name("dictionary_key"),
            name="uq_t_data_dictionary_f_dictionary_key",
        ),
        UniqueConstraint(
            column_name("namespace"),
            column_name("key"),
            name="uq_t_data_dictionary_f_namespace_f_key",
        ),
    )

    id: Mapped[int] = mapped_column(
        column_name("id"),
        BigInteger,
        Identity(),
        primary_key=True,
    )
    dictionary_key: Mapped[str] = mapped_column(
        column_name("dictionary_key"),
        String(36),
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(
        column_name("namespace"), String(100), index=True
    )
    key: Mapped[str] = mapped_column(column_name("key"), String(200), index=True)
    value_type: Mapped[str] = mapped_column(column_name("value_type"), String(20))
    value_text: Mapped[str] = mapped_column(column_name("value_text"), Text)
    is_secret: Mapped[bool] = mapped_column(
        column_name("is_secret"), Boolean, default=False, nullable=False
    )
    description: Mapped[str] = mapped_column(
        column_name("description"), String(500), default=""
    )
    revision: Mapped[int] = mapped_column(
        column_name("revision"), Integer, default=1, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        column_name("created_at"), DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        column_name("updated_at"), DateTime(timezone=True), index=True
    )
    updated_by: Mapped[str] = mapped_column(
        column_name("updated_by"), String(36), default=""
    )


class AuthAuditRow(Base):
    __tablename__ = table_name("auth_audit_event")
    __table_args__ = (
        UniqueConstraint(
            column_name("event_key"),
            name="uq_t_auth_audit_event_f_event_key",
        ),
    )

    id: Mapped[int] = mapped_column(
        column_name("id"),
        BigInteger,
        Identity(),
        primary_key=True,
    )
    event_key: Mapped[str] = mapped_column(
        column_name("event_key"), String(36), index=True
    )
    event: Mapped[str] = mapped_column(column_name("event"), String(50), index=True)
    outcome: Mapped[str] = mapped_column(
        column_name("outcome"), String(30), index=True
    )
    username: Mapped[str] = mapped_column(
        column_name("username"), String(100), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        column_name("user_id"), String(36), nullable=True, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        column_name("actor_id"), String(36), nullable=True, index=True
    )
    ip_address: Mapped[str] = mapped_column(column_name("ip_address"), String(64))
    user_agent: Mapped[str] = mapped_column(column_name("user_agent"), String(500))
    detail: Mapped[str] = mapped_column(column_name("detail"), Text)
    created_at: Mapped[datetime] = mapped_column(
        column_name("created_at"), DateTime(timezone=True), index=True
    )


class CaseRow(Base):
    __tablename__ = table_name("case")
    __table_args__ = (
        UniqueConstraint(
            column_name("case_key"),
            name="uq_t_case_f_case_key",
        ),
    )

    id: Mapped[int] = mapped_column(
        column_name("id"),
        BigInteger,
        Identity(),
        primary_key=True,
    )
    case_key: Mapped[str] = mapped_column(
        column_name("case_key"), String(36), index=True
    )
    owner_id: Mapped[str] = mapped_column(
        column_name("owner_id"), String(36), index=True, default=""
    )
    status: Mapped[str] = mapped_column(column_name("status"), String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(
        column_name("created_at"), DateTime(timezone=True), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        column_name("updated_at"), DateTime(timezone=True), index=True
    )
    payload_json: Mapped[str] = mapped_column(column_name("payload_json"), Text)


class AnalysisJobRow(Base):
    __tablename__ = table_name("analysis_job")
    __table_args__ = (
        UniqueConstraint(
            column_name("job_key"),
            name="uq_t_analysis_job_f_job_key",
        ),
    )

    id: Mapped[int] = mapped_column(
        column_name("id"),
        BigInteger,
        Identity(),
        primary_key=True,
    )
    job_key: Mapped[str] = mapped_column(
        column_name("job_key"), String(36), index=True
    )
    case_id: Mapped[str] = mapped_column(
        column_name("case_id"),
        String(36),
        ForeignKey("t_case.f_case_key", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        column_name("status"), String(20), index=True
    )
    attempt_count: Mapped[int] = mapped_column(
        column_name("attempt_count"), Integer, default=0, nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        column_name("max_attempts"), Integer, default=2, nullable=False
    )
    lease_owner: Mapped[str] = mapped_column(
        column_name("lease_owner"), String(100), default=""
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        column_name("lease_expires_at"), DateTime(timezone=True), nullable=True
    )
    error: Mapped[str] = mapped_column(column_name("error"), Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        column_name("created_at"), DateTime(timezone=True), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        column_name("updated_at"), DateTime(timezone=True), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        column_name("started_at"), DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        column_name("completed_at"), DateTime(timezone=True), nullable=True
    )

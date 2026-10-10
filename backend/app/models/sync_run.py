"""One attempt to import access history from one device."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SyncStatus(enum.StrEnum):
    running = "running"
    success = "success"
    partial = "partial"  # some chunks imported, then a failure
    failed = "failed"


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(16))  # manual | scheduled
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("app_users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, native_enum=False, length=16, create_constraint=True, name="status",
             values_callable=lambda e: [m.value for m in e]), default=SyncStatus.running)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synced_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # contiguous progress
    records_found: Mapped[int] = mapped_column(Integer, default=0)      # reported by the device
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)   # new rows
    records_existing: Mapped[int] = mapped_column(Integer, default=0)   # already imported earlier
    queries: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list[Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

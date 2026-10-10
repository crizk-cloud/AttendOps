"""Access history read from devices. Rows are imported verbatim and never edited by the app."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AccessLog(Base):
    __tablename__ = "access_logs"
    __table_args__ = (
        UniqueConstraint("device_id", "rec_no"),
        Index("ix_access_logs_device_id_event_time", "device_id", "event_time"),
        Index("ix_access_logs_card_name_trgm", "card_name", postgresql_using="gin",
              postgresql_ops={"card_name": "gin_trgm_ops"}),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # RESTRICT: a device that has history cannot be deleted by accident (disable it instead).
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    rec_no: Mapped[int] = mapped_column(BigInteger)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    device_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    card_name: Mapped[str | None] = mapped_column(String(200))
    card_no: Mapped[str | None] = mapped_column(String(64), index=True)
    type: Mapped[str | None] = mapped_column(String(32))
    method: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[int | None] = mapped_column(Integer)
    door: Mapped[int | None] = mapped_column(Integer)
    reader_id: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[int | None] = mapped_column(Integer)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

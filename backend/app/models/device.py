"""Registered devices.

Columns are grouped by who owns the data:
  - configured in AttendOps (name, ip, port, credentials, enabled, notes)
  - reported by the device (model, firmware, serial_no, capabilities)
  - observed by AttendOps when contacting it (status, last_seen_at, last_checked_at, last_error, ...)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.devices.base import DeviceStatus


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("ip", "port"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- configured in AttendOps ---
    name: Mapped[str] = mapped_column(String(100))
    vendor: Mapped[str] = mapped_column(String(32), default="dahua", server_default="dahua")
    ip: Mapped[str] = mapped_column(String(45))
    port: Mapped[int] = mapped_column(Integer, default=80, server_default="80")
    username: Mapped[str] = mapped_column(String(64))
    # Fernet ciphertext. Never returned by the API or logged.
    encrypted_password: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notes: Mapped[str | None] = mapped_column(String(500))

    # --- reported by the device ---
    model: Mapped[str | None] = mapped_column(String(100))
    firmware: Mapped[str | None] = mapped_column(String(200))
    serial_no: Mapped[str | None] = mapped_column(String(100))
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    capabilities_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- observed by AttendOps ---
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, native_enum=False, length=16, create_constraint=True, name="status",
             values_callable=lambda e: [m.value for m in e]),
        default=DeviceStatus.unknown, server_default=DeviceStatus.unknown.value)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last successful contact
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    last_response_ms: Mapped[int | None] = mapped_column(Integer)

    # --- history sync progress ---
    # Everything with event time before this has been imported contiguously.
    synced_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())

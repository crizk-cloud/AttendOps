from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.devices.base import DeviceStatus

Port = Field(default=80, ge=1, le=65535)


def _ip(v: Any) -> str:
    v = str(v).strip()
    for cls in (IPv4Address, IPv6Address):
        try:
            return str(cls(v))
        except ValueError:
            pass
    raise ValueError(f"{v!r} is not a valid IP address")


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    ip: str
    port: int = Port
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=500)

    _ip = field_validator("ip", mode="before")(_ip)


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    ip: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=64)
    # Omit (or null) to keep the stored password.
    password: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("ip", mode="before")
    @classmethod
    def _valid_ip(cls, v: Any) -> Any:
        return None if v is None else _ip(v)


class BulkDeviceLine(BaseModel):
    ip: str
    name: str | None = Field(default=None, max_length=100)
    port: int = Port
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)

    _ip = field_validator("ip", mode="before")(_ip)


class BulkDeviceCreate(BaseModel):
    devices: list[BulkDeviceLine] = Field(min_length=1, max_length=500)
    default_username: str | None = Field(default=None, max_length=64)
    default_password: str | None = Field(default=None, max_length=128)


class BulkResult(BaseModel):
    created: list[int]
    skipped: list[dict[str, str]]


class ConnectionTest(BaseModel):
    """Test credentials before saving. With device_id, missing fields come from the stored device."""

    device_id: int | None = None
    ip: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)

    @field_validator("ip", mode="before")
    @classmethod
    def _valid_ip(cls, v: Any) -> Any:
        return None if v is None else _ip(v)


class ConnectionTestResult(BaseModel):
    status: DeviceStatus
    model: str | None = None
    firmware: str | None = None
    serial_no: str | None = None
    error: str | None = None
    response_ms: int | None = None


class DeviceOut(BaseModel):
    """Never contains the password. `username` is only filled in for admins."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    # configured in AttendOps
    name: str
    vendor: str
    ip: str
    port: int
    username: str | None = None
    enabled: bool
    notes: str | None
    # reported by the device
    model: str | None
    firmware: str | None
    serial_no: str | None
    capabilities: dict[str, Any] | None
    capabilities_checked_at: datetime | None
    # observed by AttendOps
    status: DeviceStatus
    last_seen_at: datetime | None
    last_checked_at: datetime | None
    last_error: str | None
    last_response_ms: int | None
    checking: bool = False
    created_at: datetime

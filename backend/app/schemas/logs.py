from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.models import SyncStatus


class AccessLogOut(BaseModel):
    """A record read from a device (not editable in the app)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    device_name: str
    rec_no: int
    event_time: datetime | None
    device_user_id: str | None
    card_name: str | None
    card_no: str | None
    type: str | None
    method: int | None
    status: int | None
    door: int | None
    reader_id: str | None
    error_code: int | None
    granted: bool | None


class AccessLogDetail(AccessLogOut):
    raw_payload: dict[str, Any]
    imported_at: datetime


class LogPage(BaseModel):
    items: list[AccessLogOut]
    total: int
    page: int
    page_size: int


class SyncRequest(BaseModel):
    """Optional explicit range (dates in the app time zone, inclusive). Omit both for an incremental sync."""

    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _order(self) -> "SyncRequest":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        return self


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    device_name: str | None = None
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    status: SyncStatus
    window_start: datetime
    window_end: datetime
    synced_until: datetime | None
    records_found: int
    records_inserted: int
    records_existing: int
    queries: int
    warnings: list[Any] | None
    error_message: str | None

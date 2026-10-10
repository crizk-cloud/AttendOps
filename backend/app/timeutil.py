"""Time handling: store UTC (timestamptz), present in the configured zone (Asia/Beirut)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def app_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime; all stored datetimes must be timezone-aware")
    return dt.astimezone(app_zone())

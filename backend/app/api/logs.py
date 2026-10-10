"""Access history (imported from devices): search, filter, paginate."""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import require_viewer
from app.db import get_db
from app.models import AccessLog, AppUser, Device
from app.schemas.logs import AccessLogDetail, AccessLogOut, LogPage
from app.timeutil import app_zone

router = APIRouter(prefix="/api/logs", tags=["logs"])

SUCCESS_STATUS = 1  # verified on the devices: Status=1 means access granted


def local_day_start(d: date) -> datetime:
    """Midnight of a calendar day in the app time zone (Asia/Beirut), as an aware datetime."""
    return datetime.combine(d, time.min, tzinfo=app_zone())


def _row(log: AccessLog, device_name: str, detail: bool = False) -> AccessLogOut:
    cls = AccessLogDetail if detail else AccessLogOut
    data = {c: getattr(log, c) for c in cls.model_fields if hasattr(log, c)}
    data["device_name"] = device_name
    data["granted"] = None if log.status is None else log.status == SUCCESS_STATUS
    return cls(**data)


def _filtered(q: Select, device_id: list[int] | None, date_from: date | None, date_to: date | None,
              search: str | None, type_: str | None, result: str | None) -> Select:
    if device_id:
        q = q.where(AccessLog.device_id.in_(device_id))
    if date_from:
        q = q.where(AccessLog.event_time >= local_day_start(date_from))
    if date_to:
        q = q.where(AccessLog.event_time < local_day_start(date_to + timedelta(days=1)))
    if search:
        term = search.strip()
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        q = q.where(or_(AccessLog.card_name.ilike(like), AccessLog.card_no == term,
                        AccessLog.device_user_id == term))
    if type_:
        q = q.where(AccessLog.type == type_)
    if result == "granted":
        q = q.where(AccessLog.status == SUCCESS_STATUS)
    elif result == "denied":
        q = q.where(or_(AccessLog.status != SUCCESS_STATUS, AccessLog.status.is_(None)))
    return q


@router.get("", response_model=LogPage)
def search_logs(
    device_id: list[int] | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=100, description="name contains, or exact card number / user ID"),
    type: str | None = Query(default=None, max_length=32),
    result: str | None = Query(default=None, pattern="^(granted|denied)$"),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    _: AppUser = Depends(require_viewer),
    db: Session = Depends(get_db),
) -> LogPage:
    base = _filtered(select(AccessLog, Device.name).join(Device, Device.id == AccessLog.device_id),
                     device_id, date_from, date_to, q, type, result)
    total = db.scalar(_filtered(select(func.count()).select_from(AccessLog), device_id, date_from, date_to,
                                q, type, result)) or 0
    order = AccessLog.event_time.asc() if sort == "asc" else AccessLog.event_time.desc()
    rows = db.execute(base.order_by(order.nulls_last(), AccessLog.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return LogPage(items=[_row(log, name) for log, name in rows], total=total, page=page, page_size=page_size)


@router.get("/types", response_model=list[str])
def log_types(_: AppUser = Depends(require_viewer), db: Session = Depends(get_db)) -> list[str]:
    """Distinct event types seen so far (e.g. Entry, Exit), for the filter dropdown."""
    return [t for t in db.scalars(select(AccessLog.type).distinct().order_by(AccessLog.type)) if t]


@router.get("/{log_id}", response_model=AccessLogDetail)
def get_log(log_id: int, _: AppUser = Depends(require_viewer), db: Session = Depends(get_db)) -> AccessLogOut:
    row = db.execute(select(AccessLog, Device.name).join(Device).where(AccessLog.id == log_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found")
    return _row(row[0], row[1], detail=True)

"""Trigger history imports and inspect sync runs."""

from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.logs import local_day_start
from app.auth.deps import require_operator, require_viewer
from app.db import get_db
from app.models import AppUser, Device, SyncRun
from app.schemas.logs import SyncRequest, SyncRunOut
from app.services import sync as sync_svc

router = APIRouter(tags=["sync"])


@router.post("/api/devices/{device_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_one(device_id: int, body: SyncRequest | None = Body(default=None),
             user: AppUser = Depends(require_operator), db: Session = Depends(get_db)) -> dict:
    if db.get(Device, device_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    body = body or SyncRequest()
    start = local_day_start(body.start_date) if body.start_date else None
    end = local_day_start(body.end_date + timedelta(days=1)) if body.end_date else None
    started = sync_svc.sync_devices_in_background([device_id], requested_by=user.id, start=start, end=end)
    if not started:
        raise HTTPException(status.HTTP_409_CONFLICT, "A sync of this device is already running")
    return {"queued": True}


@router.post("/api/sync/all", status_code=status.HTTP_202_ACCEPTED)
def sync_all(user: AppUser = Depends(require_operator), db: Session = Depends(get_db)) -> dict:
    ids = list(db.scalars(select(Device.id).where(Device.enabled.is_(True))))
    return {"queued": len(sync_svc.sync_devices_in_background(ids, requested_by=user.id))}


@router.get("/api/sync/runs", response_model=list[SyncRunOut])
def list_runs(device_id: int | None = None, limit: int = Query(default=50, ge=1, le=500),
              _: AppUser = Depends(require_viewer), db: Session = Depends(get_db)) -> list[SyncRunOut]:
    q = select(SyncRun, Device.name).join(Device).order_by(SyncRun.started_at.desc(), SyncRun.id.desc()).limit(limit)
    if device_id is not None:
        q = q.where(SyncRun.device_id == device_id)
    out = []
    for run, name in db.execute(q).all():
        item = SyncRunOut.model_validate(run)
        item.device_name = name
        out.append(item)
    return out

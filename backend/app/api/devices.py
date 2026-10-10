"""Device registration and connectivity.

Permissions: viewers see devices; operators can trigger checks; admins add/edit/remove devices and
handle credentials. Passwords go in, never out.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import require_admin, require_operator, require_viewer
from app.db import get_db
from app.devices.base import DeviceStatus
from app.models import AppUser, Device, Role
from app.schemas.devices import (
    BulkDeviceCreate,
    BulkResult,
    ConnectionTest,
    ConnectionTestResult,
    DeviceCreate,
    DeviceOut,
    DeviceUpdate,
)
from app.security.crypto import CredentialDecryptError, decrypt_secret, encrypt_secret
from app.services import devices as svc

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _out(device: Device, user: AppUser, checking: set[int] | None = None) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    out.username = device.username if user.role == Role.admin else None
    out.checking = device.id in (checking if checking is not None else svc.checking_ids())
    return out


def _get(db: Session, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


def _duplicate(db: Session, ip: str, port: int, exclude_id: int | None = None) -> bool:
    q = select(Device.id).where(Device.ip == ip, Device.port == port)
    if exclude_id is not None:
        q = q.where(Device.id != exclude_id)
    return db.scalar(q) is not None


@router.get("", response_model=list[DeviceOut])
def list_devices(user: AppUser = Depends(require_viewer), db: Session = Depends(get_db)) -> list[DeviceOut]:
    checking = svc.checking_ids()
    devices = db.scalars(select(Device).order_by(Device.name, Device.ip))
    return [_out(d, user, checking) for d in devices]


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, user: AppUser = Depends(require_viewer),
               db: Session = Depends(get_db)) -> DeviceOut:
    return _out(_get(db, device_id), user)


@router.post("/test-connection", response_model=ConnectionTestResult)
def test_connection(body: ConnectionTest, _: AppUser = Depends(require_admin),
                    db: Session = Depends(get_db)) -> ConnectionTestResult:
    base = _get(db, body.device_id) if body.device_id is not None else None
    ip = body.ip or (base.ip if base else None)
    port = body.port or (base.port if base else 80)
    username = body.username or (base.username if base else None)
    password = body.password
    if password is None and base is not None:
        try:
            password = decrypt_secret(base.encrypted_password)
        except CredentialDecryptError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Stored password cannot be decrypted") from None
    if not (ip and username and password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ip, username and password are required")
    r = svc.test_connection(base.vendor if base else "dahua", ip, port, username, password)
    ident = r.identity
    return ConnectionTestResult(status=r.status, error=r.error, response_ms=r.response_ms,
                                model=ident and ident.model, firmware=ident and ident.firmware,
                                serial_no=ident and ident.serial_no)


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(body: DeviceCreate, check: bool = True, user: AppUser = Depends(require_admin),
                  db: Session = Depends(get_db)) -> DeviceOut:
    if _duplicate(db, body.ip, body.port):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A device at {body.ip}:{body.port} already exists")
    device = Device(name=body.name.strip(), ip=body.ip, port=body.port, username=body.username,
                    encrypted_password=encrypt_secret(body.password), notes=body.notes)
    db.add(device)
    db.commit()
    if check:
        # Identify model/firmware and capabilities right away. An unreachable device is still saved.
        svc.check_device(db, device)
    return _out(device, user)


@router.post("/bulk", response_model=BulkResult, status_code=status.HTTP_201_CREATED)
def bulk_create(body: BulkDeviceCreate, _: AppUser = Depends(require_admin),
                db: Session = Depends(get_db)) -> BulkResult:
    created: list[Device] = []
    skipped: list[dict[str, str]] = []
    seen: set[tuple[str, int]] = set()
    for line in body.devices:
        key = (line.ip, line.port)
        username = line.username or body.default_username
        password = line.password or body.default_password
        if key in seen or _duplicate(db, *key):
            skipped.append({"ip": f"{line.ip}:{line.port}", "reason": "already registered"})
            continue
        if not username or not password:
            skipped.append({"ip": f"{line.ip}:{line.port}", "reason": "no username/password given"})
            continue
        seen.add(key)
        device = Device(name=(line.name or line.ip).strip(), ip=line.ip, port=line.port, username=username,
                        encrypted_password=encrypt_secret(password))
        db.add(device)
        created.append(device)
    db.commit()
    ids = [d.id for d in created]
    svc.check_devices_in_background(ids)
    return BulkResult(created=ids, skipped=skipped)


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, body: DeviceUpdate, user: AppUser = Depends(require_admin),
                  db: Session = Depends(get_db)) -> DeviceOut:
    device = _get(db, device_id)
    changes = body.model_dump(exclude_unset=True)
    new_ip, new_port = changes.get("ip") or device.ip, changes.get("port") or device.port
    if (new_ip, new_port) != (device.ip, device.port) and _duplicate(db, new_ip, new_port, device.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A device at {new_ip}:{new_port} already exists")
    connection_changed = False
    for field in ("ip", "port", "username"):
        if changes.get(field) is not None and changes[field] != getattr(device, field):
            setattr(device, field, changes[field])
            connection_changed = True
    if changes.get("password"):
        device.encrypted_password = encrypt_secret(changes["password"])
        connection_changed = True
    if changes.get("name"):
        device.name = changes["name"].strip()
    if "notes" in changes:
        device.notes = changes["notes"]
    if changes.get("enabled") is not None:
        device.enabled = changes["enabled"]
    if connection_changed:
        device.status, device.last_error = DeviceStatus.unknown, None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another device uses this address") from None
    if connection_changed:
        svc.check_device(db, device)
    return _out(device, user)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int, _: AppUser = Depends(require_admin),
                  db: Session = Depends(get_db)) -> Response:
    db.delete(_get(db, device_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_id}/check", response_model=DeviceOut)
def check_now(device_id: int, user: AppUser = Depends(require_operator),
              db: Session = Depends(get_db)) -> DeviceOut:
    return _out(svc.check_device(db, _get(db, device_id)), user)


@router.post("/{device_id}/detect", response_model=DeviceOut)
def redetect(device_id: int, user: AppUser = Depends(require_admin),
             db: Session = Depends(get_db)) -> DeviceOut:
    """Re-read model/firmware and re-probe capabilities (read-only probes)."""
    return _out(svc.check_device(db, _get(db, device_id), detect=True), user)


@router.post("/check-all", status_code=status.HTTP_202_ACCEPTED)
def check_all(_: AppUser = Depends(require_operator), db: Session = Depends(get_db)) -> dict:
    ids = list(db.scalars(select(Device.id).where(Device.enabled.is_(True))))
    started = svc.check_devices_in_background(ids)
    return {"queued": len(started)}

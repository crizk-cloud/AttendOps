"""Device connectivity checks and capability detection.

Each check opens its own DB session, so a slow or failing device never holds up another.
"""

import logging
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker
from app.devices.base import CheckResult, DeviceStatus, capabilities_to_json
from app.devices.registry import get_driver
from app.models import Device
from app.security.crypto import CredentialDecryptError, decrypt_secret
from app.timeutil import utcnow

log = logging.getLogger(__name__)

# Tests replace this to route device traffic to an in-process fake. None = real network.
transport_factory: Callable[[str, int], httpx.BaseTransport | None] = lambda ip, port: None  # noqa: E731

_checking: set[int] = set()
_checking_lock = threading.Lock()


def checking_ids() -> set[int]:
    with _checking_lock:
        return set(_checking)


def driver_for(vendor: str, ip: str, port: int, username: str, password: str):
    return get_driver(vendor, ip, port, username, password, transport=transport_factory(ip, port))


def test_connection(vendor: str, ip: str, port: int, username: str, password: str) -> CheckResult:
    """Check credentials/reachability without saving anything."""
    return driver_for(vendor, ip, port, username, password).check()


def check_device(db: Session, device: Device, *, detect: bool = False) -> Device:
    """Contact one device, record the result, and (re)detect capabilities when needed."""
    try:
        password = decrypt_secret(device.encrypted_password)
    except CredentialDecryptError:
        _record(device, CheckResult(DeviceStatus.error,
                                    error="Stored password cannot be decrypted; re-enter it"))
        db.commit()
        return device
    driver = driver_for(device.vendor, device.ip, device.port, device.username, password)
    result = driver.check()
    identity_changed = _record(device, result)
    if result.status == DeviceStatus.online and (detect or identity_changed or device.capabilities is None):
        try:
            device.capabilities = capabilities_to_json(driver.probe_capabilities())
            device.capabilities_checked_at = utcnow()
        except Exception:  # noqa: BLE001 - detection is best effort; the check itself succeeded
            log.exception("capability detection failed for device %s", device.id)
    db.commit()
    log.info("device %s (%s) -> %s", device.id, device.ip, device.status.value)
    return device


def _record(device: Device, result: CheckResult) -> bool:
    """Store a check result. Returns True if the reported model/firmware changed."""
    now = utcnow()
    device.status = result.status
    device.last_checked_at = now
    device.last_response_ms = result.response_ms
    device.last_error = (result.error or None) and result.error[:300]
    changed = False
    if result.status == DeviceStatus.online:
        device.last_seen_at = now
        ident = result.identity
        if ident:
            for attr in ("model", "firmware", "serial_no"):
                new = getattr(ident, attr)
                if new and new != getattr(device, attr):
                    changed = changed or attr in ("model", "firmware")
                    setattr(device, attr, new)
    return changed


def _check_by_id(device_id: int) -> None:
    try:
        with get_sessionmaker()() as db:
            device = db.get(Device, device_id)
            if device is not None:
                check_device(db, device)
    except Exception:  # noqa: BLE001 - one device's failure must not affect the others
        log.exception("check failed for device %s", device_id)
    finally:
        with _checking_lock:
            _checking.discard(device_id)


def check_devices_in_background(device_ids: Iterable[int]) -> list[int]:
    """Check many devices concurrently (bounded). Skips devices already being checked."""
    with _checking_lock:
        ids = [i for i in device_ids if i not in _checking]
        _checking.update(ids)
    if not ids:
        return []

    def run() -> None:
        with ThreadPoolExecutor(max_workers=get_settings().device_max_concurrency,
                                thread_name_prefix="device-check") as pool:
            list(pool.map(_check_by_id, ids))

    threading.Thread(target=run, name="device-check-batch", daemon=True).start()
    return ids

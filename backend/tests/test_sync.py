import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, text

from app.db import get_engine
from app.models import AccessLog, Device, Role, SyncRun, SyncStatus
from app.security.crypto import encrypt_secret
from app.services import devices as dev_svc
from app.services import sync as sync_svc
from tests.fake_dahua import FakeDahua

PW = "Dev1ce-Secret!"
NOW = int(time.time())


@pytest.fixture
def fakes(monkeypatch):
    registry: dict[str, FakeDahua] = {}

    def unreachable(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    def factory(ip, port):
        return registry[ip].transport() if ip in registry else httpx.MockTransport(unreachable)

    monkeypatch.setattr(dev_svc, "transport_factory", factory)
    return registry


@pytest.fixture
def device_factory(db, fakes):
    def make(ip: str, *, online: bool = True, name: str | None = None) -> tuple[Device, FakeDahua | None]:
        fake = None
        if online:
            fake = FakeDahua(password=PW)
            fakes[ip] = fake
        d = Device(name=name or f"Door {ip}", ip=ip, port=80, username="admin", encrypted_password=encrypt_secret(PW))
        db.add(d)
        db.commit()
        return d, fake
    return make


def count_logs(db, device_id=None) -> int:
    q = select(func.count()).select_from(AccessLog)
    if device_id:
        q = q.where(AccessLog.device_id == device_id)
    return db.scalar(q)


def run_of(db, run_id) -> SyncRun:
    db.expire_all()
    return db.get(SyncRun, run_id)


def test_initial_sync_imports_everything_across_the_cap(db, device_factory):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 86400 * 2 + i * 50 for i in range(3000)])  # 3000 records, needs splitting
    run = run_of(db, sync_svc.sync_device(device.id))
    assert run.status == SyncStatus.success, run.error_message
    assert (run.records_found, run.records_inserted, run.records_existing) == (3000, 3000, 0)
    assert run.queries > 3  # had to split windows
    assert count_logs(db, device.id) == 3000
    db.refresh(device)
    assert device.synced_until is not None and device.last_sync_status == "success"
    assert all(int(r.url.params["StartTime"]) >= 0 for r in fake.requests if "StartTime" in r.url.params)


def test_resync_is_idempotent_and_incremental(db, device_factory):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 3600 * 5 + i * 60 for i in range(100)])
    sync_svc.sync_device(device.id)
    again = run_of(db, sync_svc.sync_device(device.id))
    assert again.records_inserted == 0
    assert count_logs(db, device.id) == 100
    # The incremental window starts at the last sync point minus the overlap, not at the beginning.
    assert again.window_start > datetime.fromtimestamp(NOW - 3600 * 3, UTC)

    fake.add_records([NOW - 30, NOW - 20, NOW - 10])
    third = run_of(db, sync_svc.sync_device(device.id))
    assert third.records_inserted == 3 and count_logs(db, device.id) == 103


def test_unreachable_device_fails_cleanly(db, device_factory):
    device, _ = device_factory("10.1.0.9", online=False)
    run = run_of(db, sync_svc.sync_device(device.id))
    assert run.status == SyncStatus.failed and run.error_message == "Connection timed out"
    db.refresh(device)
    assert device.synced_until is None and device.last_sync_status == "failed"


def test_failure_midway_keeps_completed_chunks_and_resumes(db, device_factory):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 86400 * 3 + i * 600 for i in range(400)])  # spread over 3 days -> several chunks
    fake.fail_after_queries = 1  # first chunk works, then the device drops off
    run = run_of(db, sync_svc.sync_device(device.id))
    assert run.status == SyncStatus.partial
    imported = count_logs(db, device.id)
    assert 0 <= imported < 400
    db.refresh(device)
    progress = device.synced_until
    assert progress is not None

    fake.fail_after_queries = None
    resumed = run_of(db, sync_svc.sync_device(device.id))
    assert resumed.status == SyncStatus.success
    assert resumed.window_start < progress  # resumed from the last good point (minus overlap)
    assert count_logs(db, device.id) == 400


def test_recno_reuse_is_reported_not_silently_dropped(db, device_factory):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 600])
    sync_svc.sync_device(device.id)
    fake.records[0]["CreateTime"] = str(NOW - 300)  # same RecNo, different time (e.g. device reset)
    run = run_of(db, sync_svc.sync_device(device.id, start=datetime.fromtimestamp(NOW - 3600, UTC)))
    assert run.status == SyncStatus.partial
    conflict = next(w for w in run.warnings if isinstance(w, dict))
    assert conflict["type"] == "recno_conflict" and conflict["count"] == 1


def test_explicit_range_does_not_move_sync_point(db, device_factory):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 86400 * 40, NOW - 100])
    sync_svc.sync_device(device.id)
    assert count_logs(db, device.id) == 1  # 40-day-old record is outside the 30-day initial backfill
    db.refresh(device)
    before = device.synced_until
    run = run_of(db, sync_svc.sync_device(device.id, start=datetime.fromtimestamp(NOW - 86400 * 41, UTC),
                                          end=datetime.fromtimestamp(NOW - 86400 * 39, UTC)))
    assert run.records_inserted == 1 and count_logs(db, device.id) == 2
    db.refresh(device)
    assert device.synced_until == before


def test_same_device_cannot_sync_twice_at_once(db, device_factory):
    device, _ = device_factory("10.1.0.1")
    with get_engine().connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:ns, :id)"), {"ns": sync_svc.LOCK_NAMESPACE, "id": device.id})
        with pytest.raises(sync_svc.SyncBusy):
            sync_svc.sync_device(device.id)
        other.execute(text("SELECT pg_advisory_unlock(:ns, :id)"), {"ns": sync_svc.LOCK_NAMESPACE, "id": device.id})
    sync_svc.sync_device(device.id)  # works once released


def test_stale_running_run_is_closed(db, device_factory):
    device, _ = device_factory("10.1.0.1")
    stale = SyncRun(device_id=device.id, trigger="manual", status=SyncStatus.running,
                    window_start=datetime.now(UTC), window_end=datetime.now(UTC))
    db.add(stale)
    db.commit()
    sync_svc.sync_device(device.id)
    assert run_of(db, stale.id).status == SyncStatus.failed


def test_pins_are_not_stored(db, device_factory):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 60], Password="4321")
    sync_svc.sync_device(device.id)
    log = db.scalar(select(AccessLog))
    assert log.raw_payload["Password"] == "[redacted]"


# --- API ---------------------------------------------------------------------

def wait_sync(timeout=10.0):
    deadline = time.monotonic() + timeout
    while sync_svc.syncing_ids() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not sync_svc.syncing_ids()


@pytest.fixture
def op(make_user, login):
    make_user("op@example.com", Role.operator)
    return login("op@example.com")


def test_sync_all_isolates_failing_devices(client, db, device_factory, op):
    good1, f1 = device_factory("10.1.0.1")
    bad, _ = device_factory("10.1.0.2", online=False)
    good2, f2 = device_factory("10.1.0.3")
    f1.add_records([NOW - 100, NOW - 50])
    f2.add_records([NOW - 70])
    assert client.post("/api/sync/all", headers=op).json() == {"queued": 3}
    wait_sync()
    runs = {r["device_id"]: r for r in client.get("/api/sync/runs", headers=op).json()}
    assert runs[good1.id]["status"] == "success" and runs[good1.id]["records_inserted"] == 2
    assert runs[good2.id]["status"] == "success" and runs[good2.id]["records_inserted"] == 1
    assert runs[bad.id]["status"] == "failed"


def test_sync_endpoint_permissions_and_range(client, db, device_factory, op, make_user, login):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 86400 * 35])
    make_user("v@example.com")
    assert client.post(f"/api/devices/{device.id}/sync", headers=login("v@example.com")).status_code == 403
    old_day = datetime.fromtimestamp(NOW - 86400 * 35, UTC).date()
    r = client.post(f"/api/devices/{device.id}/sync", headers=op,
                    json={"start_date": str(old_day - timedelta(days=1)), "end_date": str(old_day + timedelta(days=1))})
    assert r.status_code == 202
    wait_sync()
    assert count_logs(db, device.id) == 1
    bad = client.post(f"/api/devices/{device.id}/sync", headers=op,
                      json={"start_date": "2026-05-02", "end_date": "2026-05-01"})
    assert bad.status_code == 422


def test_device_with_logs_cannot_be_deleted(client, db, device_factory, make_user, login):
    device, fake = device_factory("10.1.0.1")
    fake.add_records([NOW - 60])
    sync_svc.sync_device(device.id)
    make_user("admin@example.com", Role.admin)
    r = client.delete(f"/api/devices/{device.id}", headers=login("admin@example.com"))
    assert r.status_code == 409 and "Disable it instead" in r.json()["detail"]


def test_record_on_chunk_boundary_is_counted_once(db, device_factory, monkeypatch):
    device, fake = device_factory("10.1.0.1")
    start = datetime.fromtimestamp(NOW - 86400 * 2, UTC)
    boundary = int((start + timedelta(hours=24)).timestamp())
    fake.add_records([boundary - 1, boundary, boundary + 1])
    run = run_of(db, sync_svc.sync_device(device.id, start=start, end=datetime.fromtimestamp(NOW, UTC)))
    assert (run.records_found, run.records_inserted, run.records_existing) == (3, 3, 0)

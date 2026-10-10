"""Import access history from devices into access_logs.

Guarantees:
- Idempotent: rows are upserted on (device_id, rec_no); re-running a sync never duplicates.
- Complete: windows that hit the device's 1024-record cap are split (see devices/dahua/records.py).
- Isolated: each device syncs in its own thread/session; one failure never blocks another.
- Exclusive: a PostgreSQL advisory lock per device prevents two syncs of the same device at once,
  across processes (API and the Phase 4 worker).
- Resumable: devices.synced_until only advances over fully imported, contiguous chunks.
"""

import logging
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Connection, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.devices.dahua.records import FetchStats, RecordFetchError, normalize_record
from app.models import AccessLog, Device, SyncRun, SyncStatus
from app.security.crypto import CredentialDecryptError, decrypt_secret
from app.services.devices import driver_for
from app.timeutil import utcnow

log = logging.getLogger(__name__)

LOCK_NAMESPACE = 734_001  # first key of pg_advisory_lock(int, int); second key is the device id
INSERT_BATCH = 1000

_syncing: set[int] = set()
_syncing_lock = threading.Lock()


def syncing_ids() -> set[int]:
    with _syncing_lock:
        return set(_syncing)


class SyncBusy(Exception):
    pass


@dataclass
class UpsertResult:
    inserted: int = 0
    existing: int = 0
    conflicts: int = 0  # same RecNo already stored with a different time (device reset?)
    conflict_samples: list[dict] | None = None


def upsert_records(db: Session, device_id: int, raw_records: list[dict]) -> UpsertResult:
    rows = []
    for raw in raw_records:
        n = normalize_record(raw)
        if n["rec_no"] is None:
            continue
        rows.append({"device_id": device_id, **n})
    result = UpsertResult(conflict_samples=[])
    for i in range(0, len(rows), INSERT_BATCH):
        batch = rows[i:i + INSERT_BATCH]
        stmt = (pg_insert(AccessLog).values(batch)
                .on_conflict_do_nothing(index_elements=["device_id", "rec_no"])
                .returning(AccessLog.rec_no))
        inserted = set(db.scalars(stmt))
        result.inserted += len(inserted)
        skipped = {r["rec_no"]: r for r in batch if r["rec_no"] not in inserted}
        if skipped:
            existing = db.execute(select(AccessLog.rec_no, AccessLog.event_time)
                                  .where(AccessLog.device_id == device_id,
                                         AccessLog.rec_no.in_(list(skipped)))).all()
            for rec_no, event_time in existing:
                if event_time != skipped[rec_no]["event_time"]:
                    result.conflicts += 1
                    if len(result.conflict_samples) < 5:
                        result.conflict_samples.append({
                            "rec_no": rec_no, "stored_time": str(event_time),
                            "device_time": str(skipped[rec_no]["event_time"])})
                else:
                    result.existing += 1
    return result


def _chunks(start: datetime, end: datetime, hours: int) -> Iterable[tuple[datetime, datetime]]:
    step = timedelta(hours=hours)
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt


def _try_lock(conn: Connection, device_id: int) -> bool:
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(:ns, :id)"),
                             {"ns": LOCK_NAMESPACE, "id": device_id}).scalar())


def _unlock(conn: Connection, device_id: int) -> None:
    conn.execute(text("SELECT pg_advisory_unlock(:ns, :id)"), {"ns": LOCK_NAMESPACE, "id": device_id})


def sync_device(device_id: int, *, trigger: str = "manual", requested_by: int | None = None,
                start: datetime | None = None, end: datetime | None = None) -> int:
    """Synchronously import history for one device. Returns the SyncRun id.

    Without start/end: incremental from devices.synced_until (minus overlap), or the initial backfill.
    With start/end: re-import exactly that range (does not move synced_until).
    Raises SyncBusy if this device is already being synced anywhere.
    """
    s = get_settings()
    with get_engine().connect() as lock_conn:
        if not _try_lock(lock_conn, device_id):
            raise SyncBusy(f"device {device_id} is already being synced")
        lock_conn.commit()
        try:
            with get_sessionmaker()() as db:
                return _run(db, device_id, trigger, requested_by, start, end, s)
        finally:
            _unlock(lock_conn, device_id)
            lock_conn.commit()


def _run(db: Session, device_id: int, trigger: str, requested_by: int | None,
         start: datetime | None, end: datetime | None, s) -> int:
    device = db.get(Device, device_id)
    if device is None:
        raise ValueError(f"device {device_id} not found")
    now = utcnow()
    explicit = start is not None or end is not None
    if explicit:
        window_start = start or (now - timedelta(days=s.sync_initial_days))
        window_end = end or now
    else:
        window_start = (device.synced_until - timedelta(minutes=s.sync_overlap_minutes)
                        if device.synced_until else now - timedelta(days=s.sync_initial_days))
        # Read a little past "now" so records stamped by a device clock that runs ahead are not missed.
        window_end = now + timedelta(minutes=s.sync_overlap_minutes)

    # We hold the device lock, so any other "running" run for this device is a leftover from a crash.
    db.execute(update(SyncRun).where(SyncRun.device_id == device_id, SyncRun.status == SyncStatus.running)
               .values(status=SyncStatus.failed, finished_at=now, error_message="Interrupted (process stopped)"))
    run = SyncRun(device_id=device_id, trigger=trigger, requested_by=requested_by, status=SyncStatus.running,
                  window_start=window_start, window_end=window_end, warnings=[])
    db.add(run)
    db.commit()

    warnings: list = []
    chunks_done = 0
    try:
        password = decrypt_secret(device.encrypted_password)
        driver = driver_for(device.vendor, device.ip, device.port, device.username, password)
        for c_start, c_end in _chunks(window_start, window_end, s.sync_chunk_hours):
            stats = FetchStats()
            # Chunks are [start, end): the boundary second belongs to the next chunk, so a record exactly on
            # it is fetched (and counted) once. The last chunk includes its end.
            last_second = int(c_end.timestamp()) - (0 if c_end >= window_end else 1)
            records = driver.fetch_access_records(int(c_start.timestamp()), last_second, stats)
            res = upsert_records(db, device_id, records)
            run.records_found += len(records)
            run.records_inserted += res.inserted
            run.records_existing += res.existing
            run.queries += stats.queries
            warnings.extend(stats.warnings[:20])
            if res.conflicts:
                warnings.append({"type": "recno_conflict", "count": res.conflicts, "samples": res.conflict_samples,
                                 "message": "Records with an already-stored RecNo but a different time were NOT "
                                            "imported. The device may have been reset."})
            progress = min(c_end, now)
            run.synced_until = progress
            if not explicit and (device.synced_until is None or progress > device.synced_until):
                device.synced_until = progress
            run.warnings = list(warnings)
            db.commit()  # each chunk is durable on its own
            chunks_done += 1
        has_conflicts = any(isinstance(w, dict) and w.get("type") == "recno_conflict" for w in warnings)
        run.status = SyncStatus.partial if has_conflicts else SyncStatus.success
        if has_conflicts:
            run.error_message = "Some records could not be imported (RecNo conflict); see warnings."
    except (RecordFetchError, CredentialDecryptError) as exc:
        db.rollback()
        run.status = SyncStatus.partial if chunks_done else SyncStatus.failed
        run.error_message = str(exc)[:1000]
    except Exception as exc:  # noqa: BLE001 - recorded on the run; must not crash the batch
        db.rollback()
        log.exception("sync of device %s failed", device_id)
        run.status = SyncStatus.partial if chunks_done else SyncStatus.failed
        run.error_message = f"Internal error: {type(exc).__name__}"
    run.finished_at = utcnow()
    run.warnings = warnings or None
    device.last_sync_at = run.finished_at
    device.last_sync_status = run.status.value
    db.commit()
    log.info("sync device %s: %s, %s new / %s found in %s queries", device_id, run.status.value,
             run.records_inserted, run.records_found, run.queries)
    return run.id


def _sync_safely(device_id: int, trigger: str, requested_by: int | None,
                 start: datetime | None, end: datetime | None) -> None:
    try:
        sync_device(device_id, trigger=trigger, requested_by=requested_by, start=start, end=end)
    except SyncBusy:
        log.info("device %s skipped: sync already running", device_id)
    except Exception:  # noqa: BLE001
        log.exception("sync of device %s crashed", device_id)
    finally:
        with _syncing_lock:
            _syncing.discard(device_id)


def sync_devices_in_background(device_ids: Iterable[int], *, trigger: str = "manual",
                               requested_by: int | None = None, start: datetime | None = None,
                               end: datetime | None = None) -> list[int]:
    with _syncing_lock:
        ids = [i for i in device_ids if i not in _syncing]
        _syncing.update(ids)
    if not ids:
        return []

    def run() -> None:
        with ThreadPoolExecutor(max_workers=get_settings().device_max_concurrency,
                                thread_name_prefix="device-sync") as pool:
            list(pool.map(lambda i: _sync_safely(i, trigger, requested_by, start, end), ids))

    threading.Thread(target=run, name="device-sync-batch", daemon=True).start()
    return ids


def log_count(db: Session, device_id: int) -> int:
    return db.scalar(select(func.count()).select_from(AccessLog).where(AccessLog.device_id == device_id)) or 0

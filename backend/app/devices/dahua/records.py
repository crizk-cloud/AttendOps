"""Fetching access records from a Dahua device without ever dropping any.

Verified device behaviour (from the user's tests and dahua_attendance_logger.py):
  recordFinder.cgi?action=find&name=AccessControlCardRec&StartTime=<unix>&EndTime=<unix>&count=<n>
  - StartTime/EndTime must be Unix integers.
  - At most 1024 records per call.

Strategy: query a window; if the answer may be truncated (it hit the cap), split the window in two and
query each half, recursively. Halves overlap by one second so no boundary second is missed whatever the
device's inclusive/exclusive semantics; duplicates are removed by RecNo. If a one-second window still hits
the cap we cannot split further, so we raise instead of silently losing records.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.devices.dahua.parsing import parse_indexed

MAX_PER_QUERY = 1024

# (start_unix, end_unix, count) -> raw response text
QueryFn = Callable[[int, int, int], str]


class RecordFetchError(Exception):
    pass


class TruncationError(RecordFetchError):
    """A window cannot be split further but still returns a full page."""


@dataclass
class FetchStats:
    queries: int = 0
    splits: int = 0
    found_total: int = 0  # sum of `found` over the leaf windows actually used
    warnings: list[str] = field(default_factory=list)


def fetch_window(query: QueryFn, start: int, end: int, cap: int = MAX_PER_QUERY,
                 stats: FetchStats | None = None) -> list[dict[str, str]]:
    """All records with CreateTime in [start, end], de-duplicated by RecNo, sorted by RecNo."""
    stats = stats if stats is not None else FetchStats()
    by_recno: dict[str, dict[str, str]] = {}
    _collect(query, start, end, cap, stats, by_recno)
    return sorted(by_recno.values(), key=lambda r: _int(r.get("RecNo")) or 0)


def _collect(query: QueryFn, start: int, end: int, cap: int, stats: FetchStats,
             out: dict[str, dict[str, str]]) -> None:
    text = query(start, end, cap)
    stats.queries += 1
    top, records = parse_indexed(text)
    if "found" not in top:
        raise RecordFetchError(f"unexpected response for window {start}-{end}: {text[:120]!r}")
    found = _int(top["found"])
    if found is None:
        raise RecordFetchError(f"non-numeric found={top['found']!r}")
    if found != len(records):
        stats.warnings.append(f"window {start}-{end}: found={found} but {len(records)} records parsed")

    if max(found, len(records)) >= cap:  # possibly truncated
        if end - start < 2:
            raise TruncationError(
                f"{max(found, len(records))} records in the {end - start + 1}s window starting {start}; "
                f"cannot split further")
        mid = (start + end) // 2
        stats.splits += 1
        _collect(query, start, mid, cap, stats, out)
        _collect(query, mid, end, cap, stats, out)
        return

    stats.found_total += found
    for rec in records:
        recno = rec.get("RecNo")
        if recno is None or _int(recno) is None:
            stats.warnings.append(f"record without valid RecNo skipped: {rec!r}"[:300])
            continue
        out[recno] = rec


def _int(v: Any) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def redact(raw: dict[str, str]) -> dict[str, str]:
    """Records can carry a Password field (door PIN). Never store or show its value."""
    return {k: ("[redacted]" if "password" in k.lower() and v else v) for k, v in raw.items()}


def normalize_record(raw: dict[str, str]) -> dict[str, Any]:
    """Map a raw device record to access_logs columns. The raw record (PINs redacted) goes to raw_payload."""
    create = _int(raw.get("CreateTime"))
    return {
        "rec_no": _int(raw.get("RecNo")),
        # CreateTime is treated as a true Unix epoch (UTC). See README "Time handling".
        "event_time": datetime.fromtimestamp(create, UTC) if create is not None else None,
        "device_user_id": raw.get("UserID") or None,
        "card_name": raw.get("CardName") or None,
        "card_no": raw.get("CardNo") or None,
        "type": raw.get("Type") or None,
        "method": _int(raw.get("Method")),
        "status": _int(raw.get("Status")),
        "door": _int(raw.get("Door")),
        "reader_id": raw.get("ReaderID") or None,
        "error_code": _int(raw.get("ErrorCode")),
        "raw_payload": redact(raw),
    }

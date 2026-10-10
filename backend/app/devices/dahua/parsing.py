"""Parsers for Dahua CGI responses.

Formats (verified on the real devices for recordFinder and the event stream; see README):
  key=value lines           found=2 / records[0].CardName=John / type=DHI-ASI2212J-PW
  event stream blocks       Code=AccessControlEvent;action=Pulse;index=0;data={...json...}
"""

import json
import re
from typing import Any

_INDEXED = re.compile(r"^(?P<list>\w+)\[(?P<idx>\d+)\]\.(?P<field>.+)$")


def parse_kv(text: str) -> dict[str, str]:
    """Flat key=value lines -> dict. Splits on the first '=' only; values may contain '='."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            out[key.strip()] = value.strip()
    return out


def parse_indexed(text: str, list_name: str = "records") -> tuple[dict[str, str], list[dict[str, str]]]:
    """Fold `records[i].Field=value` lines into a list of dicts (ordered by i).

    Returns (top_level_fields, items). Same approach as dahua_attendance_logger.py, but tolerant of
    unexpected list names, out-of-order indexes and blank lines.
    """
    top: dict[str, str] = {}
    items: dict[int, dict[str, str]] = {}
    for key, value in parse_kv(text).items():
        m = _INDEXED.match(key)
        if m and m["list"] == list_name:
            items.setdefault(int(m["idx"]), {})[m["field"]] = value
        else:
            top[key] = value
    return top, [items[i] for i in sorted(items)]


def parse_event_line(line: str) -> dict[str, Any] | None:
    """Parse one event line: Code=...;action=...;index=...;data={json}. Returns None if not an event."""
    line = line.strip()
    if not line.startswith("Code="):
        return None
    head, sep, data = line.partition(";data=")
    event: dict[str, Any] = {}
    for part in head.split(";"):
        k, _, v = part.partition("=")
        if k:
            event[k] = v
    if sep:
        try:
            event["data"] = json.loads(data)
        except json.JSONDecodeError:
            event["data_raw"] = data
    return event

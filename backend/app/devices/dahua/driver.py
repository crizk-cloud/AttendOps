"""Dahua access-control driver: connectivity check, identification and capability probing.

Verified on the real DHI-ASI2212J-PW devices (by the user, before this project):
  - Digest auth on port 80
  - recordFinder.cgi AccessControlCardRec with Unix-integer StartTime/EndTime
  - eventManager.cgi attach stream
NOT yet verified on these devices (standard Dahua HTTP API; confirm with tools/probe_device.py):
  - magicBox.cgi getDeviceType / getSoftwareVersion / getSerialNo
  - AccessUser.cgi / AccessCard.cgi startFind, recordFinder AccessControlCard
"""

import re
import time

import httpx

from app.devices.base import (
    Capability,
    CapabilityState,
    CheckResult,
    DeviceIdentity,
    DeviceStatus,
    Operation,
)
from app.devices.dahua.client import DahuaClient
from app.devices.dahua.parsing import parse_kv
from app.devices.dahua.records import FetchStats, RecordFetchError, fetch_window

UNSUPPORTED_CODES = {400, 404, 405, 501}


def _clean_error(exc: Exception) -> str:
    """Short, credential-free description of a transport error."""
    name = type(exc).__name__
    if isinstance(exc, httpx.ConnectTimeout):
        return "Connection timed out"
    if isinstance(exc, httpx.ReadTimeout):
        return "Device did not answer in time"
    if isinstance(exc, httpx.ConnectError):
        msg = str(exc).lower()
        if "refused" in msg:
            return "Connection refused"
        if "no route" in msg or "unreachable" in msg:
            return "Host unreachable"
        return "Cannot connect"
    return name


def parse_firmware(text: str) -> str | None:
    kv = parse_kv(text)
    version = kv.get("version")
    if not version:
        return None
    # Typical value: "1.000.0000000.1.R,build:2023-03-15" -> keep both parts readable.
    return re.sub(r",\s*build:", " build ", version)


class DahuaDriver:
    vendor = "dahua"

    def __init__(self, ip: str, port: int, username: str, password: str,
                 transport: httpx.BaseTransport | None = None):
        self._args = (ip, port, username, password)
        self._transport = transport

    def _client(self) -> DahuaClient:
        return DahuaClient(*self._args, transport=self._transport)

    # -- connectivity + identity ---------------------------------------------
    def check(self) -> CheckResult:
        started = time.monotonic()
        try:
            with self._client() as c:
                r = c.get("/cgi-bin/magicBox.cgi", {"action": "getDeviceType"})
                if r.status_code == 401:
                    return CheckResult(DeviceStatus.auth_failed, error="Username or password rejected",
                                       response_ms=r.elapsed_ms)
                identity = DeviceIdentity()
                if r.status_code == 200:
                    identity.model = parse_kv(r.text).get("type") or None
                elif r.status_code not in UNSUPPORTED_CODES:
                    return CheckResult(DeviceStatus.error, error=f"Unexpected HTTP {r.status_code}",
                                       response_ms=r.elapsed_ms)
                if identity.model is None:
                    # Fallback: some firmwares only report the model in getSystemInfo.
                    si = c.get("/cgi-bin/magicBox.cgi", {"action": "getSystemInfo"})
                    if si.status_code == 200:
                        kv = parse_kv(si.text)
                        identity.model = kv.get("deviceType") or kv.get("updateSerial") or None
                        identity.serial_no = kv.get("serialNumber") or None
                fw = c.get("/cgi-bin/magicBox.cgi", {"action": "getSoftwareVersion"})
                if fw.status_code == 200:
                    identity.firmware = parse_firmware(fw.text)
                if identity.serial_no is None:
                    sn = c.get("/cgi-bin/magicBox.cgi", {"action": "getSerialNo"})
                    if sn.status_code == 200:
                        identity.serial_no = parse_kv(sn.text).get("sn") or None
        except httpx.TransportError as exc:
            return CheckResult(DeviceStatus.offline, error=_clean_error(exc),
                               response_ms=round((time.monotonic() - started) * 1000))
        return CheckResult(DeviceStatus.online, identity=identity,
                           response_ms=round((time.monotonic() - started) * 1000))

    # -- capabilities ---------------------------------------------------------
    def probe_capabilities(self) -> dict[Operation, Capability]:
        """Read-only probes. Write operations are never exercised automatically."""
        caps: dict[Operation, Capability] = {}
        now = int(time.time())
        with self._client() as c:
            caps[Operation.device_info] = self._probe(
                c, "/cgi-bin/magicBox.cgi", {"action": "getDeviceType"})
            caps[Operation.history_read] = self._probe(
                c, "/cgi-bin/recordFinder.cgi",
                {"action": "find", "name": "AccessControlCardRec", "StartTime": now - 3600,
                 "EndTime": now, "count": 1},
                ok=lambda text: "found=" in text)
            caps[Operation.cards_read_legacy] = self._probe(
                c, "/cgi-bin/recordFinder.cgi", {"action": "find", "name": "AccessControlCard", "count": 1},
                ok=lambda text: "found=" in text)
            caps[Operation.users_read] = self._probe_cursor(c, "AccessUser")
            caps[Operation.cards_read] = self._probe_cursor(c, "AccessCard")
        caps[Operation.events_subscribe] = Capability(
            CapabilityState.unverified, "Not probed automatically (long-lived stream)")
        for op in (Operation.users_write, Operation.cards_write):
            caps[op] = Capability(CapabilityState.unverified,
                                  "Writes are never probed automatically; requires a confirmed manual test")
        return caps

    @staticmethod
    def _probe(c: DahuaClient, path: str, params: dict, ok=lambda text: True) -> Capability:
        try:
            r = c.get(path, params)
        except httpx.TransportError as exc:
            return Capability(CapabilityState.unverified, f"Inconclusive: {_clean_error(exc)}")
        if r.status_code == 200 and ok(r.text):
            return Capability(CapabilityState.verified, "HTTP 200")
        if r.status_code in UNSUPPORTED_CODES:
            return Capability(CapabilityState.unsupported, f"HTTP {r.status_code}")
        return Capability(CapabilityState.unverified, f"Inconclusive: HTTP {r.status_code}")

    @staticmethod
    def _probe_cursor(c: DahuaClient, cgi: str) -> Capability:
        """startFind opens a read-only search cursor; always close it with stopFind."""
        path = f"/cgi-bin/{cgi}.cgi"
        try:
            r = c.get(path, {"action": "startFind"})
        except httpx.TransportError as exc:
            return Capability(CapabilityState.unverified, f"Inconclusive: {_clean_error(exc)}")
        if r.status_code in UNSUPPORTED_CODES:
            return Capability(CapabilityState.unsupported, f"HTTP {r.status_code}")
        token = parse_kv(r.text).get("Token") if r.status_code == 200 else None
        if not token:
            return Capability(CapabilityState.unverified, f"Inconclusive: HTTP {r.status_code}, no Token")
        try:
            c.get(path, {"action": "stopFind", "Token": token})
        except httpx.TransportError:
            pass
        return Capability(CapabilityState.verified, "startFind returned a search token")

    # -- access history -------------------------------------------------------
    def fetch_access_records(self, start: int, end: int, stats: FetchStats) -> list[dict[str, str]]:
        """All AccessControlCardRec records with CreateTime in [start, end] (Unix seconds)."""
        with self._client() as c:
            def query(s: int, e: int, count: int) -> str:
                r = c.get("/cgi-bin/recordFinder.cgi", {"action": "find", "name": "AccessControlCardRec",
                                                       "StartTime": s, "EndTime": e, "count": count})
                if r.status_code == 401:
                    raise RecordFetchError("Username or password rejected")
                if r.status_code != 200:
                    raise RecordFetchError(f"HTTP {r.status_code} from recordFinder")
                return r.text

            try:
                return fetch_window(query, start, end, stats=stats)
            except httpx.TransportError as exc:
                raise RecordFetchError(_clean_error(exc)) from exc

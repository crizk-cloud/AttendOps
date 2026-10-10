#!/usr/bin/env python3
"""Read-only probe for ONE Dahua access-control device.

Run this on the LAN (it needs direct HTTP access to the device). It only issues
GET requests whose `action` is on a read-only allowlist; any other action is
refused before a request is sent. It never creates, updates or deletes anything.

Output: a folder with one raw response file per call plus report.json.
Personal data (names, card numbers, user IDs) is masked by default and
passwords are always masked, so the folder is safe to share.

Usage:
    python3 probe_device.py 172.22.76.12 --user admin
    python3 probe_device.py 172.22.76.12 --user admin --listen 30   # also watch live events for 30 s

The password is read from DAHUA_PASSWORD or prompted for; it is never printed
or written to disk. Python 3.9+ standard library only.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Actions that only read state. startFind/doFind/stopFind open, page and close a
# server-side search cursor; they do not change stored data.
READ_ONLY_ACTIONS = {
    "getDeviceType", "getSystemInfo", "getSoftwareVersion", "getHardwareVersion",
    "getSerialNo", "getMachineName", "getVendor", "getCurrentTime", "getConfig",
    "getCaps", "getExposureEvents", "find", "startFind", "doFind", "stopFind",
    "list", "attach",
}

# Fields that are always masked (credentials) or masked unless --no-redact (PII).
ALWAYS_MASK = re.compile(r"(password|pwd|passwd)", re.I)
PII_FIELDS = re.compile(r"(CardName|CardNo|UserName|UserID|^Name$|\.Name$|PersonID|CitizenID|Phone)", re.I)


class Probe:
    def __init__(self, host: str, port: int, user: str, password: str, timeout: float, redact: bool, out: Path):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        self.redact = redact
        self.out = out
        self.calls: list[dict] = []
        mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, self.base, user, password)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPDigestAuthHandler(mgr),
            urllib.request.ProxyHandler({}),  # LAN device: never route through a proxy
        )

    # -- safety ---------------------------------------------------------------
    @staticmethod
    def _check_read_only(path: str) -> None:
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        actions = qs.get("action", [])
        if len(actions) != 1 or actions[0] not in READ_ONLY_ACTIONS:
            raise RuntimeError(f"refusing non-read-only request: {path}")

    # -- masking --------------------------------------------------------------
    def mask_text(self, text: str) -> str:
        out_lines = []
        for line in text.splitlines():
            key, sep, value = line.partition("=")
            if sep and value.strip():
                if ALWAYS_MASK.search(key):
                    value = "***"
                elif self.redact and PII_FIELDS.search(key):
                    value = _mask(value)
            out_lines.append(f"{key}{sep}{value}")
        text = "\n".join(out_lines)
        # Event payloads carry JSON (data={...}); mask its fields too.
        text = re.sub(r'("(?:[^"]*(?:password|pwd)[^"]*)"\s*:\s*)"[^"]*"', r'\1"***"', text, flags=re.I)
        if self.redact:
            text = re.sub(
                r'("(?:CardName|CardNo|UserName|UserID|Name|PersonID)"\s*:\s*)"([^"]*)"',
                lambda m: f'{m.group(1)}"{_mask(m.group(2))}"', text)
        return text

    # -- requests -------------------------------------------------------------
    def get(self, label: str, path: str) -> dict:
        self._check_read_only(path)
        started = time.monotonic()
        rec: dict = {"label": label, "path": path}
        try:
            with self.opener.open(self.base + path, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
                rec["status"] = resp.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            rec["status"] = e.code
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            body = ""
            rec["status"] = None
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        rec["body"] = body
        masked = self.mask_text(body)
        (self.out / f"{len(self.calls):02d}_{label}.txt").write_text(
            f"GET {path}\nHTTP {rec['status']}  ({rec['elapsed_ms']} ms)\n"
            + (f"error: {rec['error']}\n" if "error" in rec else "") + "\n" + masked + "\n")
        self.calls.append({k: v for k, v in rec.items() if k != "body"} | {"body_preview": masked[:600]})
        print(f"  {label:<28} HTTP {rec['status']}  {rec.get('error', '')}")
        return rec

    def listen(self, seconds: int) -> None:
        path = "/cgi-bin/eventManager.cgi?action=attach&codes=[AccessControlEvent]&heartbeat=5"
        self._check_read_only(path)
        print(f"  listening for events for {seconds}s (swipe a card now to capture one)...")
        captured: list[str] = []
        deadline = time.monotonic() + seconds
        status = None
        try:
            with self.opener.open(self.base + path, timeout=8) as resp:
                status = resp.status
                while time.monotonic() < deadline:
                    try:
                        line = resp.readline()
                    except socket.timeout:
                        continue
                    if not line:
                        break
                    captured.append(line.decode("utf-8", "replace").rstrip("\r\n"))
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            captured.append(f"[error] {type(e).__name__}: {e}")
        masked = self.mask_text("\n".join(captured))
        (self.out / f"{len(self.calls):02d}_event_stream.txt").write_text(f"GET {path}\nHTTP {status}\n\n{masked}\n")
        self.calls.append({"label": "event_stream", "path": path, "status": status,
                           "lines": len(captured), "body_preview": masked[:2000]})
        print(f"  {'event_stream':<28} HTTP {status}  {len(captured)} lines")


def _mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def parse_kv(body: str) -> dict[str, str]:
    out = {}
    for line in body.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--user", required=True)
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--listen", type=int, default=0, help="seconds to watch the live event stream (0 = skip)")
    ap.add_argument("--no-redact", action="store_true", help="keep names/card numbers (passwords stay masked)")
    ap.add_argument("--out", default=None, help="output folder (default probe_<host>_<timestamp>)")
    args = ap.parse_args()

    password = os.environ.get("DAHUA_PASSWORD") or getpass.getpass("Device password: ")
    out = Path(args.out or f"probe_{args.host.replace(':', '_')}_{datetime.now():%Y%m%d_%H%M%S}")
    out.mkdir(parents=True, exist_ok=True)
    p = Probe(args.host, args.port, args.user, password, args.timeout, not args.no_redact, out)
    probe_started_utc = datetime.now(timezone.utc)
    print(f"Probing {p.base} (read-only) -> {out}/")

    # 1. Identity: model / firmware / serial (used for capability detection).
    for action in ("getDeviceType", "getSystemInfo", "getSoftwareVersion", "getHardwareVersion",
                   "getSerialNo", "getMachineName", "getVendor"):
        p.get(f"magicBox_{action}", f"/cgi-bin/magicBox.cgi?action={action}")

    # 2. Clock and time-zone settings (needed to interpret CreateTime correctly).
    clock = p.get("global_getCurrentTime", "/cgi-bin/global.cgi?action=getCurrentTime")
    p.get("config_NTP", "/cgi-bin/configManager.cgi?action=getConfig&name=NTP")
    p.get("config_Locales", "/cgi-bin/configManager.cgi?action=getConfig&name=Locales")

    # 3. Supported event codes.
    p.get("eventManager_getExposureEvents", "/cgi-bin/eventManager.cgi?action=getExposureEvents")

    # 4. Access history sample: last 7 days, 5 records.
    now = int(time.time())
    hist = p.get("records_AccessControlCardRec",
                 f"/cgi-bin/recordFinder.cgi?action=find&name=AccessControlCardRec"
                 f"&StartTime={now - 7 * 86400}&EndTime={now + 86400}&count=5")

    # 5. Users / cards, older API: the AccessControlCard record set.
    p.get("records_AccessControlCard", "/cgi-bin/recordFinder.cgi?action=find&name=AccessControlCard&count=5")

    # 6. Users / cards, newer API: AccessUser / AccessCard search cursors.
    for cgi in ("AccessUser", "AccessCard"):
        p.get(f"{cgi}_getCaps", f"/cgi-bin/{cgi}.cgi?action=getCaps")
        start = p.get(f"{cgi}_startFind", f"/cgi-bin/{cgi}.cgi?action=startFind")
        kv = parse_kv(start["body"]) if start.get("status") == 200 else {}
        token = kv.get("Token")
        if token:
            p.get(f"{cgi}_doFind", f"/cgi-bin/{cgi}.cgi?action=doFind&Token={token}&Offset=0&Count=5")
            p.get(f"{cgi}_stopFind", f"/cgi-bin/{cgi}.cgi?action=stopFind&Token={token}")

    if args.listen > 0:
        p.listen(args.listen)

    # Time-zone analysis: compare device wall clock with this machine's UTC clock,
    # and the newest record's CreateTime with "now".
    analysis: dict = {"probe_host_utc": probe_started_utc.isoformat()}
    m = re.search(r"result=(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", clock.get("body", ""))
    if m:
        wall = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        offset = round((wall - probe_started_utc).total_seconds() / 900) * 900
        analysis["device_wall_clock"] = m.group(1)
        analysis["device_clock_minus_utc_hours"] = offset / 3600
    times = [int(v) for k, v in parse_kv(hist.get("body", "")).items()
             if k.endswith(".CreateTime") and v.isdigit()]
    if times:
        newest = max(times)
        analysis["newest_CreateTime"] = newest
        analysis["newest_CreateTime_as_utc"] = datetime.fromtimestamp(newest, timezone.utc).isoformat()
        analysis["seconds_before_probe_if_true_utc"] = int(probe_started_utc.timestamp()) - newest
        analysis["hint"] = ("Swipe a card right before probing. If seconds_before_probe_if_true_utc is small, "
                            "CreateTime is real UTC. If it is negative by about device_clock_minus_utc_hours*3600, "
                            "the device stores local wall time as epoch.")

    report = {
        "tool": "probe_device.py",
        "device": p.base,
        "redacted": p.redact,
        "time_analysis": analysis,
        "calls": p.calls,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(f"\nDone. Share the folder {out}/ (or just report.json). Passwords are never included.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

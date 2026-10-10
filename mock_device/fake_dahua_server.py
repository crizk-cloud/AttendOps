#!/usr/bin/env python3
"""FAKE Dahua devices for local development and demos. NOT real device communication.

Starts N fake devices on 127.0.0.1, one per port, each requiring HTTP Digest auth.
Register them in AttendOps as 127.0.0.1:<port> to try the UI without hardware.

    python3 mock_device/fake_dahua_server.py --count 3 --base-port 18081 --password demo-pass

Responses imitate the formats observed on the real DHI-ASI2212J-PW devices (recordFinder) and Dahua's
documented magicBox replies. Anything learned from this fake says nothing about the real devices.
Standard library only.
"""

import argparse
import hashlib
import random
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

REALM = "Login to FAKE-DAHUA"


def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


NAMES = ["Rami Haddad", "Lara Khoury", "Omar Saleh", "Nour Aoun", "Karim Nassar", "Maya Fares", "Ziad Tannous",
         "Hiba Mansour", "Fadi Rizk", "Rana Chami"]


def make_records(n: int, days: int, seed: int) -> list[dict[str, str]]:
    """Synthetic history: mostly working hours, ~5% denied."""
    rng = random.Random(seed)
    now = int(time.time())
    times = []
    for _ in range(n):
        day = rng.randint(0, days - 1)
        hour = rng.choice([7, 8, 8, 9, 12, 13, 16, 17, 17, 18]) if rng.random() < 0.9 else rng.randint(0, 23)
        t = now - day * 86400 - (now % 86400) + (hour - 3) * 3600 + rng.randint(0, 3599)  # Beirut ~ UTC+3
        if t < now:
            times.append(t)
    times.sort()
    recs = []
    for i, t in enumerate(times):
        p = rng.randrange(len(NAMES))
        denied = rng.random() < 0.05
        recs.append({"RecNo": str(i + 1), "CreateTime": str(t), "UserID": str(1001 + p), "CardName": NAMES[p],
                     "CardNo": f"{0xA1B2C300 + p:08X}", "Type": rng.choice(["Entry", "Exit"]), "Method": "1",
                     "Status": "0" if denied else "1", "Door": "0", "ReaderID": "1",
                     "ErrorCode": "16" if denied else "0", "Password": "", "URL": ""})
    return recs


def make_handler(username: str, password: str, serial: str, records: list[dict[str, str]]):
    nonce = secrets.token_hex(8)

    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeDahua/0"

        def log_message(self, fmt, *args):
            print(f"[fake :{self.server.server_port}] {self.command} {self.path}")

        def _send(self, code: int, body: str = "", headers: dict | None = None):
            data = body.encode()
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Type", "text/plain;charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            h = self.headers.get("Authorization", "")
            if not h.startswith("Digest "):
                return False
            f = dict(re.findall(r'(\w+)="?([^",]+)"?', h))
            ha1 = md5(f"{username}:{REALM}:{password}")
            ha2 = md5(f"GET:{f.get('uri')}")
            return f.get("username") == username and f.get("response") == md5(
                f"{ha1}:{nonce}:{f.get('nc')}:{f.get('cnonce')}:auth:{ha2}")

        def do_GET(self):
            if not self._authorized():
                return self._send(401, "", {"WWW-Authenticate": f'Digest realm="{REALM}", qop="auth", nonce="{nonce}", opaque="x"'})
            url = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            cgi, action = url.path.rsplit("/", 1)[-1], q.get("action")
            if cgi == "magicBox.cgi":
                body = {"getDeviceType": "type=DHI-ASI2212J-PW (FAKE)",
                        "getSoftwareVersion": "version=0.000.0000000.0.FAKE,build:2026-01-01",
                        "getSerialNo": f"sn={serial}"}.get(action)
                return self._send(200, body + "\r\n") if body else self._send(400, "Error\r\nBad Request!\r\n")
            if cgi == "global.cgi" and action == "getCurrentTime":
                return self._send(200, time.strftime("result=%Y-%m-%d %H:%M:%S\r\n"))
            if cgi == "recordFinder.cgi" and action == "find" and q.get("name") == "AccessControlCardRec":
                st, en = q.get("StartTime", ""), q.get("EndTime", "")
                if not (st.isdigit() and en.isdigit()):
                    return self._send(400, "Error\r\nBad Request!\r\n")  # real devices reject date strings too
                count = min(int(q.get("count", 1024)), 1024)  # same hard cap as the real devices
                hits = [r for r in records if int(st) <= int(r["CreateTime"]) <= int(en)][:count]
                lines = [f"found={len(hits)}"] + [f"records[{i}].{k}={v}" for i, r in enumerate(hits) for k, v in r.items()]
                return self._send(200, "\r\n".join(lines) + "\r\n")
            if cgi in ("AccessUser.cgi", "AccessCard.cgi") and action in ("startFind", "stopFind"):
                return self._send(200, "Token=1\r\nTotal=0\r\n" if action == "startFind" else "OK\r\n")
            return self._send(400, "Error\r\nBad Request!\r\n")

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--base-port", type=int, default=18081)
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default="demo-pass")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--records", type=int, default=2500, help="synthetic history records per device")
    ap.add_argument("--days", type=int, default=14, help="spread the history over this many days")
    args = ap.parse_args()
    for i in range(args.count):
        port = args.base_port + i
        records = make_records(args.records, args.days, seed=port)
        server = ThreadingHTTPServer((args.host, port),
                                     make_handler(args.username, args.password, f"FAKE{port}", records))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"FAKE device {i + 1} listening on {args.host}:{port} ({len(records)} synthetic records)")
    print("Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

# AttendOps: notes for Claude Code

Read this first in every session. The README has the full technical documentation.

## What this is

A web app to centrally manage and monitor Dahua access-control terminals (DHI-ASI2212J-PW today), built for the
owner of this VM. It runs on this Ubuntu VM (VirtualBox, bridged to the LAN, IP **172.22.9.22**), installed with
`./deploy/setup-ubuntu-vm.sh`. Users open it at **http://172.22.9.22:8080**.

Stack: Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 (backend), React + Vite + TypeScript
(frontend), Docker Compose (one `app` container serving API and website, plus `db`).

**This project is local only, with no GitHub.** `~/AttendOps` on this VM is the only copy of the code. Use git
locally for history (commit each step). There is no remote to push to.

## Rules from the owner (keep following them)

- Work incrementally, one phase at a time. Test each step. Explain important decisions briefly.
- Ask only essential questions. Ask before starting a new phase.
- **Do NOT modify or break `dahua_attendance_logger.py`.** It runs separately (elsewhere) on a schedule and pulls
  logs from the same devices. Keep device load low (`DEVICE_MAX_CONCURRENCY`, default 4).
- Real device integration wherever possible. Mocks stay clearly separated (`mock_device/`, `backend/tests/`).
  **Never claim something was verified on a real device when it wasn't.**
- Any device write (create/update/delete users or cards): investigate **read-only on ONE device first** and report
  what works. Changes are edited in the app as *pending changes*. Nothing is pushed to a device until the user
  confirms. Log the result per device. **Never do a destructive device operation without explicit confirmation.**
- Device credentials: Fernet-encrypted at rest, never returned by the API, never logged, never sent to the
  frontend. Never print `.env` contents or device passwords.
- Show times in Asia/Beirut. Store UTC. Clearly distinguish data read from devices from data maintained in the app.
- Write tests for parsing and sync logic, and run them before moving on.

## Production safety on this VM

The live app runs here with real data. When working:

- Ask the owner to take a **VirtualBox snapshot** before risky changes (migrations, Docker changes).
- **Never run `./install.sh --reset`, `docker compose down -v`, or anything that deletes the `attendops_pgdata`
  volume.** Never regenerate or edit the secrets in `.env`.
- Deploy a change: commit, then run `./install.sh` (rebuilds, applies migrations, keeps data and `.env`).
- Before a migration, back up the database (README → *Back up*).
- Tests drop and recreate their database schema. **Never point `TEST_DATABASE_URL` at the production database.**
  Use the throwaway test database below.

## Running checks on this VM

```bash
# one-time: Python tooling and a throwaway test database (separate from production)
sudo apt install -y python3.12-venv
cd ~/AttendOps/backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
docker run -d --name attendops-testdb --restart unless-stopped -e POSTGRES_PASSWORD=test \
  -p 127.0.0.1:55432:5432 postgres:16

# backend tests + lint
cd ~/AttendOps/backend
TEST_DATABASE_URL=postgresql+psycopg://postgres:test@127.0.0.1:55432/postgres .venv/bin/pytest
.venv/bin/ruff check app tests

# frontend build + lint (Node runs in a container; nothing installed on the VM)
cd ~/AttendOps/frontend
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/web -w /web node:22-slim \
  sh -c "npm ci --no-audit --no-fund && npm run build && npm run lint"
```

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Repo inspection, read-only device probe `tools/probe_device.py` | done |
| 1 | Scaffold, config, login with roles (admin/operator/viewer), JWT + rotating refresh | done |
| 2 | Device registration (single + bulk, per-device creds), checks, model/capability detection, dashboard | done |
| 3 | Historical log sync (cap-safe window splitting, idempotent upsert), searchable logs page | done |
| — | Installers + this VM deployment | done |
| 4 | **Next:** scheduled sync of all devices (separate worker process, APScheduler), sync history/diagnostics page; one failing device must not block others | todo |
| 5 | Device users/cards: read-only mirror first, then pending-change flow, only for operations confirmed to work | todo |
| 6 | Analytics: daily/weekly/monthly counts, granted vs denied, peak periods, per-device usage, filters | todo |
| 7 | Live event feed, RBAC refinement, audit log, deployment docs | todo |

Phases 1–3 were built and tested in a cloud session against **fake devices only** (92 backend tests). Nothing had been
verified against a real terminal before this VM existed.

## Open questions to settle with the real devices (from this VM)

1. **Run the probe first:** swipe a card at a device, then
   `python3 tools/probe_device.py 172.22.76.12 --user admin --listen 30` and review `probe_*/report.json`.
2. **`CreateTime` time zone.** It is assumed to be a true UTC epoch (as the logger assumes) and is shown in
   Beirut time. If the probe shows the device stores local wall time as epoch, times are off by 2–3 h; the raw
   value is in `access_logs.raw_payload`, so a fix needs no re-import.
3. **magicBox / AccessUser / AccessCard** responses follow Dahua docs but were not yet seen on these devices.
4. **Status/Method meaning:** `Status=1` → granted, anything else → denied; `Method=1` → card. Other values are
   unmapped.

## Facts about the environment

- Device API verified by the owner: Digest auth on port 80; `recordFinder.cgi?action=find&name=AccessControlCardRec`
  with **Unix-integer** `StartTime`/`EndTime`; max 1024 records per call; flat `records[i].Field=value` text;
  event stream `eventManager.cgi?action=attach&codes=[AccessControlEvent]&heartbeat=5`.
- The logger lists 32 devices: most of 172.22.76.11–36, 172.22.76.51–54, and 172.23.5.202/.203/.210 (a second subnet;
  the extra devices may be other models). Same username on all; the owner was advised to rotate the password
  because it appears in plain text in that script.
- Docker's internal network is pinned to `10.254.254.0/24` (`DOCKER_SUBNET`) so it never shadows the device
  subnets 172.22.x / 172.23.x.

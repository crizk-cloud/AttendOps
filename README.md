# AttendOps

Central management and monitoring for Dahua access-control terminals (currently ~23 × DHI-ASI2212J-PW on
172.22.76.12–35).

| Part | Stack |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16 |
| Frontend | React + Vite + TypeScript |
| Auth | Email/password accounts, roles `viewer` < `operator` < `admin`, JWT access + rotating refresh tokens, argon2id |

The existing `dahua_attendance_logger.py` integration is separate and is not touched by this project.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Inspect repo, read-only device probe (`tools/probe_device.py`) | done |
| 1 | Scaffold, docker-compose, config, login with roles | done |
| 2 | Device registration (single + bulk), connectivity, model/capability detection, dashboard | done |
| 3 | Historical log sync (idempotent, cap-safe), searchable logs table | done |
| 4 | Scheduled sync of all devices, sync history/diagnostics page | next |
| 5–7 | Users/cards, analytics, live feed, audit, deployment | planned |

## Install on your computer

AttendOps runs on one computer (Windows, macOS or Linux) **that is on the same network as the devices**.
Everything runs in Docker: a database container and one app container that serves both the website and the API.
Both restart automatically whenever Docker is running.

### Windows

1. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ (accept the WSL 2 option if
   asked), start it, and wait until it shows *Engine running*. In *Settings → General*, tick
   *Start Docker Desktop when you sign in* so AttendOps comes back after a reboot.
2. Get this project folder: on GitHub open branch `claude/dahua-access-control-app-zkwoc8`, click
   **Code → Download ZIP**, and extract it, e.g. to `C:\AttendOps`. (Or `git clone` it.)
3. Double-click **`install.cmd`** in that folder. It will:
   - create `.env` with new random secrets,
   - build and start the app (the first run downloads images; allow several minutes),
   - ask for the email and password of the first admin account,
   - open http://127.0.0.1:8080 in your browser.

### VirtualBox VM (Ubuntu Server, bridged to the LAN)

Step-by-step guide: [deploy/VIRTUALBOX.md](deploy/VIRTUALBOX.md). In short, inside the VM:

```bash
git clone -b claude/dahua-access-control-app-zkwoc8 https://github.com/crizk-cloud/AttendOps.git
cd AttendOps && ./deploy/setup-ubuntu-vm.sh
```

It installs Docker Engine, then AttendOps with `--lan`, and prints the address to open from your computer.

### macOS / Linux

Install Docker (Docker Desktop on macOS), get the folder as above, then in a terminal in that folder:

```bash
./install.sh
```

### Options (both installers)

| Windows | macOS/Linux | Effect |
|---|---|---|
| `-Port 9000` | `--port 9000` | Use another port (default 8080) |
| `-Lan` | `--lan` | Let other computers on the network open the app at `http://<this-computer's-IP>:8080` (Windows Firewall may ask) |
| `-AdminEmail you@x.lb` | `--admin-email you@x.lb` | Skip the email prompt |
| `-Reset` | `--reset` | **Delete all AttendOps data** and start over (asks you to type DELETE) |

On Windows pass options like this: `powershell -ExecutionPolicy Bypass -File .\install.ps1 -Lan`.
`-Port`/`-Lan` only apply when `.env` is first created; later, edit `APP_PORT`/`APP_BIND` in `.env` and run the
installer again.

Running the installer again is safe. It keeps `.env` and all data, rebuilds with the current code, and restarts.
That is also how you **update**: replace the folder's contents with the new version (keep `.env`), then run it.

### Day-to-day (in the project folder)

```
docker compose stop            # stop AttendOps
docker compose start           # start it again
docker compose ps              # status
docker compose logs -f app     # live log
```

### Back up

`.env` holds `DEVICE_CREDENTIALS_KEY`. Without it the saved device passwords cannot be decrypted. Keep a copy of
`.env` somewhere safe, together with database backups:

```
docker compose exec -T db pg_dump -U attendops -Fc -f /tmp/attendops.dump attendops
docker compose cp db:/tmp/attendops.dump ./attendops-backup.dump
```

Restore into a running install (replaces current data):

```
docker compose cp ./attendops-backup.dump db:/tmp/attendops.dump
docker compose exec -T db pg_restore -U attendops -d attendops --clean --if-exists /tmp/attendops.dump
```

If `.env` is lost but the data still exists, the installer refuses to create new secrets (they would not match the
database). Put the backed-up `.env` back first.

### Networking notes

- The computer must reach every device subnet (e.g. `172.22.76.x` and `172.23.5.x`). Test it with
  `ping 172.22.76.12` from that computer.
- Docker normally gives its internal networks `172.17–172.31.x.x` addresses, which overlap the devices.
  AttendOps pins its own network to `10.254.254.0/24` (`DOCKER_SUBNET` in `.env`) so the devices stay reachable.
  If your LAN uses `10.254.254.x`, choose another range. Also avoid running other Docker projects whose
  networks use `172.22.x` / `172.23.x`.
- The app uses plain HTTP. Keep `APP_BIND=127.0.0.1` (the default) unless other computers need access. If you
  later put it behind HTTPS, set `COOKIE_SECURE=true`.

## Development setup

For working on the code (hot-reloading frontend, database port exposed on `127.0.0.1:5432`):

```bash
cp .env.example .env    # fill in POSTGRES_PASSWORD, JWT_SECRET, DEVICE_CREDENTIALS_KEY
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml exec backend python -m app.cli create-admin --email you@example.com
```

Frontend: http://localhost:5173 · API docs: http://localhost:8000/api/docs

### Without Docker

You need Python 3.12, Node 22 and a PostgreSQL 16 database.

```bash
# Backend
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env        # set DATABASE_URL, JWT_SECRET, DEVICE_CREDENTIALS_KEY
python -m app.cli generate-keys
alembic upgrade head
python -m app.cli create-admin --email you@example.com
uvicorn app.main:app --reload --port 8000

# Frontend (second terminal): Vite proxies /api to http://localhost:8000
cd frontend
npm install
npm run dev
```

## Environment variables

Read by the backend from the environment or `backend/.env`. Docker compose reads the repo-root `.env`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | outside docker | `postgresql+psycopg://attendops:attendops@localhost:5432/attendops` | SQLAlchemy URL (compose builds it from `POSTGRES_*`) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | docker | `attendops` / `attendops` / — | Database container settings |
| `JWT_SECRET` | yes | — | Signs tokens; at least 32 chars. Changing it signs everyone out |
| `DEVICE_CREDENTIALS_KEY` | yes | — | Fernet key encrypting device passwords at rest. **Back it up**: if lost, device passwords must be re-entered |
| `ENVIRONMENT` | no | `development` | `production` hides the API docs (the installed app uses `production`) |
| `COOKIE_SECURE` | no | `false` | Send the login cookie over HTTPS only. Turn on only when serving over HTTPS |
| `APP_PORT` | installer | `8080` | Port of the installed app |
| `APP_BIND` | installer | `127.0.0.1` | `127.0.0.1` = this computer only; `0.0.0.0` = also other computers on the LAN |
| `DOCKER_SUBNET` | installer | `10.254.254.0/24` | Docker network for the app; must not overlap the device subnets or your LAN |
| `STATIC_DIR` | image | `/app/static` | Built frontend served by the backend (set inside the image) |
| `APP_TIMEZONE` | no | `Asia/Beirut` | Display time zone (storage is always UTC) |
| `ACCESS_TOKEN_MINUTES` | no | `15` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | no | `7` | Refresh token lifetime |
| `DEVICE_CONNECT_TIMEOUT` | no | `3` | Seconds to wait for a device to accept a connection |
| `DEVICE_READ_TIMEOUT` | no | `10` | Seconds to wait for a device's answer |
| `DEVICE_MAX_CONCURRENCY` | no | `4` | Max simultaneous device requests from the backend (the terminals and the existing logger share them) |
| `SYNC_INITIAL_DAYS` | no | `30` | How far back a device's first sync goes (older ranges: use *Re-import*) |
| `SYNC_OVERLAP_MINUTES` | no | `60` | Each sync re-reads this much before the last sync point, and this much past "now" |
| `SYNC_CHUNK_HOURS` | no | `24` | Size of each committed import chunk |
| `LOG_LEVEL` | no | `INFO` | Backend log level |
| `CORS_ORIGINS` | no | `["http://localhost:5173"]` | Only needed if the browser calls the API cross-origin |

The backend refuses to start if `JWT_SECRET` is too short, `DEVICE_CREDENTIALS_KEY` isn't a valid Fernet key,
or `APP_TIMEZONE` is unknown.

## Devices

Admins register devices under **Manage devices**, either one at a time (with a *Test connection* button) or many
at once by pasting one line per device:

```
172.22.76.12, Main entrance                         # uses the shared login entered below the box
172.23.5.202, Annex gate, admin, its-own-password   # per-device login
```

Each device keeps its own username and password, encrypted at rest. A password is never shown again; leave the
field empty when editing to keep it.

When a device is added (and whenever its reported model or firmware changes), AttendOps:

1. **Identifies it** via `magicBox.cgi` (`getDeviceType`, `getSoftwareVersion`, `getSerialNo`).
2. **Probes capabilities with read-only requests only**: history (`recordFinder` with a 1-hour window, `count=1`),
   users/cards (`AccessUser`/`AccessCard` `startFind`, always closed with `stopFind`) and the legacy card table.
   Each operation is stored per device as `verified`, `unsupported` or `unverified`. Write operations are never
   probed automatically.

Device status: `online` (answered an authenticated request), `offline` (no network answer), `auth_failed`
(credentials rejected), `error` (unexpected answer), `unknown` (not checked yet). *Last successful contact* is the
last time the device answered an authenticated request. Operators can run *Check* / *Check all devices*; checks
run in parallel (bounded by `DEVICE_MAX_CONCURRENCY`) and one failing device never blocks the others.
Periodic automatic checks come with the scheduler in Phase 4.

**Verification status.** The integration code was tested against fakes only (`backend/tests/fake_dahua.py`,
`mock_device/`). The response formats for `magicBox.cgi`, `AccessUser.cgi` and `AccessCard.cgi` follow Dahua's
documentation and have **not yet been confirmed on the real devices**. Run `tools/probe_device.py` on the LAN to
confirm them.

**Networking.** The backend container reaches the devices through Docker's default NAT, so the host must be able
to reach every device subnet (e.g. 172.22.76.0/24 and 172.23.5.0/24).

## Access history sync

Operators start a sync from the dashboard (**Sync all logs**) or a device page (**Sync now**, or **Re-import** a
date range). Phase 4 adds the automatic schedule.

How it stays correct:

- **Nothing is dropped at the 1024 cap.** Each window is queried with Unix-integer `StartTime`/`EndTime`. If the
  answer reaches 1024 records, the window is split in half and both halves are queried, recursively. The halves
  overlap by one second, so no boundary record is missed whatever the device's inclusive/exclusive behaviour,
  and duplicates are removed by `RecNo`. If more than 1024 records share one second, the run fails with an
  explicit error instead of silently losing data.
- **Idempotent.** Rows are upserted on `(device_id, rec_no)`. Re-running any sync or range never duplicates.
- **Incremental and resumable.** Each device keeps `synced_until`. It only advances after a chunk (24 h) has been
  fully imported and committed. The next sync starts at `synced_until − 60 min`. If a device drops off midway,
  the run is marked `partial`, completed chunks are kept, and the next sync resumes from the last good point.
- **One sync per device at a time.** A PostgreSQL advisory lock protects each device, also across processes.
- **Isolated.** Devices sync in parallel (bounded by `DEVICE_MAX_CONCURRENCY`), each with its own DB session.
  One failing device never blocks the others.
- **Device resets are surfaced.** If a device returns a `RecNo` that is already stored with a different time
  (e.g. after a factory reset), that record is not imported. The run is marked `partial` with a warning, never
  silently skipped.
- **PINs are never stored.** Any non-empty `Password` field in a device record is replaced with `[redacted]`.
- A device that has imported logs cannot be deleted (disable it instead), so history is never lost by accident.

Every attempt is recorded in `sync_runs`: window, records found / new / already present, number of device
queries, warnings and errors.

### Time handling

`CreateTime` is stored as a true Unix epoch (UTC) in `access_logs.event_time` and displayed in Asia/Beirut.
Date filters on the logs page are Beirut calendar days. `dahua_attendance_logger.py` interprets `CreateTime` the
same way. This has **not yet been confirmed against a real device's clock**: `tools/probe_device.py` reports it.
The raw `CreateTime` is kept in `raw_payload`, so a correction would be possible without re-reading devices.

## Access logs

The **Access logs** page (all roles) lists imported records, newest first, with:
- date range (Beirut days; quick buttons for today / 7 / 30 days)
- device
- search: name contains, or exact card number or user ID
- type (Entry/Exit) and result (granted = `Status=1`, denied = anything else)
- page size and sort order

Filters are kept in the URL, so a filtered view can be bookmarked or shared. Clicking a row shows the raw device
record. Records are read-only: they are data reported by the devices.

## Security design (so far)

- **Tokens.** The access token (15 min) is kept only in browser memory. The refresh token is an httpOnly,
  SameSite=Strict cookie limited to `/api/auth`. Refresh tokens rotate on every use. Re-using an old one
  revokes that whole login session (theft detection).
- **Accounts.** The role is re-read from the database on every request, so demoting or disabling an
  account takes effect immediately. Disabling an account or resetting its password also ends its sessions.
  The last active admin cannot be demoted or disabled.
- **Login errors.** A wrong password and an unknown email give the same response and take the same time.
- **Device passwords** (from Phase 2) are Fernet-encrypted in the database. They are never returned by the
  API, never logged, and never sent to the frontend.
- **Auth providers.** Login goes through an `AuthProvider` interface (`backend/app/auth/providers/`), so
  Google sign-in can be added as another provider without changing tokens or roles.

## Tests

```bash
cd backend
# Uses a real PostgreSQL test database; it is wiped and re-migrated on every run.
export TEST_DATABASE_URL=postgresql+psycopg://attendops:attendops@localhost:5432/attendops_test
pytest
ruff check app tests

cd ../frontend && npm run build && npm run lint
```

## Layout

```
backend/app/
  config.py         settings from env
  db.py             engine, session, naming conventions
  models/           SQLAlchemy models
  schemas/          API request/response models
  api/              routers (auth, app-users, ...)
  auth/             passwords, JWT, role dependencies, providers/
  security/crypto.py  Fernet encryption for device credentials
  devices/          device integration layer: base.py (interface), registry.py, dahua/ (client, parsing, driver)
  services/         devices.py (checks), sync.py (history import); later pending changes, analytics
backend/alembic/    migrations
frontend/src/       api client, auth context, pages
deploy/                 VirtualBox/Ubuntu VM guide and setup script
tools/probe_device.py   read-only probe to run on the LAN against one device
mock_device/            FAKE devices for local development only (never imported by the app)
```

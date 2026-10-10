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
| 3 | Historical log sync, logs table | next |
| 4–7 | Scheduler, users/cards, analytics, live feed, audit, deployment | planned |

## Run locally with Docker (recommended)

```bash
cp .env.example .env
# Fill in POSTGRES_PASSWORD, JWT_SECRET and DEVICE_CREDENTIALS_KEY. To generate the two secrets:
echo "JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')"
echo "DEVICE_CREDENTIALS_KEY=$(openssl rand -base64 32 | tr '+/' '-_')"

docker compose up -d --build
# Create the first admin account (prompts for a password, min. 10 characters):
docker compose exec backend python -m app.cli create-admin --email you@example.com
```

Open http://localhost:5173 and sign in. API docs (development only): http://localhost:8000/api/docs.

The backend applies database migrations automatically on start.
The containers must run on a machine on the device LAN, because the backend talks to the devices directly
(Phase 2 onward).

## Run without Docker

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
| `ENVIRONMENT` | no | `development` | `production` turns on secure cookies and hides API docs |
| `APP_TIMEZONE` | no | `Asia/Beirut` | Display time zone (storage is always UTC) |
| `ACCESS_TOKEN_MINUTES` | no | `15` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | no | `7` | Refresh token lifetime |
| `DEVICE_CONNECT_TIMEOUT` | no | `3` | Seconds to wait for a device to accept a connection |
| `DEVICE_READ_TIMEOUT` | no | `10` | Seconds to wait for a device's answer |
| `DEVICE_MAX_CONCURRENCY` | no | `4` | Max simultaneous device requests from the backend (the terminals and the existing logger share them) |
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
  services/         sync, pending changes, analytics (Phase 3+)
backend/alembic/    migrations
frontend/src/       api client, auth context, pages
tools/probe_device.py   read-only probe to run on the LAN against one device
mock_device/            FAKE devices for local development only (never imported by the app)
```

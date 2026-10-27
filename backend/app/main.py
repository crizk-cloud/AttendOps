import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import app_users, auth, devices, logs, sync
from app.config import get_settings
from app.db import get_engine


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(title="AttendOps", version="0.1.0",
                  docs_url=None if settings.is_production else "/api/docs",
                  openapi_url=None if settings.is_production else "/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    app.include_router(auth.router)
    app.include_router(app_users.router)
    app.include_router(devices.router)
    app.include_router(sync.router)
    app.include_router(logs.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        db_ok = True
        try:
            with get_engine().connect() as conn:
                conn.execute(text("select 1"))
        except Exception:  # noqa: BLE001 - health check reports, never raises
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": db_ok, "timezone": settings.app_timezone}

    if settings.static_dir:
        _mount_frontend(app, Path(settings.static_dir))
    return app


def _mount_frontend(app: FastAPI, root: Path) -> None:
    """Serve the built React app; unknown non-API paths return index.html (client-side routing)."""
    index = root / "index.html"
    if not index.is_file():
        logging.getLogger(__name__).warning("STATIC_DIR %s has no index.html; frontend not served", root)
        return
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")
    root_resolved = root.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root_resolved):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()

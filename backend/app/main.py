from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import app_users, auth
from app.config import get_settings
from app.db import get_engine


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AttendOps", version="0.1.0",
                  docs_url=None if settings.is_production else "/api/docs",
                  openapi_url=None if settings.is_production else "/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["Authorization", "Content-Type"])
    app.include_router(auth.router)
    app.include_router(app_users.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        db_ok = True
        try:
            with get_engine().connect() as conn:
                conn.execute(text("select 1"))
        except Exception:  # noqa: BLE001 - health check reports, never raises
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": db_ok, "timezone": settings.app_timezone}

    return app


app = create_app()

# Single image for installing AttendOps: the FastAPI backend also serves the built React frontend.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 STATIC_DIR=/app/static
WORKDIR /app

# Dependencies first (cached between code changes).
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install -e . && rm -rf app

COPY backend/ ./
COPY --from=web /web/dist ./static
RUN useradd --system --uid 1000 attendops && chown -R attendops /app
USER attendops

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]

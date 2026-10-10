FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install -e . && rm -rf app

COPY . .
RUN useradd --system --uid 1000 attendops && chown -R attendops /app
USER attendops

EXPOSE 8000
# Apply migrations, then serve. One worker is enough for ~23 devices; scale later if needed.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

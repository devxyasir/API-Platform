# syntax=docker/dockerfile:1
# ---- Backend image: FastAPI gateway on Python 3.14 -------------------------
FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is only needed for the container HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching. We add the Postgres
# drivers (async for the app, sync psycopg2 for Alembic) on top of the core
# requirements so the same image works with the Postgres compose service.
# tiktoken is intentionally omitted — the app falls back to a heuristic
# tokenizer, keeping this build wheel-only (no compiler toolchain required).
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install "asyncpg>=0.30.0" "psycopg2-binary>=2.9.10"

COPY . .

# Run as an unprivileged user.
RUN chmod +x docker-entrypoint.sh \
    && adduser --disabled-password --gecos "" appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

# The entrypoint applies migrations (alembic upgrade head) before starting.
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

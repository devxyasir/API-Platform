#!/usr/bin/env sh
# Container entrypoint: bring the schema up to date, then run the given command.
#
# The container manages its schema with Alembic (compose sets
# AUTO_CREATE_TABLES=false), so this is the single source of truth for DDL and
# is safe to run on every start — `upgrade head` is a no-op once current.
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Starting: $*"
exec "$@"

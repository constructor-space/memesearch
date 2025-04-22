#!/usr/bin/env bash
set -e
if [ ! -f migrations_applied ]; then
  alembic upgrade head
  touch migrations_applied
fi

exec python -m app

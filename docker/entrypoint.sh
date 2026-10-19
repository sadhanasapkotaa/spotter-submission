#!/bin/sh
set -e

# Auto-migrate only where explicitly enabled (local/dev/staging).
# In prod run migrations as a separate release step: `make migrate ENV=prod`.
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
  python manage.py migrate --noinput
fi

exec "$@"

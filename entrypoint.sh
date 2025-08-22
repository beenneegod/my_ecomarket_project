#!/bin/bash
set -euo pipefail

# Optional controls (override via env):
# RUN_MIGRATIONS=1|0, RUN_COMPILEMESSAGES=1|0
RUN_MIGRATIONS=${RUN_MIGRATIONS:-1}
RUN_COMPILEMESSAGES=${RUN_COMPILEMESSAGES:-1}

ts() { date +%s; }
start_all=$(ts)

if [ "$RUN_MIGRATIONS" = "1" ]; then
	echo "Applying database migrations..."
	t0=$(ts)
	python manage.py migrate --noinput
	echo "Migrations done in $(( $(ts) - t0 ))s"
else
	echo "Skipping database migrations (RUN_MIGRATIONS=$RUN_MIGRATIONS)"
fi

if [ "$RUN_COMPILEMESSAGES" = "1" ]; then
	echo "Compiling translations..."
	t1=$(ts)
	python manage.py compilemessages || echo "WARNING: compilemessages failed (is gettext installed?). Continuing..."
	echo "Translations compiled in $(( $(ts) - t1 ))s"
else
	echo "Skipping compilemessages (RUN_COMPILEMESSAGES=$RUN_COMPILEMESSAGES)"
fi

echo "Startup preflight completed in $(( $(ts) - start_all ))s"

# Запускаем веб-сервер
echo "Starting server..."
daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application
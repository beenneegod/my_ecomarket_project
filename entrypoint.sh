#!/bin/bash

# Применяем миграции базы данных
echo "Applying database migrations..."
python manage.py migrate --noinput

# Запускаем веб-сервер
echo "Starting server..."
daphne -b 0.0.0.0 -p $PORT config.asgi:application
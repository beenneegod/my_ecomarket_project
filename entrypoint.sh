#!/bin/bash

# Применяем миграции базы данных
echo "Applying database migrations..."
python manage.py migrate --noinput

# Компилируем переводы (нужен установленный gettext/msgfmt)
echo "Compiling translations..."
python manage.py compilemessages || echo "WARNING: compilemessages failed (is gettext installed?). Continuing..."

# Запускаем веб-сервер
echo "Starting server..."
daphne -b 0.0.0.0 -p $PORT config.asgi:application
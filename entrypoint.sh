#!/bin/sh
mkdir -p /app/data
if [ ! -f /app/data/.secret_key ]; then
    python -c "import secrets; print(secrets.token_hex(50))" > /app/data/.secret_key
fi
export DJANGO_SECRET_KEY=$(cat /app/data/.secret_key)
exec "$@"

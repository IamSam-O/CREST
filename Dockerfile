FROM node:22-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --silent
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY config ./config
COPY accounts ./accounts
COPY exams ./exams
COPY multiplayer ./multiplayer
COPY adminui ./adminui
COPY templates ./templates
COPY manage.py ./
COPY --from=frontend-builder /public ./public

ENV DJANGO_SETTINGS_MODULE=config.settings
EXPOSE 3000

CMD ["sh", "-c", "mkdir -p /app/data && [ -f /app/data/.secret_key ] || openssl rand -base64 128 > /app/data/.secret_key && export DJANGO_SECRET_KEY=$(cat /app/data/.secret_key) && python manage.py migrate --noinput && python manage.py collectstatic --noinput && daphne -b 0.0.0.0 -p 3000 config.asgi:application"]

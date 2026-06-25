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
COPY public ./public
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENV DJANGO_SETTINGS_MODULE=config.settings
EXPOSE 3000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && daphne -b 0.0.0.0 -p 3000 config.asgi:application"]

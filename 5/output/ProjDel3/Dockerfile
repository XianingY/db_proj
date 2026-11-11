FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# psql / pg_isready are used by the entrypoint and the standalone SQL checks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies live in an image layer, so container restarts never reinstall.
COPY requirements.txt requirements-docs.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock

COPY . .

ENTRYPOINT ["sh", "scripts/docker-entrypoint.sh"]
CMD ["--web", "--port", "8000"]

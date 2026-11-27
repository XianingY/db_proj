#!/bin/sh
# Container entrypoint: wait for PostgreSQL, initialize once, then exec the app.
# Idempotent: an existing schema is never dropped, cleared, or re-seeded.
set -eu

: "${LAB_DSN:=host=db port=5432 dbname=research_lab user=lab_user password=local-demo-only-change-me}"
: "${LAB_SCHEMA:=research_lab_del3}"
export LAB_DSN LAB_SCHEMA

if ! printf '%s' "$LAB_SCHEMA" | grep -Eq '^[a-z][a-z0-9_]{0,62}$'; then
    printf '错误：非法 schema 名称 %s\n' "$LAB_SCHEMA" >&2
    exit 1
fi

tries=0
until psql -d "$LAB_DSN" -tAc 'SELECT 1' >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -gt 60 ]; then
        printf '错误：PostgreSQL 未就绪，已等待 %s 秒\n' "$tries" >&2
        exit 1
    fi
    sleep 1
done

EXISTS=$(psql -d "$LAB_DSN" -v schema="$LAB_SCHEMA" -tAc "SELECT 1 FROM pg_namespace WHERE nspname = :'schema'" | tr -d '[:space:]')
if [ "$EXISTS" != "1" ]; then
    printf '初始化 schema %s（已存在时不会覆盖）\n' "$LAB_SCHEMA"
    python app.py --init
fi

exec python app.py "$@"

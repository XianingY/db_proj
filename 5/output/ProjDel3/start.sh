#!/bin/sh
# Research Lab Manager - 唯一启动入口。Docker 与本机环境共用这套命令。
# Usage: sh start.sh [up|menu|demo|test|check|stop|help]
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

ACTION=${1:-up}
if [ "$#" -gt 0 ]; then shift; fi

LAB_RUNTIME=${LAB_RUNTIME:-auto}
VENV_PY="$ROOT/.venv/bin/python"
WEB_PORT=${WEB_PORT:-8000}

step() { printf '\n==> %s\n' "$1"; }
die()  { printf '\n错误：%s\n' "$1" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Research Lab Manager - 统一启动入口

  sh start.sh          一键启动：准备环境、初始化、启动课堂演示网页
  sh start.sh menu     进入中文三级终端菜单
  sh start.sh demo     运行十项只读报表
  sh start.sh test     运行全部自动化测试
  sh start.sh check    环境与数据自检
  sh start.sh fresh <schema>  初始化一个新的干净演示 schema（不覆盖默认库）
  sh start.sh stop     停止 Docker 服务（保留数据卷）
  sh start.sh help     显示本说明

运行时选择：
  auto（默认）        有可用的 Docker daemon 用容器，否则自动使用本机环境
  LAB_RUNTIME=docker  强制 Docker（需 Docker + Compose v2）
  LAB_RUNTIME=native  强制本机环境（Python 3.10+ / PostgreSQL 14+）
  WEB_PORT=8080       改变演示网页端口；也可复制 .env.example 为 .env
USAGE
}

docker_ok() {
    case "$LAB_RUNTIME" in
        docker) return 0 ;;
        native) return 1 ;;
    esac
    command -v docker >/dev/null 2>&1 || return 1
    docker compose version >/dev/null 2>&1 || return 1
    docker info >/dev/null 2>&1
}

native_ready() {
    [ -x "$VENV_PY" ] || return 1
    "$VENV_PY" -c 'from research_lab.db import connect, check_ready; c=connect(); check_ready(c); c.close()' >/dev/null 2>&1
}

ensure_native() {
    if native_ready; then
        printf '本机环境已就绪，跳过重复配置\n'
        return 0
    fi
    step '准备本机环境（首次运行或环境损坏时执行）'
    sh scripts/bootstrap.sh
}

docker_ready() {
    docker compose ps --status running --format '{{.Service}}' 2>/dev/null | grep -qx app || return 1
    docker compose exec -T app python -c 'from research_lab.db import connect, check_ready; c=connect(); check_ready(c); c.close()' >/dev/null 2>&1
}

ensure_docker() {
    case "$LAB_RUNTIME" in
        native) die 'LAB_RUNTIME=native 时不可用 Docker 子命令' ;;
    esac
    if ! docker_ok; then
        die 'Docker 不可用：请启动 Docker Desktop，或改用 LAB_RUNTIME=native'
    fi
    step '启动容器（依赖固化在镜像层，已有数据不会被覆盖）'
    # 镜像已存在时不再 --build：避免每次启动重建容器、打断正在运行的服务。
    # 源码或 Dockerfile 改动后手工执行 `docker compose up -d --build` 即可刷新。
    if [ -n "$(docker compose images -q app 2>/dev/null)" ]; then
        WEB_PORT="$WEB_PORT" docker compose up -d db app
    else
        WEB_PORT="$WEB_PORT" docker compose up -d --build db app
    fi
    tries=0
    until docker_ready; do
        tries=$((tries + 1))
        if [ "$tries" -gt 90 ]; then
            docker compose logs --tail=40 app >&2 || true
            die '容器启动超时'
        fi
        sleep 1
    done
}

case "$ACTION" in
    help|-h|--help)
        usage ;;
    stop)
        if docker_ok; then
            docker compose down
            printf '容器已停止；数据卷 lab_pg_data 保留，下次启动无需重新初始化。\n'
        else
            printf '本机模式的网页服务在前台运行，按 Ctrl+C 即可停止。\n'
        fi ;;
    up)
        if docker_ok; then
            ensure_docker
            printf '\n环境就绪：http://localhost:%s/\n' "$WEB_PORT"
            printf '停止：sh start.sh stop    终端菜单：sh start.sh menu\n'
        else
            ensure_native
            step '启动课堂演示网页（Ctrl+C 停止）'
            exec "$VENV_PY" app.py --web --port "$WEB_PORT"
        fi ;;
    menu)
        if docker_ok; then
            ensure_docker
            exec docker compose exec app python app.py
        else
            ensure_native
            exec "$VENV_PY" app.py
        fi ;;
    demo)
        if docker_ok; then
            ensure_docker
            exec docker compose exec -T app python app.py --demo
        else
            ensure_native
            exec "$VENV_PY" app.py --demo
        fi ;;
    test)
        if docker_ok; then
            ensure_docker
            exec docker compose exec -T app python -m unittest discover -s tests -v
        else
            ensure_native
            exec "$VENV_PY" -m unittest discover -s tests -v
        fi ;;
    check)
        if docker_ok; then
            ensure_docker
            docker compose exec -T app python -m unittest discover -s tests
            docker compose exec -T app python app.py --demo
            docker compose exec -T app python docs/check_demo_data.py
        else
            sh scripts/bootstrap.sh --check
            "$VENV_PY" docs/check_demo_data.py
        fi ;;
    fresh)
        TARGET_SCHEMA=${1:-}
        [ -n "$TARGET_SCHEMA" ] || die '请指定新 schema 名称，例如：sh start.sh fresh research_lab_demo2'
        printf '%s' "$TARGET_SCHEMA" | grep -Eq '^[a-z][a-z0-9_]{0,62}$' || \
            die 'schema 必须由小写英文、数字和下划线组成，以字母开头（不超过 63 字符）'
        if docker_ok; then
            ensure_docker
            docker compose exec -T app python app.py --schema "$TARGET_SCHEMA" --init
        else
            ensure_native
            "$VENV_PY" app.py --schema "$TARGET_SCHEMA" --init
        fi
        printf '干净实例已就绪：LAB_SCHEMA=%s sh start.sh （或 sh start.sh menu）\n' "$TARGET_SCHEMA" ;;
    *)
        die "未知子命令：$ACTION（用 sh start.sh help 查看用法）" ;;
esac

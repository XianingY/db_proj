#!/bin/sh
# 一键准备 Research Lab Manager (Deliverable 3) 的运行环境。
#
#   sh scripts/bootstrap.sh            # 建环境 + 初始化演示 schema + 自检
#   sh scripts/bootstrap.sh --check    # 只自检，不安装、不初始化
#   LAB_SCHEMA=other sh scripts/bootstrap.sh
#
# 幂等：可反复执行。已存在的 schema 一律不覆盖、不清空（app.py --init 本身也会拒绝）。
set -eu

cd "$(dirname "$0")/.."
ROOT=$(pwd)
SCHEMA=${LAB_SCHEMA:-research_lab_del3}
DSN=${LAB_DSN:-dbname=postgres}
CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then CHECK_ONLY=1; fi

step() { printf '\n==> %s\n' "$1"; }
die()  { printf '\n错误：%s\n' "$1" >&2; exit 1; }

add_pg_bin() {
    for bindir in /opt/homebrew/opt/postgresql@18/bin /opt/homebrew/opt/postgresql@17/bin \
                  /usr/local/opt/postgresql@18/bin /usr/local/opt/postgresql@17/bin \
                  /opt/homebrew/opt/libpq/bin /usr/lib/postgresql/18/bin \
                  /usr/lib/postgresql/17/bin /usr/pgsql-18/bin; do
        if [ -d "$bindir" ]; then
            case ":$PATH:" in
                *":$bindir:"*) ;;
                *) PATH="$bindir:$PATH" ;;
            esac
        fi
    done
    export PATH
}

# ---------------------------------------------------------------- Python 环境
# 本机可能出现「python3 在、但 python3 -m venv 失败」的情况（例如 Homebrew
# Python 的 pip 因 libexpat 符号缺失而无法运行）。因此逐个候选在临时目录里
# 实际试跑，失败就退回 uv 托管的 CPython，绝不假设第一个 python3 可用。
VENV_PY="$ROOT/.venv/bin/python"

python_works() {
    if [ -x "$VENV_PY" ]; then
        "$VENV_PY" -c 'import sys, psycopg; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1
        return $?
    fi
    return 1
}

if python_works; then
    step "复用已存在的 .venv（$("$VENV_PY" -V 2>&1)）"
elif [ "$CHECK_ONLY" = 1 ]; then
    die ".venv 不可用；去掉 --check 重新运行以创建环境"
else
    step "准备 Python 虚拟环境"
    BASE_PY=""
    PROBE=$(mktemp -d)
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 /usr/bin/python3; do
        if ! command -v "$candidate" >/dev/null 2>&1; then continue; fi
        if ! "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
            continue
        fi
        if "$candidate" -m venv "$PROBE/v" >/dev/null 2>&1; then
            BASE_PY=$candidate
            break
        fi
    done
    if [ -z "$BASE_PY" ]; then
        if ! command -v uv >/dev/null 2>&1; then
            die "找不到可用的 Python 3.10+（或 python3 -m venv 均失败），且未安装 uv：https://docs.astral.sh/uv/"
        fi
        printf '没有可用的 python3 -m venv，改用 uv 创建 CPython 3.13 环境\n'
        uv venv --python 3.13 "$ROOT/.venv" >/dev/null
    else
        printf '使用 %s 创建 .venv\n' "$BASE_PY"
        "$BASE_PY" -m venv "$ROOT/.venv"
    fi
    if command -v uv >/dev/null 2>&1; then
        uv pip install --python "$VENV_PY" -r requirements.txt -r requirements-docs.txt
    else
        "$VENV_PY" -m pip install --quiet --upgrade pip
        "$VENV_PY" -m pip install --quiet -r requirements.txt -r requirements-docs.txt
    fi
    if ! python_works; then die "依赖安装后仍无法 import psycopg"; fi
fi

# ---------------------------------------------------------------- PostgreSQL
add_pg_bin

step "检查 PostgreSQL"
if ! command -v psql >/dev/null 2>&1; then
    if [ "$CHECK_ONLY" = 1 ]; then die "找不到 psql；请安装 PostgreSQL 14+ 后重试"; fi
    if ! command -v brew >/dev/null 2>&1; then
        die "找不到 psql，也没有 Homebrew 可自动安装；请手动安装 PostgreSQL 14+"
    fi
    printf '未检测到 PostgreSQL，使用 Homebrew 安装 postgresql@18\n'
    brew install postgresql@18
    add_pg_bin
fi

if ! pg_isready -q >/dev/null 2>&1; then
    if [ "$CHECK_ONLY" = 1 ]; then die "PostgreSQL 未在监听；先启动服务再自检"; fi
    if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q postgresql; then
        printf '启动 PostgreSQL 服务\n'
        brew services start postgresql@18 >/dev/null 2>&1 || brew services start postgresql@17 >/dev/null
    else
        die "PostgreSQL 未在监听，且无法自动启动；请手动启动后重试"
    fi
    tries=0
    until pg_isready -q >/dev/null 2>&1; do
        tries=$((tries + 1))
        if [ "$tries" -gt 30 ]; then die "PostgreSQL 启动超时"; fi
        sleep 1
    done
fi
printf 'PostgreSQL 就绪：%s\n' "$(psql -d "$DSN" -tAc 'SHOW server_version' 2>/dev/null || echo '未知版本')"

# -------------------------------------------------------------------- schema
step "检查 schema $SCHEMA"
EXISTS=$(psql -d "$DSN" -tAc "SELECT count(*) FROM pg_namespace WHERE nspname='$SCHEMA'" 2>/dev/null || echo 0)
if [ "$EXISTS" = "1" ]; then
    printf 'schema 已存在，按设计不覆盖、不重新导入\n'
elif [ "$CHECK_ONLY" = 1 ]; then
    die "schema $SCHEMA 不存在；去掉 --check 重新运行以初始化"
else
    "$VENV_PY" app.py --schema "$SCHEMA" --init
fi

# ---------------------------------------------------------------------- 自检
step "自检：单元测试 + 十项只读报表"
if ! "$VENV_PY" -m unittest discover -s tests > /tmp/lab_bootstrap_tests.txt 2>&1; then
    tail -30 /tmp/lab_bootstrap_tests.txt
    die "单元测试失败，详见 /tmp/lab_bootstrap_tests.txt"
fi
tail -4 /tmp/lab_bootstrap_tests.txt
if ! "$VENV_PY" app.py --schema "$SCHEMA" --demo > /tmp/lab_bootstrap_demo.txt 2>&1; then
    tail -20 /tmp/lab_bootstrap_demo.txt
    die "只读演示失败"
fi
printf '只读演示退出码 0，输出 %s 行（/tmp/lab_bootstrap_demo.txt）\n' \
    "$(wc -l < /tmp/lab_bootstrap_demo.txt | tr -d ' ')"

cat <<DONE

环境就绪。接下来：
  cd $ROOT
  .venv/bin/python app.py --schema $SCHEMA          # 中文交互菜单
  .venv/bin/python app.py --schema $SCHEMA --demo   # 只看十项报表
  source .venv/bin/activate                         # 或先激活再直接 python app.py
DONE

#!/usr/bin/env python3
"""Entry point: python app.py --init / python app.py / python app.py --demo."""
import argparse
import os
import sys

try:
    import psycopg
    from research_lab.cli import Terminal, demo
    from research_lab.db import DEFAULT_SCHEMA, check_ready, connect, initialize
except ImportError as error:
    print(f'依赖缺失：{error}。先运行 python -m pip install -r requirements.txt',file=sys.stderr)
    raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description='科研实验室管理系统：中文菜单 / PostgreSQL')
    parser.add_argument('--dsn',default=None,help='连接串；也可用 LAB_DSN/PGHOST 等环境变量')
    parser.add_argument('--schema',default=os.environ.get('LAB_SCHEMA',DEFAULT_SCHEMA),
                        help='专用 schema，不复用 public；默认 research_lab_del3')
    parser.add_argument('--init',action='store_true',help='只创建不存在的 schema 并导入全部样例，然后退出')
    parser.add_argument('--demo',action='store_true',help='运行全部十项只读报表然后退出')
    args = parser.parse_args()
    try:
        with connect(args.dsn,args.schema) as conn:
            if args.init:
                initialize(conn,args.schema)
                print(f'初始化成功：schema={args.schema}；原有 schema/业务数据未覆盖。')
                if not args.demo:
                    return 0
            check_ready(conn)
            if args.demo:
                demo(conn)
            else:
                Terminal(conn).run()
        return 0
    except (EOFError,KeyboardInterrupt):
        print('\n已退出；未提交的操作不会保存。')
        return 0
    except (ValueError,psycopg.Error) as error:
        print(f'启动失败：{error}',file=sys.stderr)
        print('请检查 PostgreSQL 是否启动、连接权限与 schema；未建实例时先用 --init。',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())

"""Connection and one-time, non-destructive initialization."""
import os
import re
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = 'research_lab_del3'


def connect(dsn=None, schema=None):
    schema = schema or os.environ.get('LAB_SCHEMA', DEFAULT_SCHEMA)
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        raise ValueError('schema 必须由小写英文、数字和下划线组成，以字母开头')
    conn = psycopg.connect(dsn or os.environ.get('LAB_DSN', 'dbname=postgres'),
                           autocommit=True, row_factory=dict_row)
    conn.execute("SET TIME ZONE 'Asia/Shanghai'")
    conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
    return conn


def initialize(conn, schema):
    """Only create an absent named schema, never reset existing data."""
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        raise ValueError('非法 schema 名称')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(1717, 3)')
        exists = conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone()
        if exists:
            raise ValueError(f'schema {schema} 已存在，初始化不会覆盖；请直接启动或换一个新名称')
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        conn.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
        for name in ['01_create_tables.sql', '02_integrity.sql', '03_sample_data.sql']:
            source = (ROOT / 'SQL' / name).read_text(encoding='utf-8')
            # The standalone seed is transactional; run inside this one outer transaction.
            if name == '03_sample_data.sql':
                source = re.sub(r'^\s*(BEGIN|COMMIT)\s*;\s*$', '', source,
                                flags=re.MULTILINE | re.IGNORECASE)
            conn.execute(source)
        conn.execute('SELECT lab_assert_integrity()')
        conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
    conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))


def check_ready(conn):
    if conn.execute("SELECT to_regclass('lab_member') AS name").fetchone()['name'] is None:
        raise ValueError('数据库尚未初始化，请先运行 python app.py --init')

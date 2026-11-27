"""Local-only JSON API plus static frontend for the classroom demonstration.

The browser talks to exactly the same business layer as the terminal:
LabService for writes (same transactions, rollback rules and Chinese error
messages) and run_report for the ten read-only reports.  Nothing here adds a
second copy of the business rules.

This is a demonstration service, not a production one: it binds 127.0.0.1 by
default (LAB_WEB_HOST=0.0.0.0 only inside the container), has no authentication
and relies on the database triggers for integrity. Standard library only, so the
existing virtualenv is sufficient.
"""
import json
import os
import textwrap
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import psycopg
from psycopg import sql

from .cli import parse_value
from .db import DEFAULT_SCHEMA, connect
from .reports import REPORTS, run_report, run_report_all, run_report_filtered
from .service import LabService, SUBCLASSES, TABLES, format_db_error, table_counts

WEB_ROOT = Path(__file__).resolve().parents[1] / 'web'
MAX_REQUEST_BYTES = 1_000_000


class RequestError(ValueError):
    """带 HTTP 状态码的可预期客户端请求错误。"""
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

CONTENT_TYPES = {'.html': 'text/html; charset=utf-8',
                 '.css': 'text/css; charset=utf-8',
                 '.js': 'text/javascript; charset=utf-8',
                 '.svg': 'image/svg+xml',
                 '.json': 'application/json; charset=utf-8'}


def encode(value):
    """JSON-safe form that keeps money and timestamps exact, never float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return str(value)
    return value


def field_specs(table):
    """Split the 标签|类型|提示 field spec used by the terminal as well."""
    label, keys, fields = TABLES[table]
    specs = {}
    for key, description in fields.items():
        parts = description.split('|')
        specs[key] = {
            'label': parts[0],
            'kind': parts[1] if len(parts) > 1 and parts[1] else 'str',
            'hint': parts[2] if len(parts) > 2 else '',
        }
    return {'label': label, 'keys': list(keys), 'fields': specs}


def coerce(table, data):
    """Apply the terminal's typed parsing to JSON input from the browser."""
    if not isinstance(data, dict):
        raise ValueError(f'{table} 的字段数据必须是 JSON 对象')
    specs = field_specs(table)['fields']
    unknown = set(data) - set(specs)
    if unknown:
        raise ValueError(f'包含未知字段：{", ".join(sorted(unknown))}')
    result = {}
    for key, raw in data.items():
        kind = specs[key]['kind']
        if raw is None:
            if kind.endswith('?'):
                result[key] = None
            else:
                raise ValueError(f'{specs[key]["label"]} 不能为空')
            continue
        result[key] = parse_value(str(raw).strip(), kind)
    return result


def foreign_keys(conn):
    rows = conn.execute("""
        SELECT c.conname AS conname, cls.relname AS src, ref.relname AS dst,
               array_agg(a.attname ORDER BY x.n) AS cols
        FROM pg_constraint c
        JOIN pg_class cls ON cls.oid = c.conrelid
        JOIN pg_class ref ON ref.oid = c.confrelid
        JOIN pg_namespace n ON n.oid = cls.relnamespace
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS x(attnum, n)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
        WHERE n.nspname = current_schema() AND c.contype = 'f'
        GROUP BY c.conname, cls.relname, ref.relname
        ORDER BY c.conname
    """).fetchall()
    return [dict(row) for row in rows]


def unique_columns(conn):
    rows = conn.execute("""
        SELECT cls.relname AS table_name,
               array_agg(a.attname ORDER BY x.n) AS cols
        FROM pg_constraint c
        JOIN pg_class cls ON cls.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cls.relnamespace
        CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS x(attnum, n)
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
        WHERE n.nspname = current_schema() AND c.contype = 'u'
        GROUP BY cls.relname, c.conname
        ORDER BY cls.relname, c.conname
    """).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row['table_name'], []).extend(row['cols'])
    return result


_VERIFICATION_CACHE = {'key': None, 'value': {}}


def verification_payload():
    """Cache the static evidence file by (mtime_ns, size); counts remain live.

    Concurrent requests may parse twice before the cache settles, which is
    harmless under CPython's GIL. Only this static file is cached: schema,
    table counts and foreign keys are queried on every request.
    """
    path = Path(__file__).resolve().parents[1] / 'evidence' / 'verification.json'
    try:
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        if _VERIFICATION_CACHE['key'] == key:
            return _VERIFICATION_CACHE['value']
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        # Verification numbers are presentation-only. A missing, unreadable or
        # partially written evidence file must not break the schema/report UI.
        return {}
    _VERIFICATION_CACHE['key'] = key
    _VERIFICATION_CACHE['value'] = value
    return value


def meta_payload(conn):
    verification = verification_payload()
    uniques = unique_columns(conn)
    tables = {}
    for name in TABLES:
        spec = field_specs(name)
        spec['uniques'] = uniques.get(name, [])
        tables[name] = spec
    counts = table_counts(conn)
    return {
        'schema': conn.execute('SELECT current_schema() AS s').fetchone()['s'],
        'server_version': conn.execute('SHOW server_version').fetchone()['server_version'],
        'tables': tables,
        'uniques': uniques,
        'counts': counts,
        'total_tuples': sum(counts.values()),
        'foreign_keys': foreign_keys(conn),
        'reports': [{'name': name, 'title': r['title'], 'params': list(r['params']),
                     'all': 'all_sql' in r, 'filter_param': r.get('filter_param'),
                     'sql': textwrap.dedent(r['sql']).strip(),
                     'all_sql': textwrap.dedent(r['all_sql']).strip() if 'all_sql' in r else None,
                     'filter_sql': textwrap.dedent(r['filter_sql']).strip() if 'filter_sql' in r else None}
                    for name, r in REPORTS.items()],
        'verification': verification,
    }


def make_handler(dsn, schema, quiet=False):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'ResearchLabD3'

        def log_message(self, fmt, *args):
            if not quiet:
                super().log_message(fmt, *args)

        # -- helpers ---------------------------------------------------------
        def _send(self, status, payload, content_type='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else json.dumps(
                payload, ensure_ascii=False, default=encode).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The browser closed the tab mid-response; nothing to report.
                pass

        def _json_body(self):
            content_type = self.headers.get('Content-Type', '').split(';')[0].strip().lower()
            if content_type != 'application/json':
                raise RequestError(415, '写请求必须使用 application/json')
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError as error:
                raise ValueError('Content-Length 必须是整数') from error
            if length < 0:
                raise ValueError('Content-Length 不能为负数')
            if length > MAX_REQUEST_BYTES:
                raise RequestError(413, f'请求体过大，上限为 {MAX_REQUEST_BYTES} 字节')
            raw = self.rfile.read(length) if length else b'{}'
            try:
                body = json.loads(raw.decode('utf-8') or '{}')
            except (UnicodeDecodeError, ValueError) as error:
                raise ValueError(f'请求体不是合法 JSON：{error}') from error
            if not isinstance(body, dict):
                raise ValueError('请求体必须是 JSON 对象，不能是数组或标量')
            return body

        def _check_origin(self):
            origin = self.headers.get('Origin')
            if not origin:
                return  # 终端、测试和非浏览器客户端不发送 Origin。
            port = self.server.server_address[1]
            allowed = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}
            # Docker 端口映射可能让浏览器 Origin 的端口与容器内监听端口不同。
            # 只接受显式配置的额外来源，默认仍严格限定本机。
            extra = os.environ.get('LAB_WEB_ALLOWED_ORIGINS', '')
            allowed.update(item.strip().rstrip('/') for item in extra.split(',') if item.strip())
            if origin.rstrip('/') not in allowed:
                raise RequestError(403, 'Origin 不是本机演示页面，拒绝写入')

        def _conn(self):
            conn = getattr(self, '_request_conn', None)
            if conn is None or conn.closed:
                conn = connect(dsn, schema)
                self._request_conn = conn
            return conn

        def handle_one_request(self):
            # ThreadingHTTPServer 的线程生命周期不等于请求生命周期；连接必须
            # 随本次 HTTP 请求关闭，不能遗留在 thread_local 或全局列表中。
            try:
                super().handle_one_request()
            finally:
                conn = getattr(self, '_request_conn', None)
                self._request_conn = None
                if conn is not None and not conn.closed:
                    conn.close()

        def _query(self):
            return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

        def _fail(self, error):
            """Single mapping from expected failures to JSON error responses.

            RequestError keeps its own HTTP status; database errors surface their
            primary message; other validation errors keep their original text.
            """
            if isinstance(error, RequestError):
                return self._send(error.status, {'ok': False, 'error': str(error)})
            if isinstance(error, psycopg.OperationalError):
                # Connection refused, server restart or timeout: not a client
                # input problem. Do not leak host/DSN details to the browser.
                return self._send(503, {'ok': False,
                                       'error': '数据库暂时不可用，请稍后重试'})
            detail = format_db_error(error)
            return self._send(400, {'ok': False, 'error': detail})

        # -- verbs -----------------------------------------------------------
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if not path.startswith('/api/'):
                return self._static(path)
            try:
                conn = self._conn()
                query = self._query()
                if path == '/api/health':
                    conn.execute('SELECT 1')
                    return self._send(200, {'ok': True, 'db': True})
                if path == '/api/meta':
                    return self._send(200, {'ok': True, 'meta': meta_payload(conn)})
                if path == '/api/rows':
                    table = query.get('table')
                    if table not in TABLES:
                        raise ValueError('未知的表名')
                    rows = LabService(conn).list_rows(
                        table, query.get('q') or None,
                        query.get('limit'), query.get('offset'))
                    return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
                if path == '/api/record':
                    table = query.get('table')
                    if table not in TABLES:
                        raise ValueError('未知的表名')
                    keys = field_specs(table)['keys']
                    key = [query.get(k, '') for k in keys]
                    record = LabService(conn).get_record(table, key)
                    if record is None:
                        raise ValueError('未找到记录')
                    return self._send(200, {'ok': True, 'record': dict(record)})
                if path == '/api/member_detail':
                    member_id = (query.get('member_id') or '').strip()
                    if not member_id:
                        raise ValueError('缺少参数 member_id')
                    detail = LabService(conn).member_detail(member_id)
                    return self._send(200, {'ok': True, 'detail': detail})
                if path == '/api/report':
                    name = query.get('name')
                    if name not in REPORTS:
                        raise ValueError('未知的报表')
                    filter_param = REPORTS[name].get('filter_param')
                    if filter_param and (query.get(filter_param) or '').strip():
                        rows = run_report_filtered(conn, name, query[filter_param].strip())
                        return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
                    if ((query.get('all') or '').lower() in ('1', 'true', 'yes')
                            and 'all_sql' in REPORTS[name]):
                        rows = run_report_all(conn, name)
                        return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
                    params = []
                    for key in REPORTS[name]['params']:
                        raw = query.get(key)
                        if raw is None:
                            raise ValueError(f'报表缺少参数 {key}')
                        params.append(parse_value(raw, 'date') if key == 'end_before' else raw)
                    rows = run_report(conn, name, tuple(params))
                    return self._send(200, {'ok': True, 'rows': [dict(r) for r in rows]})
                if path == '/api/explain':
                    name = query.get('name')
                    if name not in REPORTS:
                        raise ValueError('未知的报表')
                    r = REPORTS[name]
                    filter_param = r.get('filter_param')
                    if filter_param and (query.get(filter_param) or '').strip():
                        stmt, bind = r['filter_sql'], (query[filter_param].strip(),)
                    elif ((query.get('all') or '').lower() in ('1', 'true', 'yes')
                          and 'all_sql' in r):
                        stmt, bind = r['all_sql'], ()
                    else:
                        bind_list = []
                        for key in r['params']:
                            raw = query.get(key)
                            if raw is None:
                                raise ValueError(f'报表缺少参数 {key}')
                            bind_list.append(parse_value(raw, 'date') if key == 'end_before' else raw)
                        stmt, bind = r['sql'], tuple(bind_list)
                    plan_rows = conn.execute('EXPLAIN (FORMAT TEXT) ' + stmt, bind).fetchall()
                    plan = '\n'.join(row['QUERY PLAN'] for row in plan_rows)
                    return self._send(200, {'ok': True, 'plan': plan})
                if path == '/api/semantics_compare':
                    p001 = conn.execute("""
                        SELECT project_id, COALESCE(SUM(budget), 0) AS sum_budget,
                               COALESCE(SUM(DISTINCT budget), 0) AS sum_distinct
                        FROM research_grant WHERE project_id = 'P001' GROUP BY project_id
                    """).fetchone()
                    mentors = conn.execute("""
                        SELECT ms.mentor_id, m.full_name AS mentor_name,
                               COUNT(DISTINCT a.publication_id) AS distinct_pubs,
                               COUNT(a.publication_id) AS naive_rows
                        FROM mentorship ms
                        JOIN lab_member m ON m.member_id = ms.mentor_id
                        LEFT JOIN authorship a ON a.member_id = ms.mentee_id
                        GROUP BY ms.mentor_id, m.full_name
                        ORDER BY distinct_pubs DESC, ms.mentor_id ASC LIMIT 2
                    """).fetchall()
                    eq = conn.execute("""
                        SELECT COUNT(*) FILTER (WHERE p.status = 'active') AS active_rows,
                               COUNT(*) AS all_rows
                        FROM (SELECT DISTINCT member_id FROM equipment_usage
                              WHERE equipment_id = 'E001' AND ended_at IS NULL) cu
                        JOIN project_participation pp ON pp.member_id = cu.member_id
                        JOIN research_project p ON p.project_id = pp.project_id
                    """).fetchone()
                    return self._send(200, {'ok': True, 'compare': {
                        'p001_funding': dict(p001) if p001 else None,
                        'top_mentors': [dict(r) for r in mentors],
                        'e001_projects': dict(eq) if eq else None,
                    }})
                raise ValueError('未知接口')
            except (RequestError, ValueError, KeyError, psycopg.Error) as error:
                return self._fail(error)

        def do_POST(self):
            try:
                self._check_origin()
                body = self._json_body()
                conn = self._conn()
                path = urlparse(self.path).path
                if path == '/api/sandbox_check':
                    case = body.get('case')
                    if case not in ('delete_leader', 'fourth_user', 'truncate_authorship'):
                        raise ValueError('未知的沙箱演示用例')
                    conn.execute('BEGIN')
                    try:
                        if case == 'delete_leader':
                            LabService(conn).delete_record('lab_member', ('F001',))
                        elif case == 'fourth_user':
                            conn.execute("""
                                INSERT INTO equipment_usage
                                    (usage_id, member_id, equipment_id, device_number, started_at, ended_at, purpose)
                                VALUES ('SANDBOX_4TH', 'S003', 'E001', 'device01',
                                        date_trunc('second', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai') - INTERVAL '10 minutes',
                                        NULL, '课堂沙箱并发上限演示')
                            """)
                            conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
                        elif case == 'truncate_authorship':
                            conn.execute('TRUNCATE authorship')
                        return self._send(200, {'ok': True, 'blocked': False, 'case': case,
                                                'error': '未触发预期拦截（可能演示数据已被修改）'})
                    except (ValueError, psycopg.Error) as err:
                        return self._send(200, {
                            'ok': True,
                            'blocked': True,
                            'case': case,
                            'sqlstate': getattr(err, 'sqlstate', None) or 'APP',
                            'error': format_db_error(err),
                        })
                    finally:
                        conn.execute('ROLLBACK')
                if path == '/api/reassign_leader':
                    project_id = str(body.get('project_id') or '').strip()
                    new_leader_id = str(body.get('new_leader_id') or '').strip()
                    raw_hours = body.get('weekly_hours')
                    hours = parse_value(str(raw_hours).strip(), 'decimal') if raw_hours not in (None, '') else 0
                    LabService(conn).reassign_project_leader(project_id, new_leader_id, hours)
                    return self._send(200, {'ok': True, 'message': '已原子更换项目负责人'})
                table = body.get('table')
                if table not in TABLES:
                    raise ValueError('未知的表名')
                service = LabService(conn)
                if table == 'lab_member':
                    service.create_member(
                        coerce(table, body['member']),
                        coerce(_subclass_of(body['member']), body['subtype']),
                        [coerce('project_participation', p) for p in body.get('participations', [])])
                elif table == 'research_project':
                    service.create_project(
                        coerce(table, body['project']),
                        [coerce('project_participation', p) for p in body.get('participants', [])])
                elif table == 'equipment':
                    service.create_equipment(
                        coerce(table, body['equipment']),
                        [coerce('device', d) for d in body.get('devices', [])])
                elif table == 'publication':
                    service.create_publication(
                        coerce(table, body['publication']),
                        [str(a).strip() for a in body.get('author_ids', []) if str(a).strip()])
                else:
                    service.create_record(table, coerce(table, body['data']))
                return self._send(200, {'ok': True, 'message': '新增已提交'})
            except (RequestError, ValueError, KeyError, psycopg.Error) as error:
                return self._fail(error)

        def do_PATCH(self):
            try:
                self._check_origin()
                body = self._json_body()
                conn = self._conn()
                table = body.get('table')
                if table not in TABLES:
                    raise ValueError('未知的表名')
                specs = field_specs(table)
                raw_changes = body.get('changes')
                if raw_changes is None:
                    raw_changes = {}
                if not isinstance(raw_changes, dict):
                    raise ValueError('changes 必须是 JSON 对象')
                changes = {}
                for key, raw in raw_changes.items():
                    if key not in specs['fields']:
                        raise ValueError(f'包含未知字段：{key}')
                    kind = specs['fields'][key]['kind']
                    text = '' if raw is None else str(raw).strip()
                    if text == '':
                        continue  # 与终端一致：留空保留原值
                    if text.upper() == 'NULL':
                        if not kind.endswith('?'):
                            raise ValueError(f'{specs["fields"][key]["label"]} 不能为空')
                        changes[key] = None
                        continue
                    changes[key] = parse_value(text, kind)
                key_values = list(body.get('key') or [])
                raw_sub = body.get('subtype_changes')
                if table == 'lab_member' and raw_sub is not None:
                    if not isinstance(raw_sub, dict):
                        raise ValueError('subtype_changes 必须是 JSON 对象')
                    member = LabService(conn).get_record('lab_member', key_values)
                    if member is None:
                        raise ValueError('未找到此记录')
                    sub_table = SUBCLASSES[member['member_type']]
                    sub_specs = field_specs(sub_table)
                    sub_changes = {}
                    for skey, sraw in raw_sub.items():
                        if skey not in sub_specs['fields']:
                            raise ValueError(f'子类包含未知字段：{skey}')
                        skind = sub_specs['fields'][skey]['kind']
                        stext = '' if sraw is None else str(sraw).strip()
                        if stext == '':
                            continue
                        if stext.upper() == 'NULL':
                            if not skind.endswith('?'):
                                raise ValueError(f'{sub_specs["fields"][skey]["label"]} 不能为空')
                            sub_changes[skey] = None
                            continue
                        sub_changes[skey] = parse_value(stext, skind)
                    LabService(conn).update_member_with_subtype(key_values[0], changes, sub_changes)
                    changed = bool(changes or sub_changes)
                    return self._send(200, {'ok': True, 'message': '修改已提交' if changed else '没有修改字段'})
                LabService(conn).update_record(table, key_values, changes)
                return self._send(200, {'ok': True, 'message': '修改已提交' if changes else '没有修改字段'})
            except (RequestError, ValueError, KeyError, psycopg.Error) as error:
                return self._fail(error)

        def do_DELETE(self):
            try:
                self._check_origin()
                body = self._json_body()
                conn = self._conn()
                table = body.get('table')
                if table not in TABLES:
                    raise ValueError('未知的表名')
                LabService(conn).delete_record(table, list(body.get('key') or []))
                return self._send(200, {'ok': True, 'message': '删除已提交'})
            except (RequestError, ValueError, KeyError, psycopg.Error) as error:
                return self._fail(error)

        # -- static ----------------------------------------------------------
        def _static(self, path):
            if path in ('/', ''):
                path = '/index.html'
            target = (WEB_ROOT / path.lstrip('/')).resolve()
            if WEB_ROOT not in target.parents or not target.is_file():
                return self._send(404, {'ok': False, 'error': '未找到页面'})
            try:
                body = target.read_bytes()
            except OSError:
                # A file may disappear or become unreadable after the is_file check.
                return self._send(500, {'ok': False, 'error': '页面文件读取失败'})
            return self._send(200, body,
                              CONTENT_TYPES.get(target.suffix, 'application/octet-stream'))

    return Handler


def _subclass_of(member):
    from .service import SUBCLASSES
    if not isinstance(member, dict):
        raise ValueError('member 必须是 JSON 对象')
    table = SUBCLASSES.get(member.get('member_type'))
    if not table:
        raise ValueError('成员类型只能为 faculty、student、collaborator')
    return table


def create_server(dsn=None, schema=None, port=0, quiet=True):
    """Bind to LAB_WEB_HOST (default 127.0.0.1); port 0 lets the OS pick one.

    Containers set LAB_WEB_HOST=0.0.0.0 so a host-side port mapping is reachable.
    The default keeps the localhost-only demonstration behaviour unchanged.
    """
    host = os.environ.get('LAB_WEB_HOST', '127.0.0.1')
    handler = make_handler(dsn or os.environ.get('LAB_DSN', 'dbname=postgres'),
                           schema or os.environ.get('LAB_SCHEMA', DEFAULT_SCHEMA),
                           quiet=quiet)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd


def serve(dsn=None, schema=None, port=8000, quiet=False):
    httpd = create_server(dsn, schema, port, quiet=quiet)
    actual = httpd.server_address[1]
    host = os.environ.get('LAB_WEB_HOST', '127.0.0.1')
    display_host = 'localhost' if host in ('0.0.0.0', '') else host
    print(f'课堂演示网页已启动：http://{display_host}:{actual}/  （schema={schema or DEFAULT_SCHEMA}）')
    if host == '127.0.0.1':
        print('仅监听本机回环地址；Ctrl+C 停止。业务规则与终端完全同源。')
    else:
        print('容器模式：监听地址已由 LAB_WEB_HOST 指定；Ctrl+C 停止。业务规则与终端完全同源。')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n网页服务已停止。')
    finally:
        httpd.server_close()

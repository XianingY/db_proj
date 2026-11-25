"""The classroom web service reuses the terminal's business layer exactly."""
import io
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from research_lab.db import connect, initialize
from research_lab.web import create_server, make_handler

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = json.loads((ROOT / 'evidence' / 'sample_reference.json').read_text(encoding='utf-8'))


def call(port, path, method='GET', body=None, content_type='application/json', origin=None):
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}{path}',
        data=json.dumps(body).encode('utf-8') if body is not None else None,
        method=method,
        headers=({'Content-Type': content_type} if content_type else {}) |
                ({'Origin': origin} if origin else {}))
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode('utf-8'))
    except (urllib.error.URLError, ConnectionError) as error:
        # 让“服务直接断开”成为明确的断言失败，而不是测试框架错误。
        return 0, {'ok': False, 'error': f'连接异常：{error}'}


class WebServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'lab_web_' + uuid.uuid4().hex[:12]
        cls.conn = connect(schema=cls.schema)
        initialize(cls.conn, cls.schema)
        cls.web_dsn = make_conninfo(os.environ.get('LAB_DSN', 'dbname=postgres'),
                                    application_name='lab_web_test')
        cls.server = create_server(dsn=cls.web_dsn, schema=cls.schema, port=0, quiet=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        for conn in list(getattr(cls.server, 'connections', [])):
            if not conn.closed:
                conn.close()
        cls.conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        cls.conn.close()

    def test_api_requests_do_not_accumulate_database_connections(self):
        for _ in range(8):
            status, payload = call(self.port, '/api/meta')
            self.assertEqual(status, 200, payload)
        # 每个请求结束后都应释放自己的连接；查询真实数据库会话而非内部计数。
        deadline = time.monotonic() + 2
        while True:
            count = self.conn.execute(
                "SELECT count(*) AS n FROM pg_stat_activity "
                "WHERE application_name='lab_web_test'").fetchone()['n']
            if count == 0 or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        self.assertEqual(count, 0, 'API 请求结束后仍遗留 PostgreSQL 会话')

    def test_non_object_json_is_a_structured_client_error(self):
        for method in ['POST', 'PATCH', 'DELETE']:
            with self.subTest(method=method):
                status, payload = call(self.port, '/api/record', method, [])
                self.assertEqual(status, 400, payload)
                self.assertIn('JSON 对象', payload['error'])

    def test_nested_payload_types_are_validated(self):
        cases = [
            ('POST', {'table': 'lab_member', 'member': []}),
            ('PATCH', {'table': 'lab_member', 'key': ['S001'], 'changes': []}),
        ]
        for method, body in cases:
            with self.subTest(method=method):
                status, payload = call(self.port, '/api/record', method, body)
                self.assertEqual(status, 400, payload)
                self.assertIn('JSON 对象', payload['error'])

    def test_write_requires_json_content_type(self):
        status, payload = call(self.port, '/api/record', 'POST',
                               {'table': 'not_a_table'}, content_type='text/plain')
        self.assertEqual(status, 415, payload)
        self.assertIn('application/json', payload['error'])

    def test_cross_origin_write_is_refused(self):
        status, payload = call(self.port, '/api/record', 'POST',
                               {'table': 'not_a_table'}, origin='https://evil.example')
        self.assertEqual(status, 403, payload)
        self.assertIn('Origin', payload['error'])

    def test_request_length_is_validated_before_reading(self):
        handler_class = make_handler('dbname=postgres', self.schema, quiet=True)
        for length, message in [(1_000_001, '请求体过大'), (-1, 'Content-Length')]:
            with self.subTest(length=length):
                handler = object.__new__(handler_class)
                handler.headers = {'Content-Length': str(length),
                                   'Content-Type': 'application/json'}
                handler.rfile = io.BytesIO(b'{}')
                with self.assertRaisesRegex(ValueError, message):
                    handler._json_body()

    def test_meta_matches_reference_counts_and_reports(self):
        status, payload = call(self.port, '/api/meta')
        self.assertEqual(status, 200)
        meta = payload['meta']
        self.assertEqual(meta['counts'], REFERENCE['table_counts'])
        self.assertEqual(meta['total_tuples'], sum(REFERENCE['table_counts'].values()))
        self.assertEqual(len(meta['foreign_keys']), 14)
        # sample_reference.json groups reports differently from REPORTS order;
        # what matters is that the same ten reports are exposed.
        self.assertEqual(sorted(r['name'] for r in meta['reports']),
                         sorted(REFERENCE['reports']))
        for report in meta['reports']:
            self.assertIn('SELECT', report['sql'].upper())

    def test_static_index_is_served_and_traversal_blocked(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/', timeout=20) as response:
            html = response.read().decode('utf-8')
        self.assertIn('科研实验室管理系统', html)
        self.assertIn('/app.js', html)
        status, _ = call(self.port, '/../research_lab/web.py')
        self.assertEqual(status, 404)

    def test_rows_listing_search_and_record(self):
        status, payload = call(self.port, '/api/rows?table=lab_member&q=S001')
        self.assertEqual(status, 200)
        self.assertTrue(payload['rows'])
        self.assertTrue(all('S001' in row['member_id'] for row in payload['rows']))
        status, payload = call(self.port, '/api/record?table=lab_member&member_id=F001')
        self.assertEqual(status, 200)
        self.assertEqual(payload['record']['member_type'], 'faculty')
        status, _ = call(self.port, '/api/rows?table=nope')
        self.assertEqual(status, 400)

    def test_health_endpoint(self):
        status, payload = call(self.port, '/api/health')
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['db'])

    def test_rows_pagination_is_optional_and_bounded(self):
        status, full = call(self.port, '/api/rows?table=lab_member')
        self.assertEqual(status, 200, full)
        status, page = call(self.port, '/api/rows?table=lab_member&limit=5&offset=5')
        self.assertEqual(status, 200, page)
        self.assertEqual(page['rows'], full['rows'][5:10])
        status, _ = call(self.port, '/api/rows?table=lab_member&limit=0')
        self.assertEqual(status, 400)
        status, _ = call(self.port, '/api/rows?table=lab_member&offset=-1')
        self.assertEqual(status, 400)

    def test_report_all_variant(self):
        status, payload = call(self.port, '/api/report?name=project_status&all=1')
        self.assertEqual(status, 200, payload)
        self.assertEqual(len(payload['rows']), 10)
        # Without all=1 the previous contract stays: parameters are required.
        status, _ = call(self.port, '/api/report?name=project_status')
        self.assertEqual(status, 400)

    def test_database_unavailable_returns_503(self):
        with patch('research_lab.web.connect',
                   side_effect=psycopg.OperationalError('simulated outage')):
            status, payload = call(self.port, '/api/meta')
        self.assertEqual(status, 503, payload)
        self.assertFalse(payload['ok'])

    def test_reports_match_reference_row_for_row(self):
        params = {'project_status': 'project_id=P005', 'grant_members': 'grant_id=G001',
                  'equipment_status': 'equipment_id=E001',
                  'equipment_current_users': 'equipment_id=E001',
                  'ended_projects': 'end_before=2025-01-01'}
        for name, expected in REFERENCE['reports'].items():
            query = params.get(name, '')
            status, payload = call(
                self.port, '/api/report?name=' + name + ('&' + query if query else ''))
            self.assertEqual(status, 200, name)
            self.assertEqual(payload['rows'], expected['rows'], name)

    def test_member_create_update_delete_round_trip(self):
        body = {'table': 'lab_member',
                'member': {'member_id': 'WEB_STU', 'full_name': '网页演示学生',
                           'member_type': 'student', 'join_date': '2025-01-01'},
                'subtype': {'student_number': 'WEB2025', 'academic_level': '硕士',
                            'major': '计算机科学'},
                'participations': [{'project_id': 'P007', 'project_role': '研究助理',
                                    'weekly_hours': '6'}]}
        status, payload = call(self.port, '/api/rows', 'POST', body)
        self.assertEqual(status, 200, payload)
        status, payload = call(self.port, '/api/record?table=student&member_id=WEB_STU')
        self.assertEqual(status, 200)
        self.assertEqual(payload['record']['major'], '计算机科学')
        status, payload = call(self.port, '/api/record', 'PATCH',
                               {'table': 'lab_member', 'key': ['WEB_STU'],
                                'changes': {'full_name': '网页改名', 'join_date': ''}})
        self.assertEqual(status, 200, payload)
        status, payload = call(self.port, '/api/record?table=lab_member&member_id=WEB_STU')
        self.assertEqual(payload['record']['full_name'], '网页改名')
        self.assertEqual(str(payload['record']['join_date']), '2025-01-01')
        status, payload = call(self.port, '/api/record', 'DELETE',
                               {'table': 'lab_member', 'key': ['WEB_STU']})
        self.assertEqual(status, 200, payload)
        status, _ = call(self.port, '/api/record?table=lab_member&member_id=WEB_STU')
        self.assertEqual(status, 400)

    def test_invalid_create_rolls_back_entirely(self):
        body = {'table': 'lab_member',
                'member': {'member_id': 'WEB_BAD', 'full_name': '缺项目',
                           'member_type': 'student', 'join_date': '2025-01-01'},
                'subtype': {'student_number': 'WEBBAD', 'academic_level': '硕士', 'major': '专业'},
                'participations': [{'project_id': 'DOES_NOT_EXIST', 'project_role': '助理',
                                    'weekly_hours': '1'}]}
        status, payload = call(self.port, '/api/rows', 'POST', body)
        self.assertEqual(status, 400, payload)
        status, _ = call(self.port, '/api/record?table=lab_member&member_id=WEB_BAD')
        self.assertEqual(status, 400)

    def test_protected_delete_is_refused(self):
        status, payload = call(self.port, '/api/record', 'DELETE',
                               {'table': 'lab_member', 'key': ['F001']})
        self.assertEqual(status, 400, payload)
        self.assertIn('负责人', payload['error'])


if __name__ == '__main__':
    unittest.main()

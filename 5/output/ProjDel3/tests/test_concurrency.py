"""Real independent sessions: a waiting fourth user must be rejected at commit."""
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import psycopg
from psycopg import sql
from research_lab.db import connect, initialize
from research_lab.service import LabService


class ConcurrencyTests(unittest.TestCase):
    def test_raw_sql_concurrent_fourth_member_cannot_commit(self):
        schema = 'lab_concurrent_' + uuid.uuid4().hex[:12]
        admin = connect(schema=schema)
        a = b = None
        try:
            initialize(admin,schema)
            LabService(admin).create_equipment(dict(equipment_id='CON_EQ',equipment_name='并发测试',
                equipment_type='仪器',manual_location='test.pdf'),
                [dict(device_number='01',purchase_date='2020-01-01',status='available')])
            insert = """INSERT INTO equipment_usage
                (usage_id,member_id,equipment_id,device_number,started_at,ended_at,purpose)
                VALUES (%s,%s,'CON_EQ','01',
                    (clock_timestamp() AT TIME ZONE 'Asia/Shanghai') - interval '1 hour',NULL,'并发测试')"""
            for i in (1,2):
                admin.execute(insert,('CON_U'+str(i),'S00'+str(i)))
            a,b = connect(schema=schema),connect(schema=schema)
            a.execute('BEGIN')
            a.execute(insert,('CON_U3','S003'))
            started = Event()
            def fourth():
                try:
                    with b.transaction():
                        started.set()
                        b.execute(insert,('CON_U4','S004'))
                    return 'unexpected_commit'
                except psycopg.Error as error:
                    return error.sqlstate,error.diag.message_primary
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(fourth)
                self.assertTrue(started.wait(5))
                deadline = time.monotonic()+5
                waiting = False
                while time.monotonic()<deadline:
                    waiting = admin.execute('SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s '
                        "AND locktype='advisory' AND NOT granted) AS waiting",
                        (b.info.backend_pid,)).fetchone()['waiting']
                    if waiting:
                        break
                    time.sleep(0.02)
                # Release a even if the diagnostic assertion fails; never leave a worker blocked.
                a.execute('COMMIT')
                outcome = future.result(timeout=10)
                self.assertTrue(waiting,'second transaction never waited on the serialized write lock')
                self.assertEqual(outcome[0],'23514',outcome)
                self.assertIn('最多由三名',outcome[1])
            self.assertEqual(admin.execute("SELECT COUNT(*) AS n FROM equipment_usage WHERE equipment_id='CON_EQ'")
                             .fetchone()['n'],3)
            self.assertIsNone(admin.execute("SELECT 1 FROM equipment_usage WHERE usage_id='CON_U4'").fetchone())
            admin.execute('SELECT lab_assert_integrity()')
        finally:
            for connection in (a,b):
                if connection is not None:
                    connection.close()
            # initialize is all-or-nothing; this name was freshly generated, never user data.
            admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            admin.close()


if __name__=='__main__':
    unittest.main()

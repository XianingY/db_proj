"""Integration tests on a private, disposable PostgreSQL schema.

Run: python -m unittest discover -s tests -v
Never reuses or drops an existing schema. Each test rolls its changes back.
"""
import os
import unittest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql

from research_lab.db import connect, initialize
from research_lab.service import LabService, TABLES


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'lab_test_' + uuid.uuid4().hex[:12]
        cls.conn = connect(schema=cls.schema)
        try:
            initialize(cls.conn, cls.schema)
        except Exception:
            cls.conn.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        cls.conn.close()

    def setUp(self):
        self.conn.execute('BEGIN')
        self.service = LabService(self.conn)

    def tearDown(self):
        self.conn.execute('ROLLBACK')

    def assert_invalid(self, callable_, message=None):
        with self.assertRaises((psycopg.Error, ValueError)) as error:
            callable_()
        if message:
            self.assertIn(message, str(error.exception))
        # Connection remains usable and the instance is still consistent.
        self.conn.execute('SELECT lab_assert_integrity()')

    def test_01_all_tables_have_sample_data(self):
        for name in TABLES:
            count = self.conn.execute(sql.SQL('SELECT count(*) AS n FROM {}')
                                      .format(sql.Identifier(name))).fetchone()['n']
            self.assertGreater(count, 0, name)
        self.conn.execute('SELECT lab_assert_integrity()')

    def test_02_member_create_update_delete(self):
        self.service.create_member(
            dict(member_id='NEW_STU', full_name='测试学生', member_type='student', join_date='2025-01-01'),
            dict(student_number='000123', academic_level='graduate', major='测试专业'),
            [dict(project_id='P001', project_role='研究助理', weekly_hours=5)])
        self.service.update_record('lab_member', ('NEW_STU',), dict(full_name='修改后的姓名'))
        self.service.update_record('student', ('NEW_STU',), dict(major='新专业'))
        self.assertEqual(self.service.get_record('student', ('NEW_STU',))['student_number'], '000123')
        self.service.delete_record('lab_member', ('NEW_STU',))
        self.assertIsNone(self.service.get_record('lab_member', ('NEW_STU',)))

    def test_03_member_without_participation_rolls_back(self):
        self.assert_invalid(lambda: self.service.create_member(
            dict(member_id='INVALID_STU', full_name='学生', member_type='student', join_date='2025-01-01'),
            dict(student_number='BAD001', academic_level='graduate', major='专业'), []), '至少参加')
        self.assertIsNone(self.service.get_record('lab_member', ('INVALID_STU',)))

    def test_04_project_create_update_delete(self):
        self.service.create_project(dict(project_id='TEMP_PROJECT', title='临时项目',
            start_date='2025-01-01', end_date=None, planned_duration_days=300,
            status='active', leader_id='F001'), [])
        self.assertIsNotNone(self.service.get_record('project_participation', ('F001','TEMP_PROJECT')))
        self.service.update_record('research_project', ('TEMP_PROJECT',),
                                   dict(status='completed', end_date='2025-12-01'))
        self.service.delete_record('research_project', ('TEMP_PROJECT',))
        self.assertIsNone(self.service.get_record('research_project', ('TEMP_PROJECT',)))

    def test_05_completed_project_without_end_rejected(self):
        self.assert_invalid(lambda: self.service.update_record('research_project', ('P001',),
                                                               dict(status='completed', end_date=None)))

    def test_06_leader_must_participate(self):
        p = self.service.get_record('research_project', ('P001',))
        self.assert_invalid(lambda: self.service.delete_record('project_participation',
                            (p['leader_id'],'P001')), '负责人')

    def test_07_faculty_leading_project_cannot_be_removed(self):
        self.assert_invalid(lambda: self.service.delete_record('lab_member', ('F001',)))
        self.assertIsNotNone(self.service.get_record('lab_member', ('F001',)))

    def test_08_equipment_device_usage_lifecycle(self):
        self.service.create_equipment(dict(equipment_id='TEMP_EQ',equipment_name='测试仪器',
            equipment_type='仪器',manual_location='manual.pdf'),
            [dict(device_number='01',purchase_date='2020-01-01',status='available')])
        now = datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None, microsecond=0)
        self.service.create_record('equipment_usage', dict(usage_id='TEMP_USE',member_id='S001',
            equipment_id='TEMP_EQ',device_number='01',started_at=now-timedelta(hours=2),
            ended_at=None,purpose='实验'))
        self.assertEqual(self.service.get_record('device',('TEMP_EQ','01'))['status'],'in_use')
        self.service.update_record('equipment_usage',('TEMP_USE',),dict(ended_at=now-timedelta(hours=1)))
        self.assertEqual(self.service.get_record('device',('TEMP_EQ','01'))['status'],'available')
        self.service.update_record('equipment_usage',('TEMP_USE',),dict(purpose='已修改目的'))
        self.service.delete_record('equipment_usage',('TEMP_USE',))
        self.service.update_record('equipment',('TEMP_EQ',),dict(equipment_name='新名称'))
        self.assert_invalid(lambda:self.service.delete_record('device',('TEMP_EQ','01')),'至少有一台')
        self.service.delete_record('equipment',('TEMP_EQ',))
        self.assertIsNone(self.service.get_record('equipment',('TEMP_EQ',)))

    def new_device(self):
        self.service.create_equipment(dict(equipment_id='TEMP_EQ',equipment_name='测试仪器',
            equipment_type='仪器',manual_location='manual.pdf'),
            [dict(device_number='01',purchase_date='2020-01-01',status='available')])

    def usage(self, identifier, member, start, end):
        self.service.create_record('equipment_usage',dict(usage_id=identifier,member_id=member,
            equipment_id='TEMP_EQ',device_number='01',started_at=start,ended_at=end,purpose='测试'))

    def test_09_fourth_simultaneous_member_rejected(self):
        self.new_device()
        for i in range(1,4):
            self.usage(f'CAP{i}',f'S{i:03}','2024-01-01 09:00','2024-01-01 12:00')
        self.assert_invalid(lambda:self.usage('CAP4','S004','2024-01-01 10:00','2024-01-01 11:00'),'三名')
        self.assertIsNone(self.service.get_record('equipment_usage',('CAP4',)))

    def test_10_overlap_same_member_and_boundary(self):
        self.new_device()
        self.usage('A','S001','2024-01-01 09:00','2024-01-01 10:00')
        self.assert_invalid(lambda:self.usage('B','S001','2024-01-01 09:30','2024-01-01 10:30'),'重叠')
        self.usage('C','S001','2024-01-01 10:00','2024-01-01 11:00')
        self.usage('ZERO','S001','2024-01-01 09:30','2024-01-01 09:30')

    def test_11_future_actual_usage_rejected(self):
        self.new_device()
        future=datetime.now(ZoneInfo('Asia/Shanghai')).replace(tzinfo=None)+timedelta(days=1)
        self.assert_invalid(lambda:self.usage('FUTURE','S001',future,None),'录入')

    def test_12_retired_device_cannot_start_use(self):
        self.new_device()
        self.service.update_record('device',('TEMP_EQ','01'),dict(status='retired'))
        self.assert_invalid(lambda:self.usage('RETIRED','S001','2024-01-01 09:00',None),'退役')

    def test_13_retirement_with_open_usage_rolls_back(self):
        self.new_device()
        self.usage('OPEN','S001','2024-01-01 09:00',None)
        self.assert_invalid(lambda:self.service.update_record('device',('TEMP_EQ','01'),dict(status='retired')),'状态')
        self.assertEqual(self.service.get_record('device',('TEMP_EQ','01'))['status'],'in_use')

    def test_14_students_cannot_mentor_faculty(self):
        self.assert_invalid(lambda:self.service.create_record('mentorship',
            dict(mentee_id='F006',mentor_id='S001',start_date='2025-01-01',end_date=None)))

    def test_15_no_self_mentorship(self):
        self.assert_invalid(lambda:self.service.create_record('mentorship',
            dict(mentee_id='C004',mentor_id='C004',start_date='2025-01-01',end_date=None)))

    def test_16_one_saved_mentorship_per_mentee(self):
        existing=self.service.list_rows('mentorship')[0]
        self.assert_invalid(lambda:self.service.create_record('mentorship',
            dict(mentee_id=existing['mentee_id'],mentor_id='F006',start_date='2025-01-01',end_date=None)))

    def test_17_publication_author_atomic_and_last_author_rejected(self):
        self.service.create_publication(dict(publication_id='TEMP_PUB',title='测试论文',
            publication_year=2024,publication_month=2,publication_day=29,venue='测试会议',doi=None), ['S001'])
        self.assert_invalid(lambda:self.service.delete_record('authorship',('S001','TEMP_PUB')),'至少有一位')
        self.service.update_record('publication',('TEMP_PUB',),dict(title='新题目'))
        self.service.delete_record('publication',('TEMP_PUB',))

    def test_18_invalid_leap_day_and_no_authors(self):
        bad=dict(publication_id='BAD_PUB',title='论文',publication_year=2023,
                 publication_month=2,publication_day=29,venue='会议',doi=None)
        self.assert_invalid(lambda:self.service.create_publication(bad,['S001']))
        bad.update(publication_year=2024)
        self.assert_invalid(lambda:self.service.create_publication(bad,[]),'至少有一位')

    def test_19_grant_crud(self):
        self.service.create_record('research_grant',dict(grant_id='TEMP_GRANT',
            funding_agency='测试机构',budget=Decimal('123.45'),start_date='2025-01-01',
            expected_duration_days=100,reporting_requirements='年度报告',project_id='P001'))
        self.service.update_record('research_grant',('TEMP_GRANT',),dict(budget=Decimal('678.90')))
        self.assertEqual(self.service.get_record('research_grant',('TEMP_GRANT',))['budget'],Decimal('678.90'))
        self.service.delete_record('research_grant',('TEMP_GRANT',))

    def test_20_last_participation_rejected(self):
        self.service.create_member(dict(member_id='ONE_PROJECT',full_name='只有一个项目',
            member_type='collaborator',join_date='2025-01-01'),dict(affiliation='机构',short_cv='履历'),
            [dict(project_id='P001',project_role='合作',weekly_hours=2)])
        self.assert_invalid(lambda:self.service.delete_record('project_participation',('ONE_PROJECT','P001')),'至少参加')

    def test_21_raw_sql_subclass_mutual_exclusion(self):
        def wrong_subclass():
            with self.conn.transaction():
                self.conn.execute("INSERT INTO faculty VALUES ('S001','错误院系')")
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assert_invalid(wrong_subclass,'子类')

    def test_22_raw_sql_member_missing_subclass(self):
        def bad_member():
            with self.conn.transaction():
                self.conn.execute("INSERT INTO lab_member VALUES ('NO_SUBCLASS','错误','student','2025-01-01')")
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assert_invalid(bad_member,'子类')

    def test_23_whitelist_and_id_immutability(self):
        self.assert_invalid(lambda:self.service.list_rows('lab_member; DROP TABLE lab_member'))
        self.assert_invalid(lambda:self.service.update_record('lab_member',('S001',),dict(member_id='NEW_ID')))
        # Apostrophes in data are values, not executable SQL.
        self.service.update_record('lab_member',('S001',),dict(full_name="O'Neil; SELECT 1"))
        self.assertEqual(self.service.get_record('lab_member',('S001',))['full_name'],"O'Neil; SELECT 1")
        # A literal '%' is an intentional match-all wildcard, not an escaped
        # literal; keep this terminal search convention pinned.
        self.assertEqual(self.service.list_rows('lab_member', '%'),
                         self.service.list_rows('lab_member'))

    def test_24_no_destructive_reinitialization(self):
        self.assert_invalid(lambda:initialize(self.conn,self.schema),'已存在')

    def test_25_invalid_hours_and_nan_budget(self):
        self.assert_invalid(lambda:self.service.update_record('project_participation',('F001','P001'),dict(weekly_hours=169)))
        row=self.service.list_rows('research_grant')[0]
        self.assert_invalid(lambda:self.service.update_record('research_grant',(row['grant_id'],),dict(budget='NaN')))

    def test_26_member_detail_returns_subtype_participations_and_mentorship(self):
        faculty = self.service.member_detail('F001')
        self.assertEqual(faculty['subtype_table'], 'faculty')
        self.assertEqual(faculty['subtype']['department'], '计算机科学系')
        self.assertIsNone(faculty['mentor'])
        self.assertEqual(len(faculty['mentees']), 3)
        self.assertGreaterEqual(len(faculty['participations']), 3)

        student = self.service.member_detail('S003')
        self.assertEqual(student['subtype_table'], 'student')
        self.assertEqual(student['mentor']['mentor_id'], 'F001')
        self.assertEqual(str(student['mentor']['end_date']), '2024-06-30')

        collab = self.service.member_detail('C001')
        self.assertEqual(collab['subtype_table'], 'external_collaborator')
        self.assertEqual(collab['mentor']['mentor_id'], 'S007')

        with self.assertRaises(ValueError):
            self.service.member_detail('NO_SUCH_MEMBER')


if __name__ == '__main__':
    unittest.main(verbosity=2)

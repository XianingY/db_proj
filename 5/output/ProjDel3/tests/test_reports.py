"""Expected results independently derived from the fictional sample fixture."""
import json
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg import sql
from research_lab.db import connect, initialize
from research_lab.reports import REPORTS, run_report
from research_lab.service import LabService
import test_application

REFERENCE = json.loads((Path(__file__).resolve().parents[1]/'evidence/sample_reference.json').read_text())


def normalize(value):
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    if isinstance(value,dict):
        return {k:normalize(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [normalize(v) for v in value]
    return value


class ReportTests(unittest.TestCase):
    setUpClass = classmethod(test_application.ApplicationTests.setUpClass.__func__)
    tearDownClass = classmethod(test_application.ApplicationTests.tearDownClass.__func__)

    def setUp(self):
        self.conn.execute('BEGIN')

    def tearDown(self):
        self.conn.execute('ROLLBACK')

    def test_sample_counts_match_independent_fixture(self):
        for table,count in REFERENCE['table_counts'].items():
            actual=self.conn.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}').format(sql.Identifier(table))).fetchone()['n']
            self.assertEqual(actual,count,table)

    def test_schema_has_original_13_primary_keys_and_14_no_action_foreign_keys(self):
        rows=self.conn.execute("SELECT contype,COUNT(*) AS n FROM pg_constraint WHERE connamespace="
            '(SELECT oid FROM pg_namespace WHERE nspname=%s) GROUP BY contype',(self.schema,)).fetchall()
        counts={r['contype']:r['n'] for r in rows}
        self.assertEqual(counts['p'],13)
        self.assertEqual(counts['f'],14)
        self.assertFalse(self.conn.execute("SELECT 1 FROM pg_constraint WHERE connamespace="
            "(SELECT oid FROM pg_namespace WHERE nspname=%s) AND contype='f' "
            "AND (confdeltype <> 'a' OR confupdtype <> 'a')",(self.schema,)).fetchone())

    def test_all_zero_mentors_return_all_ties(self):
        for publication in self.conn.execute('SELECT publication_id FROM publication').fetchall():
            LabService(self.conn).delete_record('publication',(publication['publication_id'],))
        self.assertEqual([(r['mentor_id'],r['publication_count']) for r in run_report(self.conn,'mentor_publications')],
                         [('F001',0),('F002',0),('F003',0),('F004',0),('F005',0),('F006',0)])

    def test_equal_grant_amounts_are_not_deduplicated(self):
        service=LabService(self.conn)
        for grant_id in ['SAME1','SAME2']:
            service.create_record('research_grant',dict(grant_id=grant_id,funding_agency='测试机构',
                budget=600000,start_date='2026-01-01',expected_duration_days=100,
                reporting_requirements='报告',project_id='P010'))
        actual=run_report(self.conn,'top_funded_projects')[0]
        self.assertEqual((actual['project_id'],actual['total_funding_usd']),('P010',Decimal('1200000.00')))

    def test_coauthored_years_top3_exact_limit_and_deterministic_tie(self):
        service=LabService(self.conn)
        for publication in self.conn.execute('SELECT publication_id FROM publication').fetchall():
            service.delete_record('publication',(publication['publication_id'],))
        for year in (2023,2024,2025,2026):
            service.create_publication(dict(publication_id='TIE'+str(year),title='共同作者',
                publication_year=year,publication_month=1,publication_day=None,venue='测试',doi=None),
                ['S001','S002','S005'])
        self.assertEqual(run_report(self.conn,'top_student_years'),
            [{'publication_year':2026,'publication_count':1},
             {'publication_year':2025,'publication_count':1},
             {'publication_year':2024,'publication_count':1}])
        self.assertTrue(all(r['publication_count']==1 for r in
                            run_report(self.conn,'student_publications_by_major_year')))

    def test_missing_entities_and_parameter_binding(self):
        for key,argument in [('project_status','ABSENT'),('grant_members',"G001' OR '1'='1"),
                             ('equipment_current_users','ABSENT'),('equipment_status','ABSENT')]:
            self.assertEqual(run_report(self.conn,key,(argument,)),[])
        with self.assertRaises(ValueError):
            run_report(self.conn,'ended_projects',())

    def test_current_equipment_users_only_active_projects_and_no_user_lost(self):
        rows=run_report(self.conn,'equipment_current_users',('E001',))
        self.assertEqual({r['member_id'] for r in rows},{'F001','S001','S002','S004'})
        self.assertEqual([(r['member_id'],r['project_id']) for r in rows],
                         [('F001','P007'),('S001','P006'),('S001','P007'),('S002','P007'),('S004',None)])

    def test_truncate_cannot_bypass_mandatory_authorship(self):
        self.conn.execute('SAVEPOINT forbid_truncate')
        with self.assertRaises(psycopg.Error):
            self.conn.execute('TRUNCATE authorship')
        self.conn.execute('ROLLBACK TO SAVEPOINT forbid_truncate')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) AS n FROM authorship').fetchone()['n'],144)


def reference_test(name,expected):
    def check(self):
        self.assertEqual(normalize(run_report(self.conn,name,tuple(expected['params']))),expected['rows'])
    check.__name__='test_reference_'+name
    return check


for name,expectation in REFERENCE['reports'].items():
    setattr(ReportTests,'test_reference_'+name,reference_test(name,expectation))


if __name__=='__main__':
    unittest.main()

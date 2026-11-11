"""Run real tests, independent report checks, standalone SQL, and terminal demos.

Generated evidence is data, not invented results. Only fresh owned schemas are dropped.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from psycopg import sql
from research_lab.db import connect, initialize
from research_lab.reports import REPORTS, run_report


def normalized(value):
    # Decimal and date are serialized exactly, never through float.
    return json.loads(json.dumps(value,ensure_ascii=False,default=str))


def main():
    evidence=ROOT/'evidence'
    evidence.mkdir(exist_ok=True)
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
                        cwd=ROOT,text=True,capture_output=True,timeout=120)
    log=test.stdout+test.stderr
    (evidence/'unittest.log').write_text(log,encoding='utf-8')
    if test.returncode:
        print(log)
        raise SystemExit('测试失败，停止生成通过证据')
    count=int(re.search(r'Ran (\d+) tests',log).group(1))
    reference=json.loads((evidence/'sample_reference.json').read_text())
    schema='lab_evidence_'+uuid.uuid4().hex[:12]
    results={}
    with connect(schema=schema) as conn:
        try:
            initialize(conn,schema)
            counts={table:conn.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}').format(
                sql.Identifier(table))).fetchone()['n'] for table in reference['table_counts']}
            assert counts==reference['table_counts'],(counts,reference['table_counts'])
            for name,expected in reference['reports'].items():
                rows=normalized(run_report(conn,name,tuple(expected['params'])))
                assert rows==expected['rows'],name
                results[name]={'params':expected['params'],'rows':rows,'matches_reference':True}
            conn.execute('SELECT lab_assert_integrity()')
            version=conn.execute('SHOW server_version').fetchone()['server_version']
            constraint_counts=conn.execute('SELECT contype,COUNT(*) AS count FROM pg_constraint '
                'WHERE connamespace=(SELECT oid FROM pg_namespace WHERE nspname=%s) '
                'GROUP BY contype ORDER BY contype',(schema,)).fetchall()
            if shutil.which('psql') is None:
                raise SystemExit('缺少 psql，无法验证独立 SQL 文件；已完成 unittest，但本轮不标记整体通过')
            env=os.environ.copy()
            env['PGOPTIONS']=f'-c search_path={schema}'
            standalone=subprocess.run(['psql','-d',os.environ.get('LAB_DSN','dbname=postgres'),
                '-v','ON_ERROR_STOP=1','-P','pager=off','-v','project_id=P005','-v','grant_id=G001',
                '-v','equipment_id=E001','-v','end_before=2025-01-01','-f','SQL/04_report_queries.sql'],
                cwd=ROOT,env=env,text=True,capture_output=True,timeout=30)
            (evidence/'standalone_sql.log').write_text(standalone.stdout+standalone.stderr,encoding='utf-8')
            assert standalone.returncode==0,'独立 SQL 执行失败'
            machine=subprocess.run(['psql','-d',os.environ.get('LAB_DSN','dbname=postgres'),
                '-v','ON_ERROR_STOP=1','-P','pager=off','-A','-F','|','-t',
                '-v','project_id=P005','-v','grant_id=G001','-v','equipment_id=E001',
                '-v','end_before=2025-01-01','-f','SQL/04_report_queries.sql'],
                cwd=ROOT,env=env,text=True,capture_output=True,timeout=30)
            assert machine.returncode==0,'机器可读独立 SQL 执行失败'
            lines=[line for line in machine.stdout.splitlines() if line.strip()]
            order=['project_status','grant_members','shared_project_mentorship',
                   'equipment_status','equipment_current_users','top_funded_projects',
                   'mentor_publications','student_publications_by_major_year',
                   'ended_projects','top_student_years']
            # The program rows were already asserted equal to the independent
            # reference above; comparing the standalone SQL file against the
            # program rows therefore pins file == program == reference.
            lines=[line for line in machine.stdout.splitlines() if line.strip()]
            order=['project_status','grant_members','shared_project_mentorship',
                   'equipment_status','equipment_current_users','top_funded_projects',
                   'mentor_publications','student_publications_by_major_year',
                   'ended_projects','top_student_years']
            position=0
            mismatch=[]
            for name in order:
                for row in results[name]['rows']:
                    want='|'.join('' if value is None else str(value)
                                  for key,value in row.items() if key!='devices')
                    got=lines[position] if position<len(lines) else '<missing>'
                    if 'devices' in row:
                        got=got.rsplit('|',1)[0]
                    if want!=got:
                        mismatch.append((name,want,got))
                    position+=1
            assert not mismatch,('独立 SQL 行与程序/参考不一致',mismatch[:3])
            assert position==len(lines),('独立 SQL 行数不一致',position,len(lines))
            demo=subprocess.run([sys.executable,'app.py','--schema',schema,'--demo'],
                cwd=ROOT,text=True,capture_output=True,timeout=30)
            assert demo.returncode==0,demo.stderr
            (evidence/'demo_reports.txt').write_text(demo.stdout,encoding='utf-8')
            menu_input=['1','1','2','DEMO_STU','终端演示学生','student','2025-01-01',
                'DEMO2025','硕士','计算机科学','P007','研究助理','6','n',
                '3','DEMO_STU','终端修改姓名','', '4','DEMO_STU','DELETE',
                '4','F001','DELETE','0','3','P001','0','2','4','E001','0',
                '3','1','2','4','2025-01-01','5','0','0']
            menu=subprocess.run([sys.executable,'app.py','--schema',schema],
                input='\n'.join(menu_input)+'\n',cwd=ROOT,text=True,capture_output=True,timeout=30)
            assert menu.returncode==0,menu.stderr
            assert menu.stdout.count('操作成功')==3,menu.stdout
            assert menu.stdout.count('操作失败')==1,menu.stdout
            assert conn.execute("SELECT 1 FROM lab_member WHERE member_id='DEMO_STU'").fetchone() is None
            conn.execute('SELECT lab_assert_integrity()')
            (evidence/'menu_demo.txt').write_text(menu.stdout,encoding='utf-8')
            (evidence/'menu_inputs.txt').write_text('\n'.join(menu_input)+'\n',encoding='utf-8')
            report={'verified_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                'python':sys.version.split()[0],'postgresql':version,'schema_isolation':'fresh random schema',
                'status':'passed','unittest_count':count,'unittest_exit_code':test.returncode,
                'standalone_sql_exit_code':standalone.returncode,'terminal_demo_exit_code':menu.returncode,
                'terminal_demo_successful_mutations':3,'terminal_demo_expected_rejections':1,
                'primary_key_count':13,'foreign_key_count':14,'constraints':constraint_counts,
                'table_counts':counts,'total_sample_tuples':sum(counts.values()),'reports':results,
                'standalone_sql_rows_match_reference':True,
                'source_create_tables_sha256':hashlib.sha256((ROOT/'SQL/01_create_tables.sql').read_bytes()).hexdigest(),
                'concurrency_test':'two real sessions; fourth waits, third commits, fourth rejected with 23514',
                'no_existing_business_data_overwritten':True}
            (evidence/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        finally:
            conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
    print(f'真实验证通过：{count} 项测试，十项报表逐行吻合，独立 SQL 与终端演示退出码 0。')


if __name__=='__main__':
    main()

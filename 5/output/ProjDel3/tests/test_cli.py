"""Exercise the real terminal and PostgreSQL, not a mock menu."""
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from psycopg import sql
from research_lab.db import connect, initialize

ROOT = Path(__file__).resolve().parents[1]


class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = 'lab_cli_' + uuid.uuid4().hex[:12]
        cls.conn = connect(schema=cls.schema)
        initialize(cls.conn, cls.schema)

    @classmethod
    def tearDownClass(cls):
        cls.conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        cls.conn.close()

    def terminal(self, lines, *args):
        return subprocess.run([sys.executable, str(ROOT/'app.py'), '--schema', self.schema, *args],
            input='\n'.join(lines)+'\n', text=True, capture_output=True, cwd=ROOT, timeout=30)

    def test_three_main_menus_and_reports(self):
        result = self.terminal(['1','3','P001','0', '2','3','E001','0',
                               '3','1','2','3','4','2025-01-01','5','0','0'])
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        for expected in ['项目与成员管理','设备使用跟踪','资助与成果报告','P001','E001','USD','2025']:
            self.assertIn(expected,result.stdout)
        self.assertNotIn('操作失败',result.stdout)

    def test_member_crud_is_persisted_and_removed(self):
        result = self.terminal(['1','1','2','CLI_STU','终端新增学生','student','2025-01-01',
            'CLI2025','硕士','计算机科学','P001','研究助理','5','n',
            '3','CLI_STU','终端修改姓名','', '4','CLI_STU','DELETE','0','0','0'])
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(result.stdout.count('操作成功'),3,result.stdout)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM lab_member WHERE member_id='CLI_STU'").fetchone())

    def test_invalid_add_rolls_back_and_menu_continues(self):
        result = self.terminal(['1','1','2','CLI_BAD','缺少项目学生','student','2025-01-01',
            'CLIBAD','硕士','专业','DOES_NOT_EXIST','助理','1','n', '1','CLI_BAD','0','0','0'])
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertIn('操作失败',result.stdout)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM lab_member WHERE member_id='CLI_BAD'").fetchone())

    def test_project_crud_from_terminal(self):
        result=self.terminal(['1','2','2','CLI_PROJ','终端新增项目','2025-01-01','',
            '365','active','F001','3','CLI_PROJ','终端修改项目','','2025-12-01','',
            'completed','', '4','CLI_PROJ','DELETE','0','0','0'])
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(result.stdout.count('操作成功'),3,result.stdout)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM research_project WHERE project_id='CLI_PROJ'").fetchone())

    def test_equipment_and_usage_crud_from_terminal(self):
        result=self.terminal(['2','1','2','CLI_EQ','终端设备','仪器','manual.pdf',
            '01','2020-01-01','available','3','CLI_EQ','修改设备','','', '0',
            '2','2','CLI_USE','S001','CLI_EQ','01','2026-01-01 08:00:00','', '实验',
            '3','CLI_USE','','','','','2026-01-01 09:00:00','已结束实验',
            '4','CLI_USE','DELETE','0', '1','4','CLI_EQ','DELETE','0','0','0'])
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(result.stdout.count('操作成功'),6,result.stdout)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM equipment WHERE equipment_id='CLI_EQ'").fetchone())
        self.assertIsNone(self.conn.execute("SELECT 1 FROM equipment_usage WHERE usage_id='CLI_USE'").fetchone())

    def test_empty_parameter_lists_all_statuses(self):
        result = self.terminal(['1','3','','0','2','3','','0','0'])
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('P001', result.stdout)
        self.assertIn('E001', result.stdout)
        self.assertIn('共 10 条记录', result.stdout)
        self.assertIn('共 6 条记录', result.stdout)
        self.assertNotIn('操作失败', result.stdout)

    def test_read_only_demo(self):
        result = self.terminal([], '--demo')
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertIn('学生成果最多的三个年份',result.stdout)
        self.assertIn('mentor_publications',result.stdout)

    def test_eof_and_invalid_menu_selection(self):
        result = self.terminal(['999'])
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertIn('无效选项',result.stdout)


if __name__ == '__main__':
    unittest.main()

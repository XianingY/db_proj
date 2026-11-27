"""Layout and label rules for the terminal UI; pure functions, no database."""
import io
import sys
import unittest
from contextlib import redirect_stdout

from research_lab.cli import (HARD_TOKEN_LIMIT, LABELS, MIN_COLUMN_WIDTH,
                              display_rows, fit_sizes, minimum_width, pretty, width, wrapped)
from research_lab.service import TABLES


class WrappingTests(unittest.TestCase):
    def test_short_ascii_values_are_never_split(self):
        for value in ['2024-01-15 09:00:00', 'collaborator', 'device01', 'P001']:
            self.assertEqual(minimum_width(value), width(value))
            self.assertEqual(wrapped(value, width(value)), [value])

    def test_long_ascii_text_may_break_at_spaces(self):
        value = 'manuals ' * 8 + 'end'
        self.assertGreater(width(value), HARD_TOKEN_LIMIT)
        self.assertLess(minimum_width(value), width(value))

    def test_cjk_breaks_anywhere_and_is_not_truncated(self):
        value = '可信科研数据平台'
        self.assertEqual(minimum_width(value), 2)
        self.assertEqual(wrapped(value, 8), ['可信科研', '数据平台'])
        self.assertEqual(''.join(wrapped(value, 5)).replace(' ', ''), value)

    def test_token_longer_than_column_is_hard_split_without_loss(self):
        parts = wrapped('supercalifragilistic', 6)
        self.assertGreater(len(parts), 1)
        self.assertEqual(''.join(parts), 'supercalifragilistic')
        self.assertTrue(all(width(part) <= 6 for part in parts))


class SizingTests(unittest.TestCase):
    def test_fit_sizes_respects_minimums_and_budget(self):
        natural = [8, 6, 12, 8, 8, 18, 10, 10]
        minimum = [5, 5, 5, 5, 5, 5, 10, 5]
        sizes = fit_sizes(natural, minimum, 77)
        self.assertLessEqual(sum(sizes), 77)
        self.assertTrue(all(s >= m for s, m in zip(sizes, minimum)))

    def test_fit_sizes_gives_natural_width_when_room_allows(self):
        natural = [8, 6, 10]
        self.assertEqual(fit_sizes(natural, [5, 5, 5], 100), natural)


class LabelTests(unittest.TestCase):
    def test_labels_do_not_leak_input_hints(self):
        for _, _, fields in TABLES.values():
            for description in fields.values():
                label = description.split('|')[0]
                for banned in ['faculty/', 'available/', '0-168', 'YYYY-MM-DD', '（', '）']:
                    self.assertNotIn(banned, label)
        for key, label in LABELS.items():
            self.assertNotIn('faculty/', label, key)
            self.assertNotIn('0-168', label, key)

    def test_every_field_spec_still_parses_to_a_kind(self):
        for table, (_, _, fields) in TABLES.items():
            for key, description in fields.items():
                parts = description.split('|')
                self.assertTrue(parts[0], (table, key))
                kind = parts[1] if len(parts) > 1 and parts[1] else 'str'
                self.assertIn(kind.rstrip('?'),
                              ['str', 'date', 'datetime', 'int', 'decimal'], (table, key))


class DisplayTests(unittest.TestCase):
    def rows(self, columns, count):
        return [{c: f'{c[:2].upper()}{i}' for c in columns} for i in range(count)]

    def capture(self, rows, columns_width=100):
        buffer = io.StringIO()
        old = sys.stdout
        try:
            with redirect_stdout(buffer):
                display_rows(rows)
        finally:
            sys.stdout = old
        return buffer.getvalue()

    def test_wide_report_stays_a_table_instead_of_one_block_per_row(self):
        columns = ['导师编号', '导师姓名', '被指导者编号', '被指导者姓名',
                   '项目编号', '标题', '指导开始日', '指导结束日']
        rows = [{c: '2020-09-01' if '日' in c else 'F001' for c in columns} for _ in range(40)]
        out = self.capture(rows)
        self.assertNotIn('── 记录 40 ──', out)
        self.assertIn(' | ', out)
        self.assertIn('共 40 条记录。', out)
        # 40 rows must not explode into hundreds of lines.
        self.assertLess(len(out.splitlines()), 100)

    def test_narrow_terminal_falls_back_to_records_without_losing_values(self):
        columns = ['usage_id', 'member_id', 'equipment_id', 'device_number',
                   'started_at', 'ended_at', 'purpose']
        rows = [{'usage_id': 'U001', 'member_id': 'S001', 'equipment_id': 'E001',
                 'device_number': 'device01', 'started_at': '2024-01-15 09:00:00',
                 'ended_at': '2024-01-15 10:00:00', 'purpose': '数据库基准第一阶段'}]
        import shutil
        original = shutil.get_terminal_size
        shutil.get_terminal_size = lambda fallback=None: __import__('os').terminal_size((40, 24))
        try:
            out = self.capture(rows)
        finally:
            shutil.get_terminal_size = original
        self.assertIn('── 记录 1 ──', out)
        self.assertIn('2024-01-15 09:00:00', out)

    def test_empty_result_is_reported(self):
        self.assertIn('无匹配记录。', self.capture([]))

    def test_piped_output_is_never_paginated(self):
        rows = self.rows(['a', 'b'], 200)
        out = self.capture(rows)
        self.assertNotIn('回车继续', out)
        self.assertIn('共 200 条记录。', out)

    def test_device_list_pretty_format(self):
        formatted = pretty([{'device_number': 'device01', 'status': 'in_use', 'purchase_date': '2023-01-10'}])
        self.assertIn('device01', formatted)
        self.assertIn('in_use', formatted)
        self.assertNotIn('{', formatted)
        self.assertEqual(pretty([]), '无')


if __name__ == '__main__':
    unittest.main()

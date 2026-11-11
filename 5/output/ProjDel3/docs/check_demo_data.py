"""Read-only drift check for the default demonstration schema.

Classroom demos deliberately add and delete rows. This check reports when the
default schema no longer matches the independent reference fixture, without
ever modifying, clearing, or re-seeding user data. It is advisory: exit code is
always 0 so `sh start.sh check` stays usable after a demo.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_lab.db import connect
from research_lab.web import table_counts


def main():
    reference = json.loads(
        (ROOT / 'evidence' / 'sample_reference.json').read_text(encoding='utf-8')
    )['table_counts']
    with connect() as conn:
        live = table_counts(conn)
    diffs = {name: (expected, live.get(name))
             for name, expected in reference.items() if live.get(name) != expected}
    if diffs:
        print(f'提示：演示 schema 与参考答案有 {len(diffs)} 处差异（不影响程序功能）：')
        for name, (expected, actual) in sorted(diffs.items()):
            print(f'  {name}: 参考 {expected}，当前 {actual}')
        print('如需完全一致，用新 schema 初始化：python app.py --schema <新名称> --init；'
              '现有数据不会被自动覆盖。')
    else:
        print(f'演示数据一致性：{len(reference)} 张表、'
              f'{sum(live.values())} 条元组，与参考答案一致。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

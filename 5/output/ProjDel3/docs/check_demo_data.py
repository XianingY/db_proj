"""Read-only drift check for the default demonstration schema.

Classroom demos deliberately add and delete rows. This check reports when the
default schema no longer matches the independent reference fixture (both table
counts and all ten report outputs / key sample witnesses), without ever
modifying, clearing, or re-seeding user data. It is advisory: exit code is
always 0 so `sh start.sh check` stays usable after a demo.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_lab.db import connect
from research_lab.reports import run_report
from research_lab.web import table_counts


def _normalized(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def main():
    reference = json.loads(
        (ROOT / 'evidence' / 'sample_reference.json').read_text(encoding='utf-8')
    )
    ref_counts = reference['table_counts']
    with connect() as conn:
        live = table_counts(conn)
        report_diffs = []
        for name, expected in reference['reports'].items():
            actual = _normalized(run_report(conn, name, tuple(expected['params'])))
            if actual != expected['rows']:
                report_diffs.append(name)
        p001_budgets = [
            str(r['budget']) for r in conn.execute(
                "SELECT budget FROM research_grant WHERE project_id = 'P001' ORDER BY grant_id"
            ).fetchall()
        ]
    count_diffs = {name: (expected, live.get(name))
                   for name, expected in ref_counts.items() if live.get(name) != expected}
    witness_ok = (p001_budgets == ['250000.50', '150000.50', '150000.50'])

    if count_diffs or report_diffs or not witness_ok:
        print('提示：演示 schema 与最新参考答案存在差异（不影响程序功能）：')
        for name, (expected, actual) in sorted(count_diffs.items()):
            print(f'  表行数 {name}: 参考 {expected}，当前 {actual}')
        if report_diffs:
            print('  报表结果不一致：' + ', '.join(sorted(report_diffs)))
        if not witness_ok:
            print(f'  样例见证漂移：P001 资助金额当前为 {p001_budgets}（参考为 250000.50 / 150000.50 / 150000.50）')
        print('如需与最新样例完全一致，请用新 schema 初始化：sh start.sh fresh research_lab_demo2；'
              '现有数据不会被自动覆盖。')
    else:
        print(f'演示数据一致性：{len(ref_counts)} 张表、'
              f'{sum(live.values())} 条元组，十项报表与样例见证均与参考答案一致。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

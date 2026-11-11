"""Practical three-level Chinese terminal menus; all writes use LabService."""
import json
import shutil
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import psycopg
from psycopg import sql

from .reports import REPORTS, run_report
from .service import LabService, TABLES, SUBCLASSES


LABELS = {key: value.split('|')[0] for _, _, fields in TABLES.values()
          for key, value in fields.items()}
LABELS.update(title='标题', full_name='姓名', status='状态', leader_name='负责人姓名',
    total_funding_usd='总资助 USD', mentor_id='导师编号', mentor_name='导师姓名',
    mentee_id='被指导者编号', mentee_name='被指导者姓名', publication_count='成果数',
    grant_count='资助数', device_count='装置数', available_device_count='可用数',
    in_use_device_count='使用中数', retired_device_count='退役数', devices='装置明细',
    mentorship_start_date='指导开始日', mentorship_end_date='指导结束日')


def parse_value(value, field_type='str'):
    nullable = field_type.endswith('?')
    kind = field_type.rstrip('?')
    if value.upper() == 'NULL' or not value:
        if nullable:
            return None
        raise ValueError('此字段不能为空')
    try:
        if kind == 'date':
            return date.fromisoformat(value)
        if kind == 'datetime':
            result = datetime.fromisoformat(value)
            if result.tzinfo is not None or result.microsecond:
                raise ValueError('使用时刻须为北京时间、精确到秒，不附时区或小数秒')
            return result
        if kind == 'int':
            return int(value)
        if kind == 'decimal':
            result = Decimal(value)
            if not result.is_finite():
                raise ValueError('数值必须有限，不能为 NaN 或 Infinity')
            return result
        return value
    except (ValueError, InvalidOperation) as error:
        raise ValueError(f'无效 {kind} 输入：{value}；{error}') from error


def pretty(value):
    if value is None:
        return 'NULL'
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    if isinstance(value, (dict,list)):
        return json.dumps(value,ensure_ascii=False,default=str)
    return str(value).replace('\n',' ')


# A column never gets narrower than this, so IDs and dates stay legible.
MIN_COLUMN_WIDTH = 5
# Header text may wrap, but only after every column already has room for its data.
HEADER_WIDTH_CAP = 12
# Short ASCII values (timestamps, enums) are kept whole instead of split at spaces.
HARD_TOKEN_LIMIT = 24


def width(value):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in value)


def tokens(value):
    """Split into unbreakable units: CJK characters break freely, ASCII runs do not.

    Keeps `2020-09-01` and `collaborator` on one line instead of splitting them
    mid-token, which is what makes a narrow terminal table still readable.
    """
    units, buffer = [], ''
    for character in value:
        if unicodedata.east_asian_width(character) in 'WF':
            if buffer:
                units.append(buffer)
                buffer = ''
            units.append(character)
        elif character == ' ':
            if buffer:
                units.append(buffer)
                buffer = ''
            units.append(' ')
        else:
            buffer += character
    if buffer:
        units.append(buffer)
    return units or ['']


def minimum_width(value):
    """Narrowest width that still avoids breaking an indivisible token.

    A short pure-ASCII value such as `2024-01-15 09:00:00` is one token, so the
    timestamp column never wraps mid-value; CJK text may still break anywhere.
    """
    if width(value) <= HARD_TOKEN_LIMIT and not any(
            unicodedata.east_asian_width(c) in 'WF' for c in value):
        return width(value)
    return max((width(unit) for unit in tokens(value) if unit.strip()), default=1)


def wrapped(value, maximum):
    lines, line = [], ''
    for unit in tokens(value):
        if line and width(line + unit) > maximum:
            lines.append(line.rstrip())
            line = '' if unit == ' ' else unit
        else:
            line += unit
        while width(line) > maximum:  # a single token longer than the column
            cut = len(line)
            while cut > 1 and width(line[:cut]) > maximum:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    return lines + [line.rstrip()]


def fit_sizes(natural, minimum, budget):
    """Give every column its minimum, then spend the rest on the largest deficits."""
    sizes = [min(n, m) if n < m else m for n, m in zip(natural, minimum)]
    remaining = budget - sum(sizes)
    while remaining > 0:
        deficits = [(natural[i] - sizes[i], -i) for i in range(len(sizes))]
        largest = max(deficits)
        if largest[0] <= 0:
            break
        index = -largest[1]
        sizes[index] += 1
        remaining -= 1
    return sizes


def table_lines(headers, cells, sizes):
    def render(line):
        return ' | '.join(value + ' ' * (sizes[i] - width(value)) for i, value in enumerate(line))
    lines = [render([wrapped(h, sizes[i])[0] for i, h in enumerate(headers)]),
             '-+-'.join('-' * n for n in sizes)]
    header_fragments = [wrapped(h, sizes[i]) for i, h in enumerate(headers)]
    if any(len(f) > 1 for f in header_fragments):
        lines = []
        for depth in range(max(map(len, header_fragments))):
            lines.append(render([f[depth] if depth < len(f) else '' for f in header_fragments]))
        lines.append('-+-'.join('-' * n for n in sizes))
    for row in cells:
        # Wrap instead of truncating: no value is ever silently cut off.
        fragments = [wrapped(value, sizes[i]) for i, value in enumerate(row)]
        for depth in range(max(map(len, fragments))):
            lines.append(render([part[depth] if depth < len(part) else '' for part in fragments]))
    return lines


def record_lines(rows, columns):
    lines = []
    for index, row in enumerate(rows, 1):
        lines.append(f'── 记录 {index} ──')
        for key in columns:
            lines.append(f'  {LABELS.get(key, key)}: {pretty(row[key])}')
    return lines


def emit(lines):
    """Page long output on a real terminal only; pipes and logs get everything."""
    if not sys.stdout.isatty():
        print('\n'.join(lines))
        return
    page = max(8, shutil.get_terminal_size((100, 24)).lines - 3)
    for start in range(0, len(lines), page):
        print('\n'.join(lines[start:start + page]))
        remaining = len(lines) - start - page
        if remaining <= 0:
            return
        try:
            answer = input(f'── 还有 {remaining} 行，回车继续 / q 回车跳过 ── ')
        except EOFError:
            return
        if answer.strip().lower() == 'q':
            return


def display_rows(rows):
    """Print rows as a table when the terminal is wide enough, else per record.

    Widths follow the live terminal, so a nine-column report stays a table
    instead of turning into one vertical block per row.
    """
    if not rows:
        print('无匹配记录。')
        return
    columns = list(rows[0])
    headers = [LABELS.get(key, key) for key in columns]
    cells = [[pretty(row[key]) for key in columns] for row in rows]
    available = max(40, shutil.get_terminal_size((100, 24)).columns - 2)
    natural = [max(width(headers[i]), *(width(row[i]) for row in cells))
               for i in range(len(columns))]
    data_floor = [max(MIN_COLUMN_WIDTH,
                      minimum_width(headers[i]),
                      *(minimum_width(row[i]) for row in cells)) for i in range(len(columns))]
    # First try to keep every header on one line; only if that cannot fit do we
    # let headers wrap, and only as a last resort fall back to one block per row.
    header_floor = [max(floor, min(width(headers[i]), HEADER_WIDTH_CAP))
                    for i, floor in enumerate(data_floor)]
    separators = 3 * (len(columns) - 1)
    budget = available - separators
    for floor in (header_floor, data_floor):
        if sum(max(f, m) for f, m in zip(floor, data_floor)) > budget:
            continue
        sizes = fit_sizes(natural, [max(f, m) for f, m in zip(floor, data_floor)], budget)
        if sum(sizes) + separators <= available:
            emit(table_lines(headers, cells, sizes))
            break
    else:
        emit(record_lines(rows, columns))
    print(f'共 {len(rows)} 条记录。')


class Terminal:
    def __init__(self,conn):
        self.conn = conn
        self.service = LabService(conn)

    def fields(self,table,skip=(),old=None):
        result = {}
        keys = TABLES[table][1]
        for key,description in TABLES[table][2].items():
            if key in skip or (old is not None and (key in keys or
                (table=='lab_member' and key=='member_type'))):
                continue
            parts = description.split('|')
            label = parts[0]
            kind = parts[1] if len(parts) > 1 and parts[1] else 'str'
            hint = f'（{parts[2]}）' if len(parts) > 2 and parts[2] else ''
            suffix = f' [{pretty(old[key])}] 留空保留' if old is not None else ''
            while True:
                value = input(f'{label} ({key}){hint}{suffix}: ').strip()
                if old is not None and not value:
                    break
                try:
                    result[key] = parse_value(value,kind)
                    break
                except ValueError as error:
                    print(error)
        return result

    def key(self,table):
        return tuple(input(f'{LABELS.get(key,key)} ({key}): ').strip()
                     for key in TABLES[table][1])

    def add(self,table):
        data = self.fields(table)
        if table=='lab_member':
            subtype_table = SUBCLASSES.get(data['member_type'])
            if not subtype_table:
                raise ValueError('成员类型须为 faculty/student/collaborator')
            child = self.fields(subtype_table,skip=('member_id',))
            participations = []
            print('新增成员至少参与一个现有项目；编号可先通过项目查询菜单取得。')
            while True:
                participations.append(self.fields('project_participation',skip=('member_id',)))
                if input('继续添加参与项目？[y/N]: ').strip().lower()!='y':
                    break
            self.service.create_member(data,child,participations)
        elif table=='research_project':
            self.service.create_project(data,[])
            print('已同时建立负责人参与记录（负责人角色，初始每周 0 小时，可在参与菜单修改）。')
        elif table=='equipment':
            print('同时新增第一台装置，初始状态通常填 available；更多装置在装置菜单新增。')
            device = self.fields('device',skip=('equipment_id',))
            self.service.create_equipment(data,[device])
        elif table=='publication':
            authors = [v.strip() for v in input('作者成员编号（逗号分隔，至少一个）: ').split(',') if v.strip()]
            self.service.create_publication(data,list(dict.fromkeys(authors)))
        else:
            self.service.create_record(table,data)

    def guard(self,operation):
        try:
            operation()
        except (ValueError,KeyError,psycopg.Error) as error:
            detail = error.diag.message_primary if isinstance(error,psycopg.Error) else str(error)
            print(f'操作失败：{detail}。本次写入已回滚，原数据不变。')

    def crud(self,table):
        label = TABLES[table][0]
        while True:
            print(f'\n【{label}管理】\n1 查询（全表/关键词）\n2 新增\n3 修改\n4 删除\n0 返回')
            choice = input('请选择: ').strip()
            if choice=='0':
                return
            def action():
                if choice=='1':
                    keyword = input('查询关键词（空=全部；可输入编号、姓名等）: ').strip()
                    display_rows(self.service.list_rows(table,keyword))
                elif choice=='2':
                    self.add(table)
                    print('操作成功：新增已提交。')
                elif choice=='3':
                    key = self.key(table)
                    old = self.service.get_record(table,key)
                    if old is None:
                        raise ValueError('未找到记录')
                    print('空输入=不变；可空字段输入 NULL=清除。编号与成员类型不可改。')
                    changes = self.fields(table,old=old)
                    self.service.update_record(table,key,changes)
                    print('操作成功：修改已提交。' if changes else '没有修改字段。')
                elif choice=='4':
                    key = self.key(table)
                    old = self.service.get_record(table,key)
                    if old is None:
                        raise ValueError('未找到记录')
                    display_rows([old])
                    print('删除主实体时，同时清除该对象的参与/作者/使用等依赖记录；')
                    print('若破坏其余对象的必需关系会整体拒绝，负责人须先更换。')
                    if input('确认删除请输入 DELETE，其余输入取消: ').strip()!='DELETE':
                        print('已取消删除。')
                        return
                    self.service.delete_record(table,key)
                    print('操作成功：删除已提交。')
                else:
                    print('无效选项。')
            self.guard(action)

    def report(self,name):
        definition = REPORTS[name]
        params = []
        for key in definition['params']:
            if key=='end_before':
                while True:
                    try:
                        params.append(parse_value(input('截止日期 X（YYYY-MM-DD，严格早于）: ').strip(),'date'))
                        break
                    except ValueError as error:
                        print(error)
            else:
                params.append(input(f'{LABELS.get(key,key)} ({key}): ').strip())
        print(f'\n【{definition["title"]}】')
        display_rows(run_report(self.conn,name,tuple(params)))

    def submenu(self,title,choices):
        while True:
            print(f'\n【{title}】')
            for key,(label,_,_) in choices.items():
                print(f'{key} {label}')
            print('0 返回主菜单')
            choice = input('请选择: ').strip()
            if choice=='0':
                return
            if choice not in choices:
                print('无效选项。')
                continue
            _,kind,name = choices[choice]
            if kind=='crud':
                self.crud(name)
            else:
                self.guard(lambda:self.report(name))

    def run(self):
        first = {
            '1':('成员管理','crud','lab_member'), '2':('项目管理','crud','research_project'),
            '3':('显示项目状态','report','project_status'),
            '4':('按资助查询项目参与成员','report','grant_members'),
            '5':('同项目成员指导关系','report','shared_project_mentorship'),
            '6':('项目参与管理','crud','project_participation'),
            '7':('教师资料管理','crud','faculty'), '8':('学生资料管理','crud','student'),
            '9':('合作者资料管理','crud','external_collaborator'),
            '10':('指导关系管理','crud','mentorship')}
        second = {
            '1':('设备管理','crud','equipment'), '2':('使用记录管理','crud','equipment_usage'),
            '3':('显示设备状态','report','equipment_status'),
            '4':('当前使用成员及其项目','report','equipment_current_users'),
            '5':('具体装置管理','crud','device')}
        third = {
            '1':('项目资助总额 Top5（USD）','report','top_funded_projects'),
            '2':('被指导者成果最多的导师（含全部并列）','report','mentor_publications'),
            '3':('专业/年份学生成果统计','report','student_publications_by_major_year'),
            '4':('日期 X 前结束项目及资助数','report','ended_projects'),
            '5':('学生成果最丰富 Top3 年份','report','top_student_years'),
            '6':('资助管理','crud','research_grant'), '7':('成果管理','crud','publication'),
            '8':('成果作者管理','crud','authorship')}
        while True:
            print('\n╔ 科研实验室管理系统 · Deliverable 3 ╗\n1 项目与成员管理\n2 设备使用跟踪\n3 资助与成果报告\n0 退出')
            choice = input('请选择: ').strip()
            if choice=='0':
                print('再见。')
                return
            menus = {'1':('项目与成员管理',first), '2':('设备使用跟踪',second),
                     '3':('资助与成果报告',third)}
            if choice not in menus:
                print('无效选项。')
                continue
            self.submenu(*menus[choice])


def demo(conn):
    print('Research Lab Manager D3 · 只读 SQL 演示 · Budget=USD')
    print('时区 Asia/Shanghai；设备当前使用由未结束记录判定。')
    for table,(label,_,_) in TABLES.items():
        n = conn.execute(sql.SQL('SELECT COUNT(*) AS n FROM {}').format(sql.Identifier(table))).fetchone()['n']
        print(f'{table} ({label}): {n}')
    defaults = {'project_id':'P001','grant_id':'G001','equipment_id':'E001','end_before':date(2025,1,1)}
    for name,definition in REPORTS.items():
        print(f'\n=== {name} | {definition["title"]} ===')
        params = tuple(defaults[key] for key in definition['params'])
        if params:
            print('参数:',', '.join(map(str,params)))
        display_rows(run_report(conn,name,params))

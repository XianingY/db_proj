"""Practical three-level Chinese terminal menus; all writes use LabService.

Formatting and input parsing live in display.py; the names are re-exported here
so existing imports (tests, app.py, web.py) keep working unchanged.
"""
from datetime import date

import psycopg

from .display import (HARD_TOKEN_LIMIT, HEADER_WIDTH_CAP, LABELS, MIN_COLUMN_WIDTH,
                      display_rows, emit, fit_sizes, minimum_width, parse_value,
                      pretty, record_lines, table_lines, tokens, width, wrapped)
from .reports import REPORTS, run_report, run_report_all, run_report_filtered
from .service import LabService, TABLES, SUBCLASSES, table_counts


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
        list_all = False
        filter_value = None
        if not definition['params'] and definition.get('filter_param'):
            fp = definition['filter_param']
            raw = input(f'{LABELS.get(fp,fp)} ({fp})，留空列出全部: ').strip()
            if raw:
                filter_value = raw
        for key in definition['params']:
            if key=='end_before':
                while True:
                    try:
                        params.append(parse_value(input('截止日期 X（YYYY-MM-DD，严格早于）: ').strip(),'date'))
                        break
                    except ValueError as error:
                        print(error)
            else:
                suffix = '，留空列出全部' if definition.get('all_sql') else ''
                raw = input(f'{LABELS.get(key,key)} ({key}){suffix}: ').strip()
                if not raw and definition.get('all_sql'):
                    list_all = True
                params.append(raw)
        print(f'\n【{definition["title"]}】')
        if filter_value is not None:
            display_rows(run_report_filtered(self.conn,name,filter_value))
        elif list_all:
            display_rows(run_report_all(self.conn,name))
        else:
            display_rows(run_report(self.conn,name,tuple(params)))

    def member_detail_view(self):
        member_id = input('成员编号 (member_id): ').strip()
        detail = self.service.member_detail(member_id)
        print('\n【成员基本资料】')
        display_rows([detail['member']])
        print(f'\n【子类资料 · {TABLES[detail["subtype_table"]][0]}】')
        display_rows([detail['subtype']] if detail['subtype'] else [])
        print('\n【参与项目】')
        display_rows(detail['participations'])
        if detail['mentor']:
            print('\n【指导老师 / 上级导师】')
            display_rows([detail['mentor']])
        if detail['mentees']:
            print('\n【被指导成员】')
            display_rows(detail['mentees'])

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
            elif kind=='detail':
                self.guard(self.member_detail_view)
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
            '10':('指导关系管理','crud','mentorship'),
            '11':('成员完整详情（含子类与参与）','detail','lab_member')}
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
    counts = table_counts(conn)
    for table,(label,_,_) in TABLES.items():
        print(f'{table} ({label}): {counts[table]}')
    defaults = {'project_id':'P001','grant_id':'G001','equipment_id':'E001','end_before':date(2025,1,1)}
    for name,definition in REPORTS.items():
        print(f'\n=== {name} | {definition["title"]} ===')
        params = tuple(defaults[key] for key in definition['params'])
        if params:
            print('参数:',', '.join(map(str,params)))
        display_rows(run_report(conn,name,params))

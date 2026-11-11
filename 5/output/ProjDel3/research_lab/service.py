"""Atomic business operations, using the exact Deliverable 2 schema."""
from contextlib import contextmanager

from psycopg import sql


# Field type is used by the CLI for strict parsing. '?' means nullable.
TABLES = {
    'lab_member': ('成员', ('member_id',), {
        'member_id':'编号', 'full_name':'姓名', 'member_type':'类型|str|faculty / student / collaborator',
        'join_date':'加入日期|date'}),
    'faculty': ('教师资料', ('member_id',), {'member_id':'成员编号','department':'院系'}),
    'student': ('学生资料', ('member_id',), {'member_id':'成员编号','student_number':'学号',
        'academic_level':'学业阶段','major':'专业'}),
    'external_collaborator': ('合作者资料', ('member_id',), {'member_id':'成员编号',
        'affiliation':'机构','short_cv':'简短履历|str|一段文字即可'}),
    'research_project': ('项目', ('project_id',), {'project_id':'项目编号','title':'标题',
        'start_date':'开始日期|date','end_date':'结束日期|date?|留空表示尚未结束',
        'planned_duration_days':'计划天数|int|大于 0','status':'状态|str|active / completed / paused','leader_id':'负责人编号|str|必须是教师；新增时自动补参与记录'}),
    'project_participation': ('项目参与', ('member_id','project_id'), {'member_id':'成员编号',
        'project_id':'项目编号','project_role':'角色','weekly_hours':'每周工时|decimal|0-168 小时'}),
    'research_grant': ('资助', ('grant_id',), {'grant_id':'资助编号','funding_agency':'资助机构',
        'budget':'预算 USD|decimal|不小于 0，两位小数','start_date':'开始日期|date',
        'expected_duration_days':'预计天数|int|大于 0','reporting_requirements':'报告要求','project_id':'项目编号'}),
    'equipment': ('设备', ('equipment_id',), {'equipment_id':'设备编号','equipment_name':'名称',
        'equipment_type':'类型','manual_location':'手册位置|str|例如 manuals/xxx.pdf'}),
    'device': ('具体装置', ('equipment_id','device_number'), {'equipment_id':'设备编号',
        'device_number':'装置编号|str|设备内唯一，不同设备可重号','purchase_date':'购买日期|date',
        'status':'状态|str|available / in_use / retired'}),
    'equipment_usage': ('设备使用记录', ('usage_id',), {'usage_id':'使用编号','member_id':'成员编号',
        'equipment_id':'设备编号','device_number':'装置编号',
        'started_at':'开始时刻|datetime|YYYY-MM-DD HH:MM:SS 北京时间',
        'ended_at':'结束时刻|datetime?|留空表示仍在使用','purpose':'目的'}),
    'publication': ('学术成果', ('publication_id',), {'publication_id':'成果编号','title':'标题',
        'publication_year':'发表年|int','publication_month':'发表月|int',
        'publication_day':'发表日|int?|只知道年月时填 NULL','venue':'发表场所','doi':'DOI|str?|可空'}),
    'authorship': ('成果作者', ('member_id','publication_id'), {'member_id':'成员编号','publication_id':'成果编号'}),
    'mentorship': ('指导关系', ('mentee_id',), {'mentee_id':'被指导者编号','mentor_id':'指导者编号|str|学生不能指导教师，不能自我指导',
        'start_date':'开始日期|date','end_date':'结束日期|date?|留空表示尚未结束'}),
}
SUBCLASSES = {'faculty':'faculty', 'student':'student', 'collaborator':'external_collaborator'}


class LabService:
    def __init__(self, connection):
        self.conn = connection

    def metadata(self, table):
        if table not in TABLES:
            raise ValueError('未知的表名')
        return TABLES[table]

    def _key_clause(self, table, key):
        keys = self.metadata(table)[1]
        if len(key) != len(keys):
            raise ValueError('主键列数不匹配')
        return sql.SQL(' AND ').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in keys)

    def list_rows(self, table, search=None):
        self.metadata(table)
        query = sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))
        params = ()
        # Wildcards are intentionally passed through: an empty keyword lists
        # all rows, and a literal '%' is an explicit match-everything query in
        # the terminal demo. Escaping here would change the documented search
        # behaviour, so the convention is kept and pinned by a test.
        if search:
            columns = self.metadata(table)[2]
            query += sql.SQL(' WHERE ') + sql.SQL(' OR ').join(
                sql.SQL('CAST({} AS TEXT) ILIKE %s').format(sql.Identifier(c)) for c in columns)
            params = tuple('%'+search+'%' for _ in columns)
        query += sql.SQL(' ORDER BY ') + sql.SQL(',').join(
            sql.Identifier(k) for k in self.metadata(table)[1])
        return self.conn.execute(query, params).fetchall()

    def get_record(self, table, key):
        return self.conn.execute(sql.SQL('SELECT * FROM {} WHERE {}').format(
            sql.Identifier(table), self._key_clause(table,key)),tuple(key)).fetchone()

    @contextmanager
    def atomic(self):
        with self.conn.transaction():
            self.conn.execute('SELECT pg_advisory_xact_lock(1717,3)')
            self.conn.execute('SET CONSTRAINTS ALL DEFERRED')
            yield
            self.conn.execute('SELECT lab_assert_integrity()')
            self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
            # Restore deferred mode so COMMIT re-checks the deferred triggers.
            # Verified with real transactions: a violating row written after
            # IMMEDIATE is rejected at COMMIT in deferred mode, but at INSERT in
            # immediate mode. atomic() has no writes between IMMEDIATE and here,
            # so the 80 tests cannot observe it (reverse-verified); keep this
            # defensive second check rather than changing the commit timing.
            self.conn.execute('SET CONSTRAINTS ALL DEFERRED')

    def _insert(self, table, data):
        allowed = self.metadata(table)[2]
        if not data or set(data) - set(allowed):
            raise ValueError('插入包含未知字段或没有字段')
        columns = list(data)
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
            sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),
            sql.SQL(',').join(sql.Placeholder() for _ in columns))
        self.conn.execute(query,tuple(data[c] for c in columns))

    def create_record(self, table, data):
        if table in ('lab_member','research_project','equipment','publication'):
            raise ValueError('此实体必须使用带必需关系的组合新增操作')
        with self.atomic():
            self._insert(table,data)

    def create_member(self, member, subtype, participations):
        table = SUBCLASSES.get(member.get('member_type'))
        if not table:
            raise ValueError('成员类型只能为 faculty、student、collaborator')
        with self.atomic():
            self._insert('lab_member',member)
            self._insert(table,{**subtype,'member_id':member['member_id']})
            for p in participations:
                self._insert('project_participation',{**p,'member_id':member['member_id']})

    def create_project(self, project, participants):
        with self.atomic():
            self._insert('research_project',project)
            participants = list(participants)
            if not any(p['member_id']==project['leader_id'] for p in participants):
                participants.insert(0,dict(member_id=project['leader_id'],project_role='负责人',weekly_hours=0))
            for p in participants:
                self._insert('project_participation',{**p,'project_id':project['project_id']})

    def create_equipment(self, equipment, devices):
        with self.atomic():
            self._insert('equipment',equipment)
            for d in devices:
                self._insert('device',{**d,'equipment_id':equipment['equipment_id']})

    def create_publication(self, publication, author_ids):
        with self.atomic():
            self._insert('publication',publication)
            for member in author_ids:
                self._insert('authorship',dict(member_id=member,publication_id=publication['publication_id']))

    def update_record(self, table, key, changes):
        name, keys, columns = self.metadata(table)
        if not changes:
            return
        if set(changes) - set(columns) or set(changes) & set(keys):
            raise ValueError('编号主键不可修改，或修改包含未知字段')
        if table == 'lab_member' and 'member_type' in changes:
            raise ValueError('成员类型固定；更新对应子类资料即可')
        with self.atomic():
            self._require_record(table,key)
            self.conn.execute(sql.SQL('UPDATE {} SET {} WHERE {}').format(
                sql.Identifier(table),sql.SQL(',').join(
                    sql.SQL('{}=%s').format(sql.Identifier(c)) for c in changes),
                self._key_clause(table,key)),tuple(changes.values())+tuple(key))

    def _require_record(self, table, key):
        record=self.get_record(table,key)
        if record is None:
            raise ValueError('未找到此记录')
        return record

    def delete_record(self, table, key):
        self.metadata(table)
        with self.atomic():
            self._require_record(table,key)
            identifier=key[0]
            if table == 'lab_member':
                if self.conn.execute('SELECT 1 FROM research_project WHERE leader_id=%s',(identifier,)).fetchone():
                    raise ValueError('成员仍是项目负责人，请先更换负责人并添加其参与记录')
                self.conn.execute('DELETE FROM mentorship WHERE mentor_id=%s OR mentee_id=%s',(identifier,identifier))
                for rel in ['equipment_usage','authorship','project_participation']:
                    self.conn.execute(sql.SQL('DELETE FROM {} WHERE member_id=%s').format(sql.Identifier(rel)),(identifier,))
                for rel in ['faculty','student','external_collaborator']:
                    self.conn.execute(sql.SQL('DELETE FROM {} WHERE member_id=%s').format(sql.Identifier(rel)),(identifier,))
            elif table == 'research_project':
                for rel in ['research_grant','project_participation']:
                    self.conn.execute(sql.SQL('DELETE FROM {} WHERE project_id=%s').format(sql.Identifier(rel)),(identifier,))
            elif table == 'equipment':
                self.conn.execute('DELETE FROM equipment_usage WHERE equipment_id=%s',(identifier,))
                self.conn.execute('DELETE FROM device WHERE equipment_id=%s',(identifier,))
            elif table == 'publication':
                self.conn.execute('DELETE FROM authorship WHERE publication_id=%s',(identifier,))
            self.conn.execute(sql.SQL('DELETE FROM {} WHERE {}').format(
                sql.Identifier(table),self._key_clause(table,key)),tuple(key))

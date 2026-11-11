"""第三阶段只读报表：沿用 D2 的 13 张表、文本编号和上海使用时刻。

预算按第三阶段题意解释为美元，不换算或转为浮点数。所有 SQL 都内嵌于
REPORTS，不读取 SQL 文件、不创建视图，也不依赖本项目的其他模块。
params 是按占位符顺序排列的输入名称；输入值单独交给 psycopg 绑定。
"""

from typing import Any


REPORTS: dict[str, dict] = {
    "project_status": {
        "title": "项目状态",
        "params": ("project_id",),
        "sql": """
            SELECT p.project_id,
                   p.title,
                   p.status,
                   p.start_date,
                   p.end_date,
                   p.planned_duration_days,
                   p.leader_id,
                   leader.full_name AS leader_name
            FROM research_project AS p
            JOIN lab_member AS leader ON leader.member_id = p.leader_id
            WHERE p.project_id = %s
        """,
        "all_sql": """
            SELECT p.project_id,
                   p.title,
                   p.status,
                   p.start_date,
                   p.end_date,
                   p.planned_duration_days,
                   p.leader_id,
                   leader.full_name AS leader_name
            FROM research_project AS p
            JOIN lab_member AS leader ON leader.member_id = p.leader_id
            ORDER BY p.project_id
        """,
    },
    "grant_members": {
        "title": "指定资助项目的参与成员",
        "params": ("grant_id",),
        "sql": """
            SELECT g.grant_id,
                   p.project_id,
                   p.title,
                   m.member_id,
                   m.full_name,
                   m.member_type,
                   pp.project_role,
                   pp.weekly_hours
            FROM research_grant AS g
            JOIN research_project AS p ON p.project_id = g.project_id
            JOIN project_participation AS pp ON pp.project_id = p.project_id
            JOIN lab_member AS m ON m.member_id = pp.member_id
            WHERE g.grant_id = %s
            ORDER BY p.project_id, m.member_id
        """,
    },
    "shared_project_mentorship": {
        "title": "同项目成员的指导关系（含历史记录）",
        "params": (),
        "sql": """
            SELECT ms.mentor_id,
                   mentor.full_name AS mentor_name,
                   ms.mentee_id,
                   mentee.full_name AS mentee_name,
                   p.project_id,
                   p.title,
                   ms.start_date AS mentorship_start_date,
                   ms.end_date AS mentorship_end_date
            FROM mentorship AS ms
            JOIN lab_member AS mentor ON mentor.member_id = ms.mentor_id
            JOIN lab_member AS mentee ON mentee.member_id = ms.mentee_id
            JOIN project_participation AS mentor_pp
              ON mentor_pp.member_id = ms.mentor_id
            JOIN project_participation AS mentee_pp
              ON mentee_pp.member_id = ms.mentee_id
             AND mentee_pp.project_id = mentor_pp.project_id
            JOIN research_project AS p ON p.project_id = mentor_pp.project_id
            ORDER BY ms.mentor_id, ms.mentee_id, p.project_id
        """,
    },
    "equipment_status": {
        "title": "设备的装置状态明细与汇总",
        "params": ("equipment_id",),
        "sql": """
            SELECT e.equipment_id,
                   e.equipment_name,
                   e.equipment_type,
                   e.manual_location,
                   COUNT(d.device_number) AS device_count,
                   COUNT(d.device_number) FILTER (WHERE d.status = 'available')
                       AS available_device_count,
                   COUNT(d.device_number) FILTER (WHERE d.status = 'in_use')
                       AS in_use_device_count,
                   COUNT(d.device_number) FILTER (WHERE d.status = 'retired')
                       AS retired_device_count,
                   COALESCE(
                       jsonb_agg(
                           jsonb_build_object(
                               'device_number', d.device_number,
                               'purchase_date', d.purchase_date,
                               'status', d.status
                           ) ORDER BY d.device_number
                       ) FILTER (WHERE d.device_number IS NOT NULL),
                       '[]'::jsonb
                   ) AS devices
            FROM equipment AS e
            LEFT JOIN device AS d ON d.equipment_id = e.equipment_id
            WHERE e.equipment_id = %s
            GROUP BY e.equipment_id, e.equipment_name,
                     e.equipment_type, e.manual_location
        """,
        "all_sql": """
            SELECT e.equipment_id,
                   e.equipment_name,
                   e.equipment_type,
                   e.manual_location,
                   COUNT(d.device_number) AS device_count,
                   COUNT(d.device_number) FILTER (WHERE d.status = 'available')
                       AS available_device_count,
                   COUNT(d.device_number) FILTER (WHERE d.status = 'in_use')
                       AS in_use_device_count,
                   COUNT(d.device_number) FILTER (WHERE d.status = 'retired')
                       AS retired_device_count,
                   COALESCE(
                       jsonb_agg(
                           jsonb_build_object(
                               'device_number', d.device_number,
                               'purchase_date', d.purchase_date,
                               'status', d.status
                           ) ORDER BY d.device_number
                       ) FILTER (WHERE d.device_number IS NOT NULL),
                       '[]'::jsonb
                   ) AS devices
            FROM equipment AS e
            LEFT JOIN device AS d ON d.equipment_id = e.equipment_id
            GROUP BY e.equipment_id, e.equipment_name,
                     e.equipment_type, e.manual_location
            ORDER BY e.equipment_id
        """,
    },
    "equipment_current_users": {
        "title": "设备当前使用成员及其进行中项目",
        "params": ("equipment_id",),
        "sql": """
            WITH current_usage AS (
                SELECT DISTINCT u.equipment_id, u.device_number, u.member_id
                FROM equipment_usage AS u
                WHERE u.equipment_id = %s
                  AND u.started_at <= (statement_timestamp() AT TIME ZONE 'Asia/Shanghai')
                  AND (u.ended_at IS NULL OR
                       u.ended_at > (statement_timestamp() AT TIME ZONE 'Asia/Shanghai'))
            ), current_projects AS (
                SELECT pp.member_id, p.project_id, p.title
                FROM project_participation AS pp
                JOIN research_project AS p ON p.project_id = pp.project_id
                WHERE p.status = 'active'
            )
            SELECT cu.equipment_id,
                   e.equipment_name,
                   cu.device_number,
                   m.member_id,
                   m.full_name,
                   p.project_id,
                   p.title
            FROM current_usage AS cu
            JOIN equipment AS e ON e.equipment_id = cu.equipment_id
            JOIN lab_member AS m ON m.member_id = cu.member_id
            LEFT JOIN current_projects AS p ON p.member_id = m.member_id
            ORDER BY cu.equipment_id, cu.device_number, m.member_id, p.project_id
        """,
    },
    "top_funded_projects": {
        "title": "资助总额最高的五个项目（美元）",
        "params": (),
        "sql": """
            SELECT p.project_id,
                   p.title,
                   COALESCE(SUM(g.budget), 0) AS total_funding_usd
            FROM research_project AS p
            LEFT JOIN research_grant AS g ON g.project_id = p.project_id
            GROUP BY p.project_id, p.title
            ORDER BY total_funding_usd DESC, p.project_id ASC
            LIMIT 5
        """,
    },
    "mentor_publications": {
        "title": "被指导者成果最多的导师（全部并列）",
        "params": (),
        "sql": """
            WITH mentor_totals AS (
                SELECT ms.mentor_id,
                       mentor.full_name AS mentor_name,
                       COUNT(DISTINCT a.publication_id) AS publication_count
                FROM mentorship AS ms
                JOIN lab_member AS mentor ON mentor.member_id = ms.mentor_id
                LEFT JOIN authorship AS a ON a.member_id = ms.mentee_id
                GROUP BY ms.mentor_id, mentor.full_name
            )
            SELECT mentor_id, mentor_name, publication_count
            FROM mentor_totals
            WHERE publication_count = (
                SELECT MAX(publication_count) FROM mentor_totals
            )
            ORDER BY mentor_id
        """,
    },
    "student_publications_by_major_year": {
        "title": "按专业及发表年份统计学生成果",
        "params": (),
        "sql": """
            SELECT s.major,
                   p.publication_year,
                   COUNT(DISTINCT p.publication_id) AS publication_count
            FROM student AS s
            JOIN authorship AS a ON a.member_id = s.member_id
            JOIN publication AS p ON p.publication_id = a.publication_id
            GROUP BY s.major, p.publication_year
            ORDER BY s.major, p.publication_year
        """,
    },
    "ended_projects": {
        "title": "指定日期之前结束的项目及资助数量",
        "params": ("end_before",),
        "sql": """
            SELECT p.project_id,
                   p.title,
                   p.end_date,
                   COUNT(g.grant_id) AS grant_count
            FROM research_project AS p
            LEFT JOIN research_grant AS g ON g.project_id = p.project_id
            WHERE p.end_date < %s::date
            GROUP BY p.project_id, p.title, p.end_date
            ORDER BY p.end_date, p.project_id
        """,
    },
    "top_student_years": {
        "title": "学生成果最多的三个年份",
        "params": (),
        "sql": """
            SELECT p.publication_year,
                   COUNT(DISTINCT p.publication_id) AS publication_count
            FROM publication AS p
            JOIN authorship AS a ON a.publication_id = p.publication_id
            JOIN student AS s ON s.member_id = a.member_id
            GROUP BY p.publication_year
            ORDER BY publication_count DESC, p.publication_year DESC
            LIMIT 3
        """,
    },
}


def _fetch_rows(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute one read-only statement and return dict rows, closing only our cursor."""
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def run_report_all(conn: Any, name: str) -> list[dict[str, Any]]:
    """List-all variant used when the terminal leaves the parameter empty."""
    report = REPORTS[name]
    if 'all_sql' not in report:
        raise ValueError(f'报表 {name} 没有列出全部的变体')
    return _fetch_rows(conn, report['all_sql'])


def run_report(
    conn: Any, name: str, params: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    """使用调用方的 psycopg 连接执行报表，返回字典行列表。

    未知键抛出 KeyError，参数数量错误抛出 ValueError；查询无结果返回 []。
    参数按 REPORTS[name]["params"] 的顺序传入，日期使用 date 或 ISO 日期串。
    只关闭本次游标，不提交、回滚或关闭连接；数据库异常交由调用方处理。
    延迟导入 psycopg，使纯 SQL 注册表在未安装驱动时也可独立读取。
    """
    report = REPORTS[name]
    if len(params) != len(report["params"]):
        raise ValueError(
            f"报表 {name} 需要 {len(report['params'])} 个参数"
            f"（{', '.join(report['params']) or '无'}），收到 {len(params)} 个"
        )

    return _fetch_rows(conn, report["sql"], params)

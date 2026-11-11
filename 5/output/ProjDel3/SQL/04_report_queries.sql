-- 第三阶段十项只读报表，与 research_lab/reports.py 的 REPORTS 一一对应。
-- 直接查询 D2 的 13 张表；本文件不创建视图、不改结构、不引用其他 SQL 文件。
-- 附加只读视图见 SQL/05_views.sql，仅作 psql 演示入口，不影响本文件口径。
-- 编号保持文本；budget 按第三阶段题意解释为美元，不做汇率换算。
-- equipment_usage 的无时区时间戳保存上海本地时刻，使用区间为 [start, end)。
-- Python 使用 %s 和独立参数绑定。本文件使用 psql 的安全字面量变量语法
-- :'变量名'，不要改成未加引号的 :变量名，也不要手工拼接用户输入。
-- 执行前设置四个变量，例如在 psql 中：
--   \set project_id 'P001'
--   \set grant_id 'G001'
--   \set equipment_id 'E001'
--   \set end_before '2026-01-01'
-- 或命令行：psql -v project_id=P001 -v grant_id=G001 -v equipment_id=E001
--                  -v end_before=2026-01-01 -f SQL/04_report_queries.sql
-- 下方的 report 标记是固定模块键；中文说明与统计口径均写在相应查询前。

-- report: project_status
-- 项目不存在时返回零行，而不是构造一行空值。
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
WHERE p.project_id = :'project_id';

-- report: grant_members
-- 给定 grant 只关联其所属项目，再按参与关系列出成员。
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
WHERE g.grant_id = :'grant_id'
ORDER BY p.project_id, m.member_id;

-- report: shared_project_mentorship
-- 双方必须参与同一 project；不按指导结束日期过滤，保留保存的历史记录。
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
ORDER BY ms.mentor_id, ms.mentee_id, p.project_id;

-- report: equipment_status
-- equipment 本身没有 status：汇总三种装置状态数量，并保留每台装置明细。
-- 不连接使用记录，避免使用次数放大装置数量；零装置时 devices 为 []。
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
WHERE e.equipment_id = :'equipment_id'
GROUP BY e.equipment_id, e.equipment_name,
         e.equipment_type, e.manual_location;

-- report: equipment_current_users
-- 以本条语句执行时刻转换为上海无时区时间，避免依赖会话 TimeZone。
-- 开始边界纳入，结束边界排除；未来开始和零长度使用不会算作当前使用。
-- 先去重装置/成员，再列其正在进行(status='active')的参与项目。
-- LEFT JOIN 保留没有进行中项目的当前使用成员，其 project_id/title 为 NULL。
WITH current_usage AS (
    SELECT DISTINCT u.equipment_id, u.device_number, u.member_id
    FROM equipment_usage AS u
    WHERE u.equipment_id = :'equipment_id'
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
ORDER BY cu.equipment_id, cu.device_number, m.member_id, p.project_id;

-- report: top_funded_projects
-- 只连接项目与资助，不连接成员/成果；不使用 SUM(DISTINCT budget)，
-- 因为不同资助可能金额相同。零资助保留为 0，同额按 project_id 稳定选五项。
SELECT p.project_id,
       p.title,
       COALESCE(SUM(g.budget), 0) AS total_funding_usd
FROM research_project AS p
LEFT JOIN research_grant AS g ON g.project_id = p.project_id
GROUP BY p.project_id, p.title
ORDER BY total_funding_usd DESC, p.project_id ASC
LIMIT 5;

-- report: mentor_publications
-- 指导者以 mentorship 中实际保存的 mentor_id 为准，不限教师。
-- 包括所有类型 mentee、历史指导及其全部成果，不按指导起止日期截断成果。
-- 同一导师的多个 mentee 合著只算一项；LEFT JOIN 保留成果为零的导师。
-- 返回全部最大值并列；若所有导师都是零，返回所有这些导师。
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
ORDER BY mentor_id;

-- report: student_publications_by_major_year
-- 同专业学生合著在该专业/年份内只计一项；跨专业成果各专业分别计一项。
SELECT s.major,
       p.publication_year,
       COUNT(DISTINCT p.publication_id) AS publication_count
FROM student AS s
JOIN authorship AS a ON a.member_id = s.member_id
JOIN publication AS p ON p.publication_id = a.publication_id
GROUP BY s.major, p.publication_year
ORDER BY s.major, p.publication_year;

-- report: ended_projects
-- 严格早于输入 DATE（等于不算）；NULL end_date 自动排除。
-- COUNT(grant_id) 而非 COUNT(*)，使没有资助的结束项目计为 0。
SELECT p.project_id,
       p.title,
       p.end_date,
       COUNT(g.grant_id) AS grant_count
FROM research_project AS p
LEFT JOIN research_grant AS g ON g.project_id = p.project_id
WHERE p.end_date < :'end_before'::date
GROUP BY p.project_id, p.title, p.end_date
ORDER BY p.end_date, p.project_id;

-- report: top_student_years
-- 每年在所有学生作者之间全局去重，不计作者数，也不累加各专业的数量。
-- 数量相同按年份 DESC 稳定选择三年，不扩展第三名并列。
SELECT p.publication_year,
       COUNT(DISTINCT p.publication_id) AS publication_count
FROM publication AS p
JOIN authorship AS a ON a.publication_id = p.publication_id
JOIN student AS s ON s.member_id = a.member_id
GROUP BY p.publication_year
ORDER BY publication_count DESC, p.publication_year DESC
LIMIT 3;

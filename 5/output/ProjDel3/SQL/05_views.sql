-- 附加只读视图：落实课件视图章节，给 psql 演示提供附加入口。
-- 十项报表仍直接查询基表（见 04 的文件头），视图不改变任何报表口径。
-- 当前使用以未结束记录判定，与 equipment_current_users 同一语义。

CREATE VIEW v_project_total_funding AS
SELECT p.project_id,
       p.title,
       COALESCE(SUM(g.budget), 0) AS total_funding_usd
FROM research_project AS p
LEFT JOIN research_grant AS g ON g.project_id = p.project_id
GROUP BY p.project_id, p.title;

CREATE VIEW v_device_current_usage AS
SELECT u.equipment_id,
       u.device_number,
       u.member_id,
       m.full_name AS member_name,
       u.started_at,
       u.purpose
FROM equipment_usage AS u
JOIN lab_member AS m ON m.member_id = u.member_id
WHERE u.ended_at IS NULL
  AND u.started_at <= (statement_timestamp() AT TIME ZONE 'Asia/Shanghai');

CREATE VIEW v_student_publication_years AS
SELECT s.major,
       p.publication_year,
       COUNT(DISTINCT p.publication_id) AS publication_count
FROM student AS s
JOIN authorship AS a ON a.member_id = s.member_id
JOIN publication AS p ON p.publication_id = a.publication_id
GROUP BY s.major, p.publication_year;

CREATE VIEW v_mentor_publication_totals AS
SELECT ms.mentor_id,
       m.full_name AS mentor_name,
       m.member_type AS mentor_type,
       COUNT(DISTINCT a.publication_id) AS publication_count
FROM mentorship AS ms
JOIN lab_member AS m ON m.member_id = ms.mentor_id
LEFT JOIN authorship AS a ON a.member_id = ms.mentee_id
GROUP BY ms.mentor_id, m.full_name, m.member_type;

# 关系代数与十项报表 SQL 的对应（加分项）

本文件是报告附录 B 的完整符号版本。依据课件 `pdf/06(1)-RelationalAlgebra.pdf`：
第 4 页把选择记作 `σC(R)`，投影记作 `π`，连接记作 `⋈`；课件后段把分组聚集记作
script-F `ℱ`（PDF 文本提取为 `F`，例如 `T ← DNO F COUNT(SSN), AVERAGE(SAL) (EMPLOYEE)`），
通用教材把同一运算记作 `γ`，两者同义。本报告为兼容嵌入的中文字体，正文用 `γ`
并以 `JOIN` / `LEFT OUTER JOIN` 文字替代连接符；本文件保留标准 Unicode 记号。

| 记号 | 运算 | SQL 对应 |
| --- | --- | --- |
| `σ<C>` | 选择 | `WHERE` |
| `π<...>` | 投影 | `SELECT` 列表 |
| `⋈<cond>` | θ 连接 | `JOIN ... ON ...` |
| `⟕<cond>` | 左外连接 | `LEFT JOIN ... ON ...` |
| `γ<groups; agg → name>` / `ℱ` | 分组聚集 | `GROUP BY` + `SUM` / `COUNT(DISTINCT ...)` |
| `ρ<...>` | 重命名 | `AS` |

参数写作 `:name`，对应 psycopg 绑定的占位符 `%s`，绝不拼接输入。

## B.1 项目状态：选择、投影与连接

对应 `project_status`（报告 §5.1、附录 A.1）。

```text
π<project_id, title, status, start_date, end_date,
   planned_duration_days, leader_id, full_name>(
  σ<project_id = :project_id>(
    research_project ⋈<leader_id = member_id> lab_member
  )
)
```

- `⋈<leader_id = member_id>` 即 `JOIN lab_member leader ON leader.member_id = p.leader_id`；
  `full_name` 来自负责人所在成员行，SQL 中重命名为 `leader_name`。
- `σ` 对应 `WHERE p.project_id = %s`，`π` 对应 `SELECT` 列表。关系代数只描述结果集合，
  不含显示顺序；该查询最多返回一行。

## B.2 资助总额 Top5：分组聚集与左外连接

对应 `top_funded_projects`（报告 §5.2、附录 A.6）。

```text
γ<project_id, title; SUM(budget) → total_funding_usd>(
  research_project ⟕<project_id = project_id> research_grant
)
```

- `⟕` 保留没有资助的项目，SQL 用 `COALESCE(SUM(g.budget), 0)` 把空和转成 `0`。
- 必须是 `SUM(budget)` 而不是 `SUM(DISTINCT budget)`：两笔金额相同的资助要分别计入。
- `ORDER BY total_funding_usd DESC, project_id ASC` 与 `LIMIT 5` 是 SQL 对排序和截断的
  扩展，关系代数的结果是无序集合，因此不写进 `γ`；第五名并列时按项目编号截断，不扩展。

## B.3 专业 / 年份学生成果：分组去重计数

对应 `student_publications_by_major_year`（报告 §5.4、附录 A.8）。

```text
γ<major, publication_year; COUNT_DISTINCT(publication_id) → publication_count>(
  student ⋈<member_id> authorship ⋈<publication_id> publication
)
```

- `COUNT_DISTINCT` 对应 `COUNT(DISTINCT p.publication_id)`：同专业多名学生合著只计一次，
  跨专业成果在每个相关专业分别计一次，因此各专业数量之和可以大于全局学生成果数。
- 不补零年份，实际输出 22 个非空分组；`mentor_publications` 的「全并列」和
  `top_student_years` 的「全局去重」同样需要聚集后再做比较/截断，属 SQL 扩展，见报告 §5.3、§5.6。

## 为什么选这三项

分别覆盖 `σ`/`π`/`⋈`、`⟕`/`γ`、`γ` 去重计数，正好把课件 ch6 的基本运算与
`08-09(3)-SQLComplexQueries` 的聚集、外连接、去重串起来。十项报表的完整 SQL 仍在报告附录 A，
逐行结果以 `evidence/verification.json` 与 `evidence/sample_reference.json` 为准。

> 字体说明：报告 PDF 使用嵌入 Songti 字体，不含 `⋈`(U+22C8)、`⟕`(U+27D5) 与
> `ℱ`(U+2131) 字形；若直接写入会渲染成缺字。因此报告附录 B 用等价文字记号，
> 本文件保留标准 Unicode 版本，两者语义一致。`docs/verify_documents.py` 已加入
> PDF 文本缺字检查，防止后续改动重新引入该问题。

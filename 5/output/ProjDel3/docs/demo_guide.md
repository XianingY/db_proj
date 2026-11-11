# 课堂演示流程（约 8–10 分钟）

本文件是操作动线；逐分钟讲稿、预期画面与常见提问应答见同目录 `demo_script.md`。

## 评分点速查（给评分者的一页）

| 题目要求 | 演示动作 | 报告章节 | 可核对的证据 |
| --- | --- | --- | --- |
| 本阶段目标、实例创建、应用开发 | 开场说明；`sh start.sh` 一键启动 | §1、§3、§4 | README、start.sh、docker-compose.yml |
| 相对 D2 的结构修订 | 模式页 13 表 / 14 外键；说明预算 USD 约定 | §2.1–2.2 | SQL/01 与 D2 DDL 的 SHA-256 一致性 |
| 课程理论：函数依赖与范式 | 说明子类表、复合键、全键表的 BCNF 判断 | §2.3 | SQL/01_create_tables.sql |
| D1 图外约束在 D3 落实 | 三名上限、拒绝违规删除、装置状态同步 | §2.4、§6 | SQL/02_integrity.sql、unittest.log |
| 菜单 1：成员/项目 CRUD 与 3 项查询 | 菜单一操作 | §4.2、§5.1 | menu_demo.txt |
| 菜单 2：设备/使用 CRUD 与 2 项查询 | 菜单二操作 | §4.2、§5.1 | menu_demo.txt |
| 菜单 3：五项统计 | 逐项运行报表 | §5.2–5.6 | demo_reports.txt、SQL/04_report_queries.sql |
| 样例充足、程序必须能运行 | 模式页各表真实行数；`sh start.sh check` | §3.2、§6.3 | verification.json、package_validation.json |
| 困难与解决理由 | 收尾一分钟复述 | §7 | 报告 §7 |
| 菜单驱动、不必做复杂 GUI | 明确终端为主、网页仅投影辅助 | §1、§4.4 | demo_script.md 对应问答 |
| 期末现场演示 | 本流程 8–10 分钟 | §6.3 | demo_guide.md、demo_script.md |

## 准备

统一入口是 `start.sh`。演示前执行一键启动，它会准备环境、仅在 schema 缺失时初始化并启动演示网页；已就绪的环境不重复安装依赖：

```sh
sh start.sh            # 默认 http://localhost:8000/
sh start.sh check      # 环境与数据自检（含全部自动化测试，当前 80 项）
```

若需手工排障，等价命令为 `sh scripts/bootstrap.sh --check`；环境损坏时去掉 `--check` 重跑，脚本会重建 `.venv`、确认/启动 PostgreSQL 并仅在 schema 缺失时初始化，已存在的 schema 不会被覆盖。随后确认只读报告：

```sh
sh start.sh demo       # 等价于 .venv/bin/python app.py --demo
```

正式展示执行 `sh start.sh menu`（等价于 `.venv/bin/python app.py`），或直接使用 `sh start.sh` 打开的演示网页。存在可用 Docker 时自动使用固化容器，否则自动使用本机环境。

**网页版（投影推荐）**：`sh start.sh` 已启动网页；手工排障时可先 `sh scripts/bootstrap.sh --check`，再另开终端运行
`.venv/bin/python app.py --web`，浏览器打开打印的地址。建议动线：01 模式图悬停任一表高亮外键 →
02 成员表现场新增一名学生再删除（演示 DELETE 确认与回滚提示）→ 04 报表区更换项目/资助/日期 X 重跑 →
06 验证页展示测试数与元组数。网页与终端可二选一，或先网页讲结构、再终端演事务。

**终端宽度**：建议不窄于 100 列。表格按终端宽度自适应——同项目指导关系这类 8 列报表在 100 列下是正常的多行表格，在 80 列下会折表头，太窄时退化为逐条竖排。交互终端下长结果会分页，回车继续、`q` 回车跳过；演示前可先按一次 `q` 熟悉操作，避免现场翻页打断节奏。

## 一、项目与成员（约 2 分钟）

1. 主菜单 1 → 成员管理 → 查询，输入 `S001`；回去项目查询，输入 `P005`。
2. 项目状态输入 `P001`：completed，结束于 2023-12-31。
3. 按资助输入 `G001`：9 名成员。展示同项目指导关系。
4. 成员新增 `DEMO_STU` / 演示学生 / student / 2025-01-01；子类输入 `DEMO2025` / 硕士 / 计算机科学；项目 `P007` / 研究助理 / 6 / n。
5. 修改 DEMO_STU 姓名，其余留空；删除 DEMO_STU，确认 DELETE。
6. 试删除 F001：仍任项目负责人，拒绝；再次查询 F001 证明未丢数据。

## 二、设备（约 2–3 分钟）

1. 主菜单 2 → 状态 → `E001`：两台装置均使用中；当前用户四名，展开 active 项目后五行，S004 没有 active 项目仍保留。
2. 新增设备 `DEMO_EQ` / 演示仪器 / 仪器 / demo_manual.pdf；第一台装置 `01` / 2020-01-01 / available。
3. 新增使用 `DEMO_USE`，成员 S001，设备 DEMO_EQ，装置 01。开始时刻填今天已过去的一小时，北京时间 YYYY-MM-DD HH:MM:SS；结束留空；目的填课堂演示。
4. 查询设备状态：in_use。修改 DEMO_USE 的结束时刻为已经过去、但晚于开始的时刻，状态恢复 available。
5. 修改使用目的，然后删除使用；修改设备名称，然后删除设备。全部需要 DELETE 确认。
6. 若需展示三人上限，可运行并发测试：`python -m unittest discover -s tests -p test_concurrency.py -v`；两名占用后第三人提交，第四人等待后被拒绝。

## 三、五项统计（约 2 分钟）

依次运行主菜单 3 的选项 1–5：

- Top5：P005 = 1000000.75 USD，随后 P002、P001、P006、P003。
- 最多成果导师：F001、F002，各 16 项，体现全并列及共同作者去重。
- 专业/年份统计：22 个有成果的分组；解释跨专业共同作者的计数。
- 截止 `2025-01-01`：P009=0、P001=3、P002=2、P003=2。P004 恰在该日结束，不纳入。
- 年度 Top3：2025=7、2024=6、2023=5。

## 四、证据与收尾

收尾时可在 `psql` 中 `\dv` 展示 4 个附加只读视图（SQL/05_views.sql），说明报表口径不依赖视图。

展示 `evidence/unittest.log`、`verification.json` 及 SQL/03_sample_data.sql 各表 INSERT。程序退出选择 0。演示时自己新增的对象请通过菜单删除；不要重新初始化或 TRUNCATE 默认实例。课程要求期末现场演示及预约时间，提交包不会替代现场演示，也未替你预约。

## 五、现场故障速查

| 现象 | 处置 |
| --- | --- |
| `--web` 报端口占用 | `WEB_PORT=8080 sh start.sh`（等价手工命令：`.venv/bin/python app.py --web --port 0`） |
| 启动报数据库未初始化 | `sh start.sh` 只初始化缺失 schema，不覆盖已有；手工排障用 `sh scripts/bootstrap.sh` |
| PostgreSQL 没起 | 默认 `sh start.sh` 走 Docker 容器；强制本机时 macOS 用 `brew services start postgresql@18`，其他系统 bootstrap 会用 docker/podman 起容器 |
| 终端表格折行难看 | 窗口拉宽到 ≥100 列；网页版不受终端宽度影响 |
| 网页打不开 | 确认服务仍在运行；地址以服务打印的为准，默认仅本机可达 |

# Research Lab Manager · 同组协作指南

本仓库是数据库课程大作业的完整成果：D1 概念设计、D2 逻辑设计、D3 实现与验证，以及课程课件。**本文档面向 clone 仓库的同组组员**；给评分者的交付说明见 `5/output/README.md` 与 `5/output/ProjDel3/README.md`。

当前状态：仓库已关联 `origin`（`git@github.com:XianingY/db_proj.git`）；13 张表 / 385 条样例、80 项自动化测试、26 页中文报告，提交包 59 个文件。

## 1. 30 秒跑起来

```sh
git clone git@github.com:XianingY/db_proj.git
cd db_proj
sh start.sh
```

浏览器打开 `http://localhost:8000/`。根目录的 `start.sh` 只是转发，真正的实现只有一份：`5/output/ProjDel3/start.sh`。

- 有可用的 Docker daemon 时自动使用固化容器（Python 3.13 + PostgreSQL 18）；否则自动回退本机环境。
- 首次需要拉取 `postgres:18` 并构建应用镜像，约 2–3 分钟；中断后重跑同一命令会复用已下载层。
- 已就绪的环境**不会重复安装依赖、不会覆盖已有数据**；每人本地是独立实例（各自数据卷），不共享数据库。

| 命令 | 作用 |
| --- | --- |
| `sh start.sh` | 一键启动课堂演示网页 |
| `sh start.sh menu` | 中文三级终端菜单 |
| `sh start.sh demo` | 十项只读报表 |
| `sh start.sh test` | 全部自动化测试 |
| `sh start.sh check` | 环境与数据自检（含演示数据一致性） |
| `sh start.sh stop` | 停止容器（数据卷保留） |
| `sh start.sh help` | 完整用法与运行时选择 |

## 2. 前置条件与运行时覆盖

| 路径 | 需要 | 不需要 |
| --- | --- | --- |
| Docker（推荐，自动选择） | Docker Desktop + Compose v2 | 本机 Python / PostgreSQL |
| 本机环境（自动回退） | Python 3.10+、PostgreSQL 14+（实测 18.6），uv 可选 | Docker |
| 手工排障 | `scripts/bootstrap.sh` 会自愈重建失效的 `.venv` | 手动逐个 pip 安装 |

```sh
LAB_RUNTIME=docker sh start.sh    # 强制容器
LAB_RUNTIME=native sh start.sh    # 强制本机
WEB_PORT=8080 sh start.sh         # 换端口
```

容器参数可复制 `5/output/ProjDel3/.env.example` 为 `.env` 后修改；`.env` 已被 `.gitignore` 排除，**不要提交真实凭证**。

## 3. 目录导览

| 路径 | 内容 |
| --- | --- |
| `1/` | D1：题目、概念结构报告（md/docx）、两张 EER 图与 drawio 源文件 |
| `3/` | D2：逻辑结构报告 docx、`create_tables.sql`、`ProjDel2.zip` |
| `5/ProjDel3-ResearchLabManager.pdf` | D3 题目原文（2 页） |
| `5/output/ProjDel3/` | 可运行程序、SQL、测试、报告、证据、演示材料 |
| `5/output/ProjDel3.zip` | 完整提交包，评分交付用 |
| `5/output/README.md` | 交付物清单 |
| `pdf/` | 16 份课程课件（ch1–11，含关系代数、FD/NF、模式分解） |
| `start.sh` | 仓库根入口（转发） |
| `README.md` | 本文件 |

`2/`、`4/` 为按要求不入库的个人作业，不在仓库内，不影响运行。本文件**不打进提交包**（打包脚本只扫描 `5/output/ProjDel3/`）。

## 4. 交付物速查

| 用途 | 文件 |
| --- | --- |
| 看报告 | `5/output/ProjDel3/第三次小组作业报告.pdf`（26 页）、`.docx`、`.md` |
| 交作业 | `5/output/ProjDel3.zip` |
| 环境、依赖、配置、手工命令 | `5/output/ProjDel3/README.md` |
| 演示 | `5/output/ProjDel3/docs/demo_guide.md`（评分点速查 + 8–10 分钟流程）、`demo_script.md`（逐分钟讲稿与问答） |
| 验证证据 | `5/output/ProjDel3/evidence/`（`verification.json`、`unittest.log`、独立参考答案、截图） |
| 关系代数加分项 | `5/output/ProjDel3/docs/relational_algebra.md`（报告附录 B 为字体兼容的等价写法） |

## 5. 协作约定（改动前必读）

1. **报告三格式是生成产物**：`docs/build_report.py` 的 `report_blocks()` 统一生成 `.md` / `.docx` / `.pdf`。不要直接手改报告文件，改内容要改生成脚本再重生成；`5/output/README.md` 的页数描述也要同步。
2. **文档校验有硬编码期望值**：`docs/verify_documents.py` 检查 DOCX 表格数（当前 18 张）、PDF 嵌入中文字体、文字边界与缺字 NUL。新增表格或章节时要同步更新期望值，否则校验会失败。
3. **改源码 / SQL / 文档后跑门禁并重新打包**（在 `5/output/ProjDel3/` 目录执行）：
   ```sh
   sh start.sh check
   sh start.sh test
   .venv/bin/python docs/verify_submission.py
   .venv/bin/python docs/build_report.py
   .venv/bin/python docs/verify_documents.py
   .venv/bin/python docs/package_submission.py
   ```
4. **Docker 源码改动**：`start.sh` 为保持幂等不会自动 `--build`。改了 `research_lab/`、`SQL/`、`web/` 之后需在包目录执行 `docker compose up -d --build app`，否则容器仍运行旧镜像。
5. **演示数据**：默认 schema `research_lab_del3` 与 `evidence/sample_reference.json` 一致（13 表 / 385 元组）。课堂演示会增删数据，`sh start.sh check` 会提示漂移但**不会自动改写**。需要干净实例请用新 schema：`python app.py --schema <新名称> --init`。
6. **凭证**：`.env.example` 与 compose 中的 `local-demo-only-change-me` 是本地容器 PostgreSQL 的占位口令，不是真实凭证；仓库已被 GitGuardian 扫描，请勿引入任何 token / API key / 私钥。真实口令放本机 `.env`，或用 `PGPASSWORD` / `.pgpass`。
7. **提交规范**：英文 conventional commits（`type(scope): ...`），每个语义改动一个提交；提交与推送前先确认。`origin` 已关联，`main` 跟踪 `origin/main`；tag `del3-submission` 仍指向较早提交，若按 tag 交付需先确认后更新。

## 6. 常见问题

| 现象 | 处置 |
| --- | --- |
| 8000 端口被占用 | `WEB_PORT=8080 sh start.sh` |
| Docker Desktop 没启动 | 自动回退本机；或启动 Docker 后 `LAB_RUNTIME=docker sh start.sh` |
| `bootstrap.sh --check` 报 `.venv` 不可用 | 直接 `sh start.sh`（不带 `--check`），入口会自愈重建 |
| 首次拉镜像慢或中断 | 重跑 `sh start.sh`，已下载层会复用 |
| 网页写操作返回 403 | 写请求只接受本机 Origin；用 `http://localhost:<port>/` 打开，不要用容器内网地址 |
| 报告生成失败 | 需中文字体 Songti（或 `LAB_REPORT_FONT` 指定 TTF）与 `requirements-docs.txt` 依赖 |
| 想释放容器资源 | `sh start.sh stop`，数据卷保留，下次 `sh start.sh` 直接复用 |

## 7. 期末演示

- 题目要求**现场演示并预约时间**，提交包不能替代演示；预约由小组按课程通知完成。
- 演示前跑 `sh start.sh check`，按 `docs/demo_guide.md` 的评分点速查表逐条走（8–10 分钟），逐分钟话术与常见问答见 `docs/demo_script.md`。
- 三条讲述原则：先用 SHA-256 证明 13 表 / 14 外键与 D2 逐字节一致，再演示功能；把网页定位为投影辅助而非复杂 GUI；每个统计都解释 SQL 口径（`SUM` vs `SUM(DISTINCT)`、`COUNT(DISTINCT)`、严格 `<`、全并列）。

---

先查本文件，需要细节再看 `5/output/ProjDel3/README.md`；命令不确定时运行 `sh start.sh help`。

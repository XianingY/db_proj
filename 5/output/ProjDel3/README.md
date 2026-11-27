# Research Lab Manager — 第三次小组作业

本提交按 `5/ProjDel3-ResearchLabManager.pdf` 完成，直接继承第 2 次**实际提交**的 13 张表、14 个外键及文本编号。不是用个人作业或早期草稿重建的另一套模式。

## 快速开始（推荐）

解压 `ProjDel3.zip` 后进入 `ProjDel3/`；若 clone 整个仓库，则在仓库根目录执行同一条命令（根目录的 `start.sh` 只是转发）：

```sh
sh start.sh            # 一键：准备环境 → 仅缺失时初始化 → 启动演示网页
```

默认访问 `http://localhost:8000/`。入口自动选择运行时：**存在可用的 Docker daemon 时用容器**（Python 3.13 + PostgreSQL 18 固化在镜像，数据卷持久化），否则使用本机环境（自动重建失效的 `.venv`、确认/启动 PostgreSQL、仅在 schema 缺失时初始化）。依赖固化在镜像层或 `.venv`，已就绪的环境**不会重复安装、不会覆盖已有数据**，第二次启动直接可用。

| 命令 | 作用 |
|---|---|
| `sh start.sh` | 一键启动课堂演示网页 |
| `sh start.sh menu` | 中文三级终端菜单 |
| `sh start.sh demo` | 十项只读报表 |
| `sh start.sh test` | 全部自动化测试 |
| `sh start.sh check` | 环境与数据自检 |
| `sh start.sh fresh <schema>` | 初始化一个全新的干净演示 schema（不覆盖默认实例） |
| `sh start.sh stop` | 停止容器（保留数据卷） |
| `sh start.sh help` | 完整用法与运行时选择 |

覆盖默认行为：`LAB_RUNTIME=docker|native sh start.sh`、`WEB_PORT=8080 sh start.sh`；容器参数可复制 `.env.example` 为 `.env` 后修改。Docker 路径只要求 Docker + Compose v2，不需要本机装 Python 或 PostgreSQL；原生路径要求 Python 3.10+ 与 PostgreSQL 14+（本项目实测 18.7）。以下各节保留等价的手工命令，用于理解流程或排障。报告中提到的 `2/`、`4/` 为按要求不入库的个人作业，不在本仓库与提交包内，不影响运行。

## 交付内容

| 文件/目录 | 用途 |
|---|---|
| `第三次小组作业报告.pdf` | 可提交的完整中文报告 |
| `第三次小组作业报告.docx` / `.md` | 可编辑版本 |
| `app.py`、`research_lab/` | 可运行的中文三级菜单程序 |
| `SQL/01_create_tables.sql` | 原第二阶段建表 SQL，逐字节保留 |
| `SQL/02_integrity.sql` | 跨表、设备时间/状态及并发完整性 |
| `SQL/03_sample_data.sql` | 13 张表的显式 INSERT 样例；一个事务全部导入 |
| `SQL/04_report_queries.sql` | 原题全部十项查询，可用 psql 单独执行 |
| `SQL/05_views.sql` | 4 个附加只读视图（psql 中 `\dv` 可见），报表口径不依赖视图 |
| `tests/` | 业务、真实终端、报表、双连接并发测试 |
| `scripts/bootstrap.sh` | 一键准备 Python/PostgreSQL 环境、初始化并自检 |
| `evidence/` | 独立参考答案、真实运行日志、数据库结果和截图 |
| `docs/` | 演示步骤、逐分钟讲稿、生成报告/验证的脚本 |
| `requirements.lock` | 本机验证通过的精确依赖版本，容器镜像按此文件安装，用于逐位复现 |
| `start.sh`、仓库根 `start.sh` | 唯一启动入口（包内实现 + 仓库根转发） |
| `Dockerfile`、`docker-compose.yml`、`.dockerignore` | 固化 Python 3.13 / PostgreSQL 18 运行环境与持久化数据卷 |
| `.env.example`、`scripts/docker-entrypoint.sh` | 统一配置样例、容器幂等初始化 |
| `web/`、`SQL/05_views.sql` | 课堂演示网页三件套与 4 个附加只读视图 |

## 1. 环境与安装

**推荐直接使用 `sh start.sh`**（见「快速开始」），它会自动完成下面全部步骤并跳过已就绪的部分。以下为等价的手工步骤，用于理解流程或排障。

使用 Python 3.10+、PostgreSQL 18、psycopg 3。本次实测为 Python 3.13.18 / PostgreSQL 18.7（macOS）；需要本机或可访问的 PostgreSQL 服务，不能用 SQLite 替代。

**推荐：一键准备（幂等，可反复执行）**

```sh
sh scripts/bootstrap.sh          # 建 .venv + 装依赖 + 确认/启动 PostgreSQL + 初始化 + 自检
sh scripts/bootstrap.sh --check  # 只自检，不安装、不初始化
```

脚本会依次挑选可用的解释器。注意：部分 macOS 上 Homebrew 的 `python3` 虽然存在，
`python3 -m venv` 却会失败（pip 依赖的 libexpat 符号缺失），因此脚本先在临时目录实测
`venv`，全部失败时自动改用 `uv venv --python 3.13`。已存在的 schema 一律不覆盖。

**手工安装**

```sh
uv venv --python 3.13 .venv                       # 或 python3 -m venv .venv（若可用）
.venv/bin/python -m pip install -r requirements.txt
source .venv/bin/activate
```

需要逐位复现已验证环境时，用 `requirements.lock` 替换区间依赖文件
（`uv pip install --python .venv/bin/python -r requirements.lock`），其中区分直接依赖与传递依赖。

先安装并启动 PostgreSQL，确认 `psql -d postgres` 能连接。已有可用数据库可直接复用；也可以创建自己的数据库：

```sh
createdb research_lab
export LAB_DSN='dbname=research_lab'
```

远程/密码连接示例（用户名和地址换成自己的）：

```sh
export LAB_DSN='host=127.0.0.1 port=5432 dbname=research_lab user=lab_user'
# 密码用终端环境变量 PGPASSWORD 或 PostgreSQL 的 .pgpass，不写进代码/提交包。
```

默认连接为 `dbname=postgres`，同时支持标准 PGHOST、PGPORT、PGUSER、PGPASSWORD 环境变量。业务存放在独立的 `research_lab_del3` schema，不使用 public 中的同名表。

### 1.1 统一配置

| 变量 | 默认值 | 作用 |
|---|---|---|
| `LAB_RUNTIME` | `auto` | `docker` / `native` / 自动探测 |
| `WEB_PORT` | `8000` | 演示网页端口（宿主与容器内保持一致） |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `research_lab` / `lab_user` / `local-demo-only-change-me` | 容器数据库凭证，可写入 `.env`；仅为本地演示占位符 |
| `LAB_SCHEMA` | `research_lab_del3` | 专用 schema，已存在时不覆盖 |
| `LAB_DSN` | `dbname=postgres`（容器内指向 `db` 服务） | 连接串；密码用 `PGPASSWORD` 或 `.pgpass`，不写入代码与提交包 |
| `LAB_WEB_HOST` | `127.0.0.1`（容器内 `0.0.0.0`） | 网页监听地址 |
| `LAB_WEB_ALLOWED_ORIGINS` | 空（容器内 localhost / 127.0.0.1 + 端口） | 写请求允许的额外 Origin 白名单 |

`.env.example` 汇总容器可改项，复制为 `.env` 后由 `docker compose` 自动读取。依赖分三层：`requirements.txt`（运行时 psycopg）、`requirements-docs.txt`（报告与文档管线，内含 `-r requirements.txt`）、`requirements.lock`（精确版本；容器镜像按此安装，保证与验证环境一致）。

## 2. 初始化、启动、演示

统一入口：`sh start.sh`（网页）、`sh start.sh menu`（菜单）、`sh start.sh demo`（报表）。下列为等价的手工命令：

```sh
.venv/bin/python app.py --init       # 仅新环境执行一次；已有 schema 会拒绝
.venv/bin/python app.py              # 中文交互菜单
.venv/bin/python app.py --demo       # 十项只读查询及各表计数
```

已 `source .venv/bin/activate` 时可直接写 `python app.py`。

### 2.1 课堂演示网页（投影推荐）

```sh
.venv/bin/python app.py --web            # 默认 http://127.0.0.1:8000/
.venv/bin/python app.py --web --port 0   # 端口被占用时自动选择
```

网页与终端完全同源：新增/修改/删除走同一 `LabService` 事务与回滚规则，十项报表走同一份 SQL；
页面是原生 JS 单页（`web/` 三件套），无框架、无 CDN，教室断网可用。服务默认仅监听 127.0.0.1（容器模式由 `LAB_WEB_HOST=0.0.0.0` 放开回环映射），
不含登录与权限，属课堂演示服务；完整性仍由数据库触发器兜底。模式图、报表参数控件、完整性说明
与验证数字全部来自真实数据库和 `evidence/verification.json`，不是手写文案。

`--init` 只创建**不存在**的 schema。重复初始化会拒绝，不覆盖数据，不隐式清空表。想创建另一套样例，请给新名称，并在后续命令中保持一致：

```sh
python app.py --schema research_lab_demo2 --init
python app.py --schema research_lab_demo2
```

若本机已存在默认专用演示 schema，可直接启动，不必再次 `--init`；全新环境由 `sh start.sh` 或 `sh scripts/bootstrap.sh` 自动初始化。此处环境若未激活 venv，先按安装步骤配置 Python 依赖。

## 3. 菜单与操作

- 主菜单 1：成员/项目 CRUD、项目状态、按资助查询成员、同项目指导（支持按项目筛选）；附带参与/三类成员资料/指导管理及 `11` 成员完整详情。
- 主菜单 2：设备/使用 CRUD、装置状态及设备汇总、当前使用人及进行中项目；附带具体装置管理。
- 主菜单 3：原题五项统计，以及资助/成果/作者 CRUD。
- 表管理：`1 查询 / 2 新增 / 3 修改 / 4 删除 / 0 返回`；查询空关键词显示全表，也可按编号、名称等匹配。
- 课堂演示网页提供同一套功能的图形界面：模式与外键图、三菜单的增删改查、十项参数化报表（附口径与真实 SQL）、完整性与验证页。
- 结果表格按当前终端宽度自适应：优先保证每列数据不被折断（时间戳、`collaborator` 等短 ASCII 值整体保留），宽度不够时先折表头、再退化为逐条竖排，绝不静默截断内容。终端交互时长结果自动分页（回车继续、`q` 回车跳过）；重定向到文件或管道（含 `--demo`、测试、证据日志）时不分页，完整输出。建议演示终端宽度 ≥ 100 列。
- 新增成员必须同时输入对应子类资料和至少一个现有项目；新增项目自动添加负责人参与记录（初始工时 0，可修改）；新增设备同时输入第一台装置；新增成果同时输入作者编号。
- 修改字段时，空输入表示保留原值；可空字段输入 `NULL` 清除。可以一次同时修改状态与结束日期。编号/学号仍为文本，前导零不丢失；主键和成员类型不支持直接改动。
- 时间格式 `YYYY-MM-DD HH:MM:SS`，统一北京时间，不带时区。金额为 USD，采用 Decimal，不使用二进制浮点计算资金。
- 删除显示目标并要求输入 `DELETE` 确认。主实体删除会移除其依赖关系；仍任负责人或导致其他成员没有项目、成果没有作者等时整体回滚。禁止 TRUNCATE 绕过关系检查。
- 变更负责人：先在“项目参与”菜单添加新教师的参与，再修改项目负责人；之后可删除旧负责人不再需要的参与记录。
- 装置 `in_use/available` 随未结束使用自动同步；退役前先结束使用。删除有使用记录的单台装置会被外键拒绝，可先处理记录，或确认删除所属设备及全部依赖。

## 4. 查询口径

- “正在工作的项目”按 `status='active'` 解释；已完成/暂停项目不混入当前设备使用报表。当前使用成员没有 active 项目时保留该人，项目列为 NULL。
- 按给定资助查询成员、同项目指导基于原模式保存的参与记录；原模式不保存完整参与起止历史，不能据此推断已删除的过去工作经历。
- 指导者不限教师，计所有类型被指导者的全部保存成果，包含历史指导；同一导师多个被指导者合著只算一个 publication_id，最大值全并列返回。
- 学生成果按 publication_id 去重；同专业合著计一次，跨专业在各专业分别计一次；年度 Top3 全局去重，不能把专业统计简单相加。
- 日期查询严格 `end_date < X`；零资助项目计 0；Top5/Top3 分别最多五项/三年，同数以项目编号升序/年份降序稳定截断。
- 第 2 阶段报告使用人民币，本阶段按 D3 原题将 Budget **约定为 USD**。这是样例计量单位的修订，不是假装对旧金额做过汇率转换。

## 5. 自动验证

统一入口：`sh start.sh test`（全部测试）、`sh start.sh check`（环境与数据自检）。`check` 还会运行 `docs/check_demo_data.py`：只读比对默认演示 schema 与独立参考答案，课堂演示增删过样例行时给出提示，但**不会自动改写数据**。等价的手工命令：

```sh
sh scripts/bootstrap.sh --check    # 环境与数据自检
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python docs/verify_submission.py
```

测试需要建 schema 和触发器的权限，每次使用随机专用 schema，操作后回滚并只删除自己创建的测试 schema，不清理既有业务实例。`verify_submission.py` 会再创建临时样例，核对十项独立参考结果，执行 SQL 文件与真实终端演示，把证据写入 `evidence/`。

手工执行 SQL 报表（已初始化，默认示例数据库 postgres）：

```sh
PGOPTIONS='-c search_path=research_lab_del3' psql -d postgres -v ON_ERROR_STOP=1 \
  -v project_id=P005 -v grant_id=G001 -v equipment_id=E001 \
  -v end_before=2025-01-01 -f SQL/04_report_queries.sql
```

只读程序报表不要求安装 psql；额外验证脚本执行独立 SQL 文件时才需要 psql 客户端。

## 6. 重新生成文档

```sh
python -m pip install -r requirements-docs.txt
python docs/verify_submission.py
python docs/build_report.py
python docs/verify_documents.py
python docs/package_submission.py
```

PDF 使用嵌入的中文字体。本机自动采用系统 Songti；其他系统需通过 `LAB_REPORT_FONT` 指定支持中文、TrueType 轮廓的 TTF 字体（例如本机已有的中文 TTF），`LAB_REPORT_FONT_BOLD` 可指定粗体。这仅影响重新生成 PDF，阅读提交好的 PDF 不需要安装字体。

## 7. 边界

这是课程用单实验室应用，提供与终端同源的本机演示网页，但不是生产级 Web GUI；不实现登录权限、财务换汇、参与历史或审计恢复。跨表约束使用统一事务锁，适合小型负载，写操作串行化，不适合作为高吞吐多实验室方案。写事务要求 READ COMMITTED；管理员/表所有者有禁用或删除触发器的权限时可绕过保护，应在正式部署中收紧权限。样例均为虚构教学资料，手册字段只是元数据位置，不附带真实仪器手册。

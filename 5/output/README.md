# 第三次小组作业成果

**一键启动**：解压 `ProjDel3.zip` 进入 `ProjDel3/` 后执行 `sh start.sh`（默认 http://localhost:8000/）；有 Docker 时自动使用固化容器，否则自动准备本机环境。`sh start.sh help` 查看全部命令。

- `ProjDel3.zip`：完整提交包，解压后进入 ProjDel3 目录。
- `ProjDel3/第三次小组作业报告.pdf`：21 页中文报告（含要求逐条对照表、14 外键关系一览、逐表函数依赖与 BCNF 判断、7 类图外约束落实映射、网页前端说明、英文摘要、十项 SQL 附录与三项报表的关系代数对照附录）。
- 同目录 `.docx`、`.md`：可编辑报告。
- `ProjDel3/docs/relational_algebra.md`：三项代表性报表的关系代数对照（σ / π / ⋈ / ⟕ / γ 完整符号版，呼应课件 `06(1)-RelationalAlgebra.pdf`；报告附录 B 为字体兼容的等价写法）。
- `ProjDel3/README.md`：安装、初始化、启动与验证说明。
- `ProjDel3/scripts/bootstrap.sh`：一键准备 Python/PostgreSQL 环境、初始化并自检（幂等）。
- `ProjDel3/docs/demo_guide.md` 与 `demo_script.md`：现场演示步骤和逐分钟讲稿（含预期画面与提问应答）。
- `ProjDel3/evidence/`：80 项测试（六类，数量由 unittest 动态发现）、独立报表核对、真实终端和 SQL 日志。
- `ProjDel3/requirements.lock`：本机验证通过的精确依赖版本，容器镜像按此安装，用于逐位复现。
- `ProjDel3/web/` + `app.py --web`：课堂演示网页，与终端同源，默认仅监听 127.0.0.1（容器内由 `LAB_WEB_HOST` 放开映射）。
- `ProjDel3/start.sh`：唯一启动入口；`Dockerfile`、`docker-compose.yml`、`.dockerignore`、`.env.example`、`scripts/docker-entrypoint.sh` 固化运行环境与配置。

在 `ProjDel3` 目录运行 `sh start.sh` 即可；环境已就绪时直接启动，不重复安装依赖、不覆盖已有数据。自检与测试分别用 `sh start.sh check` / `sh start.sh test`；手工排障仍可用 `sh scripts/bootstrap.sh --check`，环境损坏时去掉 `--check` 重跑，bootstrap 优先使用 uv 并以 `--clear` 重建失效的 `.venv`。原第 1、第 2 次提交及个人作业文件均未改动。

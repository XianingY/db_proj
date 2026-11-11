# 第三次小组作业成果

- `ProjDel3.zip`：完整提交包，解压后进入 ProjDel3 目录。
- `ProjDel3/第三次小组作业报告.pdf`：18 页中文报告（含要求逐条对照表、14 外键关系一览、网页前端说明、英文摘要与十项 SQL 附录）。
- 同目录 `.docx`、`.md`：可编辑报告。
- `ProjDel3/README.md`：安装、初始化、启动与验证说明。
- `ProjDel3/scripts/bootstrap.sh`：一键准备 Python/PostgreSQL 环境、初始化并自检（幂等）。
- `ProjDel3/docs/demo_guide.md` 与 `demo_script.md`：现场演示步骤和逐分钟讲稿（含预期画面与提问应答）。
- `ProjDel3/evidence/`：74 项测试（六类，数量由 unittest 动态发现）、独立报表核对、真实终端和 SQL 日志。
- `ProjDel3/requirements.lock`：本机验证通过的精确依赖版本，用于逐位复现。
- `ProjDel3/web/` + `app.py --web`：课堂演示网页，与终端同源，仅监听 127.0.0.1。

在 `ProjDel3` 目录先跑 `sh scripts/bootstrap.sh --check` 自检；环境缺失时去掉 `--check` 重跑即可补装依赖、启动 PostgreSQL 并初始化。注意部分 macOS 上 Homebrew 的 `python3` 无法建 venv（pip 的 libexpat 符号缺失），bootstrap 会自动退回 uv。自检通过后运行 `.venv/bin/python app.py`。原第 1、第 2 次提交及个人作业文件均未改动。

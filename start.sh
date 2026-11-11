#!/bin/sh
# 仓库根目录转发入口；实现只有一份，位于 5/output/ProjDel3/start.sh。
# 下载 ProjDel3.zip 解压后，直接在 ProjDel3 目录运行 sh start.sh 即可。
exec sh "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/5/output/ProjDel3/start.sh" "$@"

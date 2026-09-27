#!/usr/bin/env bash
# =============================================================================
# start.sh —— PQKDS(Django) 容器启动脚本
# -----------------------------------------------------------------------------
# 职责：等待数据库就绪 → 执行迁移 → 启动 gunicorn
#
# 为什么要重试：
#   即使 compose 已用 `depends_on: mysql: condition: service_healthy` 约束，
#   仍可能出现健康检查刚通过、连接尚未完全可用，或数据库在迁移过程中重启
#   的情况。原实现是 `migrate && gunicorn` 一条命令，
#   一次失败即导致容器处于「运行但无表」的状态——
#   此时所有 PQKDS 接口都返回 500，且容器不会重启（命令已结束判定为失败后
#   由 restart: always 重启，但会形成快速重启循环）。
#
# 迁移失败必须视为致命错误：缺表的服务即使起来了也不可用，
# 这里选择退出让编排层重启，而不是带着残缺状态继续跑。
# =============================================================================
set -euo pipefail

cd /backend

DB_HOST="${DATABASE_HOST:-mysql}"
DB_PORT="${DATABASE_PORT:-3306}"
MAX_WAIT="${DB_WAIT_SECONDS:-180}"

# 就绪判定用 `manage.py check --database default`：
#   仅探测 TCP 端口是不够的——MySQL 进程已在监听、但目标库尚未创建时，
#   migrate 仍会以 (1049, "Unknown database ...") 失败。
#   Django 自身的 check 会真正建立到目标库的连接，因此能同时覆盖
#   「实例未就绪」与「库不存在」两种情况。
echo "[start] 等待数据库 ${DB_HOST}:${DB_PORT} 就绪（最多 ${MAX_WAIT}s）"

waited=0
until python manage.py check --database default >/dev/null 2>&1; do
    if [ "$waited" -ge "$MAX_WAIT" ]; then
        echo "[start] 错误：等待数据库超时（${MAX_WAIT}s），退出" >&2
        echo "[start] 提示：若为全新部署，请确认 MySQL 初始化脚本已创建目标库" >&2
        exit 1
    fi
    sleep 3
    waited=$((waited + 3))
    if [ $((waited % 15)) -eq 0 ]; then
        echo "[start] 仍在等待数据库… 已等待 ${waited}s"
    fi
done

echo "[start] 数据库已就绪（${waited}s），执行迁移"
python manage.py migrate --noinput

echo "[start] 迁移完成，启动 gunicorn"
exec gunicorn application.asgi:application -c gunicorn_conf.py

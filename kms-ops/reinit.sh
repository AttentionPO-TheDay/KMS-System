#!/bin/bash
# 重新导入初始化 SQL 到 kms 库。
#
# 本脚本修复了两个问题：
#   1. 口令改为从 MYSQL_ROOT_PASSWORD 读取，不再硬编码 root123456。
#   2. 原先引用了一个并不存在的 9_alter_permission_request_for_system_scope.sql，
#      导致脚本必然中途失败；现改为按 mysql/init/ 下实际存在的文件排序导入。
set -euo pipefail

DB_NAME="${MYSQL_DATABASE:-kms}"
DB_PASSWORD="${MYSQL_ROOT_PASSWORD:?必须设置 MYSQL_ROOT_PASSWORD}"

echo "Reinitializing DB: ${DB_NAME}"

shopt -s nullglob
files=(/docker-entrypoint-initdb.d/*.sql)
if [ ${#files[@]} -eq 0 ]; then
    echo "[ERROR] /docker-entrypoint-initdb.d 下没有 .sql 文件" >&2
    exit 1
fi

# 按文件名排序导入，保证与首次初始化顺序一致
IFS=$'\n' sorted=($(printf '%s\n' "${files[@]}" | sort))
unset IFS

for f in "${sorted[@]}"; do
    echo "  -> $(basename "$f")"
    mysql -uroot -p"${DB_PASSWORD}" --default-character-set=utf8mb4 "${DB_NAME}" < "$f"
done

echo "import complete"
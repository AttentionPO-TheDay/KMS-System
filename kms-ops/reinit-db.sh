#!/usr/bin/env bash
# =============================================================================
# reinit-db.sh —— **只**重新初始化数据库（kms + falcon_kds）
# -----------------------------------------------------------------------------
# 与 `rebuild-env.sh` 的区别（这是本脚本存在的理由）：
#   * `rebuild-env.sh` 会连 **Redis / Kafka / FISCO 链**一起清掉，并重跑
#     `build-local.sh`（Maven + npm + go 全量重建）。那是"换一台机器"级别的重置。
#   * 本脚本只动数据库：**链上历史、Redis、Kafka 全部保留**。
#     适合"数据被我改乱了、想回到干净的种子状态"，而不想丢链上存证、
#     也不想等二十分钟构建。
#
# 流程（顺序是刻意的）：
#   1. 等 MySQL 就绪
#   2. **DROP + CREATE 两个库** —— 不是逐个 DROP TABLE：后者会漏掉
#      迁移建的表、遗留视图与触发器，而"重置"的全部意义就是回到**已知**状态
#   3. 重放 `/docker-entrypoint-initdb.d/*.sql`（按文件名排序，与首次初始化同序）
#      ⚠️ `00_create_databases.sql` 会先 `CREATE DATABASE IF NOT EXISTS falcon_kds`
#      —— 它**不建 kms**（假设 MySQL 镜像已按 MYSQL_DATABASE 自动建好）。
#      所以第 2 步必须**两个库都自己建**，否则重放会以
#      "Unknown database 'kms'" 失败（reinit.sh 里遇到过同类失败模式）。
#   4. 重启 Django 容器 —— `start.sh` 会等库就绪并跑 `migrate --noinput`，
#      falcon_kds 的全部业务表（含最新的 0022/0023）由迁移在**空库**上建出来。
#      让容器自己迁移而不是在这里手跑 manage.py：迁移失败的可见性与
#      线上一致（容器退出并重启重试），而手跑会把失败留在本次 shell 里。
#
# ⚠️ 数据会**全部丢失**（kms 的用户/角色/菜单/操作日志，falcon_kds 的节点/
#    密钥/会话/授权）。链上历史仍在，但链上的 keyId 会指向 DB 里已不存在的行
#    —— 这是任何"只重置数据库"的固有代价，不是本脚本的缺陷。
#
# 幂等：可重复执行。
# =============================================================================
set -euo pipefail

# ⚠️ 本脚本就在 kms-ops/ 下，所以 compose 目录是**它自己所在目录** ——
#    多写一个 `/..` 会指到仓库根（那里没有 docker-compose.yml），
#    报的是 `no configuration file provided: not found`（实测踩到）。
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYSQL_CONTAINER="${MYSQL_CONTAINER:-kms_mysql}"
INIT_DIR="/docker-entrypoint-initdb.d"

echo "=========================================="
echo "  KMS 数据库重新初始化（只动数据库）"
echo "=========================================="

# ---- 1. 等 MySQL 就绪（带重试；容器刚起来时 mysqld 还在初始化） ----
echo "[INFO] 等待 MySQL 就绪…"
for i in $(seq 1 60); do
    if docker exec "$MYSQL_CONTAINER" sh -c 'mysqladmin ping -uroot -p"$MYSQL_ROOT_PASSWORD" --silent' >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 60 ]; then
        echo "[ERROR] MySQL 未在 120s 内就绪" >&2
        exit 1
    fi
    sleep 2
done
echo "[INFO] MySQL 已就绪"

# ---- 2. 重建两个库 ----
# ⚠️ 用完即删：SQL 里不出现明文口令，口令只经环境变量传给 mysql 客户端。
# ⚠️ heredoc 的定界符**必须加引号**（`<<"SQL"`）：不加的话容器里的 sh 会按
#    普通 heredoc 做展开，SQL 里的反引号会被当**命令替换**执行 ——
#    现象是 "kms: command not found"，而 `DROP DATABASE` 一个字都没跑，
#    接着重放旧脚本时会撞上一堆已存在的外键（实测踩到，且那次把 kms 库
#    丢在了"删了一半"的状态）。
echo "[INFO] 重建数据库 kms / falcon_kds（现有数据全部丢弃）…"
docker exec "$MYSQL_CONTAINER" sh -c '
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 <<"SQL"
DROP DATABASE IF EXISTS `kms`;
CREATE DATABASE `kms` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
DROP DATABASE IF EXISTS `falcon_kds`;
CREATE DATABASE `falcon_kds` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
SQL
' 2>&1 | grep -v "Using a password" || true

# ---- 3. 按文件名排序重放初始化 SQL ----
echo "[INFO] 重放 ${INIT_DIR}/*.sql …"
docker exec "$MYSQL_CONTAINER" sh -c '
set -e
for f in $(ls '"${INIT_DIR}"'/*.sql | sort); do
    echo "  -> $(basename "$f")"
    mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 kms < "$f"
done
' 2>&1 | grep -v "Using a password"

# ---- 4. 重启 Django：它自己跑 migrate（在空库上建全部业务表） ----
echo "[INFO] 重启 dvadmin3-django（start.sh 会等库就绪并执行 migrate）…"
( cd "$COMPOSE_DIR" && docker compose restart dvadmin3-django )

# 等迁移落定：表存在即认为完成。
echo "[INFO] 等待迁移完成…"
for i in $(seq 1 90); do
    if docker exec "$MYSQL_CONTAINER" sh -c '
        mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B -e \
          "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"falcon_kds\" AND table_name=\"dvadmin_pqkds_nodes\";" 2>/dev/null
    ' | grep -q '^1$'; then
        echo "[INFO] 迁移完成（dvadmin_pqkds_nodes 已建）"
        break
    fi
    if [ "$i" -eq 90 ]; then
        echo "[ERROR] 180s 内未看到迁移结果，请查：docker logs dvadmin3-django" >&2
        exit 1
    fi
    sleep 2
done

# ---- 5. 自检：新表与菜单都在 ----
echo "[INFO] 自检…"
docker exec "$MYSQL_CONTAINER" sh -c '
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --default-character-set=utf8mb4 -t -e "
SELECT
  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"kms\" AND table_name=\"sys_user\")            AS kms_sys_user,
  (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=\"falcon_kds\" AND table_name=\"dvadmin_pqkds_node_authorization_requests\") AS auth_req_table,
  (SELECT COUNT(*) FROM kms.sys_menu WHERE menu_id=9476)                                                          AS menu_9476,
  (SELECT COUNT(*) FROM kms.sys_role_menu WHERE role_id=2 AND menu_id=9476)                                       AS role2_9476,
  (SELECT COUNT(*) FROM kms.sys_user WHERE user_name=\"admin\")                                                    AS admin_user;
" kms' 2>&1 | grep -v "Using a password"

echo "[INFO] 数据库重新初始化完成。"
echo "[INFO] 后端容器日志尾部（确认迁移无异常）："
docker logs --tail 6 dvadmin3-django 2>&1 | sed 's/^/    /'

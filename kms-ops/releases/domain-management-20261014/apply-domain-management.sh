#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

sha256sum -c SHA256SUMS-domain-management
test -f docker-compose.yml
test -f docker-compose.fisco-enabled.yml
compose=(docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" ps --status running mysql
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -Nse "SELECT 1" kms' >/dev/null

stamp=$(date +%Y%m%d-%H%M%S)
backup="domain-management-backup-$stamp"
mkdir -m 700 "$backup"
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces --no-create-info --skip-triggers --replace kms sys_menu sys_role_menu --where="menu_id IN (9461,9470,9482)"' > "$backup/menu-rows.sql"
chmod 600 "$backup/menu-rows.sql"
docker tag kms-updatedel-java:local "kms-updatedel-java:before-domain-$stamp"
docker tag kms-gateway-nginx:local "kms-gateway-nginx:before-domain-$stamp"
printf 'Backup: %s; rollback image suffix: before-domain-%s\n' "$backup" "$stamp"

# 先校验镜像可载入，再执行幂等菜单迁移；任何一步失败都停止。
docker load -i kms-domain-management-images.tar.gz
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot kms' < 55_restore_domain_management.sql
"${compose[@]}" up -d --no-deps --force-recreate --no-build updatedel-java nginx
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot kms -e "SELECT menu_id,menu_name,icon,status FROM sys_menu WHERE menu_id IN (9461,9482);"'
"${compose[@]}" ps updatedel-java nginx
printf 'Update activated. Wait for Java readiness, run deploy.sh verify, then re-enter Demo admin and Ctrl+F5.\n'

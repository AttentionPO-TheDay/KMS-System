#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
sha256sum -c SHA256SUMS-domain-registry
test -f docker-compose.yml
test -f docker-compose.fisco-enabled.yml
compose=(docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -Nse "SELECT 1" falcon_kds' >/dev/null
stamp=$(date +%Y%m%d-%H%M%S)
backup="domain-registry-backup-$stamp"
mkdir -m 700 "$backup"
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces --no-create-info --skip-triggers --replace kms sys_menu sys_role_menu --where="menu_id IN (9453,9461,9470,9482)"' > "$backup/menu-rows.sql"
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot falcon_kds -e "SELECT id,node_id,domain_id FROM dvadmin_pqkds_nodes ORDER BY id"' > "$backup/node-domains.tsv"
chmod 600 "$backup"/*
for image in kms-dvadmin3-django kms-updatedel-java kms-gateway-nginx; do
  docker tag "$image:local" "$image:before-domain-registry-$stamp"
done
printf 'Backup: %s; rollback image suffix: before-domain-registry-%s\n' "$backup" "$stamp"
docker load -i kms-domain-registry-images.tar.gz
# 单独执行新增表与旧域回填；失败即停止，不改节点归属或历史分发快照。
"${compose[@]}" run --rm --no-deps -T dvadmin3-django python manage.py migrate --noinput
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot kms' < 55_restore_domain_management.sql
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot kms' < 56_domain_registry_cross_distribution.sql
"${compose[@]}" up -d --no-deps --force-recreate --no-build dvadmin3-django dvadmin3-key-reclaimer updatedel-java nginx
"${compose[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot falcon_kds -e "SELECT domain_id,name FROM dvadmin_pqkds_domains ORDER BY domain_id"'
"${compose[@]}" ps dvadmin3-django dvadmin3-key-reclaimer updatedel-java nginx
printf 'Wait for readiness, run deploy.sh verify, re-enter Demo and refresh browser.\n'

#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/group-agreement-20261014
cd "$release"
sha256sum -c SHA256SUMS
test ! -e backup-complete
cd /home/rbf/kms-sys
compose=(docker compose -p kms-ops -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
for image in kms-dvadmin3-django kms-gateway-nginx; do
  if docker image inspect "$image:before-group-agreement-20261014" >/dev/null 2>&1; then
    echo "Backup tag already exists, refusing overwrite" >&2
    exit 1
  fi
done
docker tag "$(docker inspect dvadmin3-django --format '{{.Image}}')" kms-dvadmin3-django:before-group-agreement-20261014
docker tag "$(docker inspect kms_gateway --format '{{.Image}}')" kms-gateway-nginx:before-group-agreement-20261014
cp docker-compose.yml docker-compose.fisco-enabled.yml "$release/"
docker exec kms_mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --events --all-databases' > "$release/database-before.sql"
test -s "$release/database-before.sql"
touch "$release/backup-complete"
cd "$release"
mkdir source
tar -xzf source.tar.gz -C source
cp backend.Dockerfile frontend.Dockerfile source/
docker build --pull=false -f source/backend.Dockerfile -t kms-dvadmin3-django:group-agreement-20261014 source
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:group-agreement-20261014 source
docker run --rm --network none --entrypoint python kms-dvadmin3-django:group-agreement-20261014 -m compileall -q /backend/pqkds/group_agreement_service.py /backend/pqkds/group_agreement_views.py
cd /home/rbf/kms-sys
docker tag kms-dvadmin3-django:group-agreement-20261014 kms-dvadmin3-django:local
docker tag kms-gateway-nginx:group-agreement-20261014 kms-gateway-nginx:local
"${compose[@]}" stop dvadmin3-key-reclaimer
"${compose[@]}" run --rm --no-deps -T dvadmin3-django python manage.py migrate --noinput
"${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django dvadmin3-key-reclaimer nginx
"${compose[@]}" ps dvadmin3-django dvadmin3-key-reclaimer nginx

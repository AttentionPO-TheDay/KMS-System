#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/node-permission-20261015
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
test ! -e source
compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
test "$(docker inspect kms_gateway --format '{{.Image}}')" = 'sha256:b835bb32a1bc2e9dc1b83da0fbe81bbc39be811c482ca1a8f7d42a2259bbaea4'
test "$(docker inspect dvadmin3-django --format '{{.Image}}')" = 'sha256:9205076241361070ca9c20cd7168e0c0a51d2cb594e43eed9497c2b08b235eda'
backend_backup=kms-dvadmin3-django:before-node-permission-20261015
frontend_backup=kms-gateway-nginx:before-node-permission-20261015
for image in "$backend_backup" "$frontend_backup"; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo 'Backup tag exists; refusing overwrite' >&2
    exit 1
  fi
done
services=(kms_generate_java kms_updatedel_java kms_acceptance_backend kms_mysql kms_redis kms-ops-dvadmin3-key-reclaimer-1)
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-before.txt
docker tag "$(docker inspect dvadmin3-django --format '{{.Image}}')" "$backend_backup"
docker tag "$(docker inspect kms_gateway --format '{{.Image}}')" "$frontend_backup"
mkdir -p source/dist
tar -xzf frontend.tar.gz -C source/dist
tar -xzf backend.tar.gz -C source
cp backend.Dockerfile frontend.Dockerfile source/
docker build --pull=false -f source/backend.Dockerfile -t kms-dvadmin3-django:node-permission-20261015 source
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:node-permission-20261015 source
# No production settings, network, database or cryptographic materials in tests.
docker run --rm --network none --entrypoint python kms-dvadmin3-django:node-permission-20261015 /backend/tests/test_node_distribution_permissions_offline.py
docker run --rm --network none --entrypoint python kms-dvadmin3-django:node-permission-20261015 -m compileall -q /backend/pqkds/api_contract.py /backend/pqkds/node_self_views.py
rollback() {
  echo 'Deployment failed; restoring both application images' >&2
  docker tag "$backend_backup" kms-dvadmin3-django:local
  docker tag "$frontend_backup" kms-gateway-nginx:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django nginx
}
trap rollback ERR
docker tag kms-dvadmin3-django:node-permission-20261015 kms-dvadmin3-django:local
docker tag kms-gateway-nginx:node-permission-20261015 kms-gateway-nginx:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django nginx
ready=false
for attempt in $(seq 1 20); do
  code=$(curl -sk -o backend-readiness.json -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/demo-api/pqkds/node-self/ || true)
  if [ "$code" = 401 ] && grep -q 'DEMO_CONTEXT_STALE' backend-readiness.json; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker exec kms_gateway nginx -t
expected=$(sha256sum source/dist/index.html | cut -d ' ' -f 1)
actual=$(docker exec kms_gateway sha256sum /usr/share/nginx/html/updatedel/index.html | cut -d ' ' -f 1)
test "$actual" = "$expected"
curl -fsk --max-time 10 https://10.112.125.22:8443/updatedel/demo -o served-index.html
test "$(sha256sum served-index.html | cut -d ' ' -f 1)" = "$expected"
for file in api_contract.py node_self_views.py; do
  candidate=$(sha256sum "source/pqkds/$file" | cut -d ' ' -f 1)
  running=$(docker exec dvadmin3-django sha256sum "/backend/pqkds/$file" | cut -d ' ' -f 1)
  test "$candidate" = "$running"
done
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-after.txt
cmp services-before.txt services-after.txt
touch applied
trap - ERR
printf 'DEPLOY_OK index_sha256=%s database_migrations=none node_levels_unchanged=true\n' "$expected"
"${compose[@]}" ps dvadmin3-django nginx

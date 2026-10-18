#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/pool-sender-falcon-20261015-1807
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
test ! -e source
compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
test "$(docker inspect kms_gateway --format '{{.Image}}')" = 'sha256:9827f45443babdeacb320d704f1c821e8cddabe7d4c7888c2b29aec6f1c83be9'
test "$(docker inspect dvadmin3-django --format '{{.Image}}')" = 'sha256:3642835719088be746b5d3f52704358cc270fd23b8fa1006b01bb8fe9cee921e'
backend_backup=kms-dvadmin3-django:before-pool-sender-falcon-20261015-1807
frontend_backup=kms-gateway-nginx:before-pool-sender-falcon-20261015-1807
for image in "$backend_backup" "$frontend_backup"; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo 'Backup tag exists; refusing overwrite' >&2
    exit 1
  fi
done
services=(kms_generate_java kms_updatedel_java kms_acceptance_backend kms_mysql kms_redis)
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-before.txt
docker tag "$(docker inspect dvadmin3-django --format '{{.Image}}')" "$backend_backup"
docker tag "$(docker inspect kms_gateway --format '{{.Image}}')" "$frontend_backup"
mkdir -p source/dist
tar -xzf frontend.tar.gz -C source/dist
tar -xzf backend.tar.gz -C source
cp backend.Dockerfile frontend.Dockerfile source/
docker build --pull=false -f source/backend.Dockerfile -t kms-dvadmin3-django:pool-sender-falcon-20261015-1807 source
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:pool-sender-falcon-20261015-1807 source
docker run --rm --network none --entrypoint python kms-dvadmin3-django:pool-sender-falcon-20261015-1807 /backend/tests/test_pool_sender_material_offline.py
docker run --rm --network none --entrypoint python kms-dvadmin3-django:pool-sender-falcon-20261015-1807 -m compileall -q /backend/pqkds/serializers.py /backend/pqkds/views.py /backend/pqkds/node_self_views.py /backend/pqkds/pool_consume_service.py /backend/pqkds/key_pool_service.py
rollback() {
  echo 'Deployment failed; restoring both previous application images' >&2
  docker tag "$backend_backup" kms-dvadmin3-django:local
  docker tag "$frontend_backup" kms-gateway-nginx:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django nginx
}
trap rollback ERR
docker tag kms-dvadmin3-django:pool-sender-falcon-20261015-1807 kms-dvadmin3-django:local
docker tag kms-gateway-nginx:pool-sender-falcon-20261015-1807 kms-gateway-nginx:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django nginx
ready=false
for attempt in $(seq 1 20); do
  code=$(curl -sk -o backend-readiness.json -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/demo-api/pqkds/node-self/ || true)
  if [ "$code" = 401 ] && grep -q 'DEMO_CONTEXT_STALE' backend-readiness.json; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker exec kms_gateway nginx -t
expected=6e6c1faf54a435bcd307f3e4bbdb2cc6dc5c341f708ae4b52c398546229b777e
test "$(sha256sum source/dist/index.html | cut -d ' ' -f 1)" = "$expected"
actual=$(docker exec kms_gateway sha256sum /usr/share/nginx/html/updatedel/index.html | cut -d ' ' -f 1)
test "$actual" = "$expected"
curl -fsk --max-time 10 https://10.112.125.22:8443/updatedel/demo -o served-index.html
test "$(sha256sum served-index.html | cut -d ' ' -f 1)" = "$expected"
for file in serializers.py views.py node_self_views.py pool_consume_service.py key_pool_service.py; do
  candidate=$(sha256sum "source/pqkds/$file" | cut -d ' ' -f 1)
  running=$(docker exec dvadmin3-django sha256sum "/backend/pqkds/$file" | cut -d ' ' -f 1)
  test "$candidate" = "$running"
done
docker exec -i dvadmin3-django python manage.py shell < verify-live.py > live-readiness.txt
grep 'FALCON_READY_OK' live-readiness.txt
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-after.txt
cmp services-before.txt services-after.txt
touch applied
trap - ERR
printf 'DEPLOY_OK index_sha256=%s database_migrations=none\n' "$expected"
"${compose[@]}" ps dvadmin3-django nginx

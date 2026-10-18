#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/technical-operation-linked-20261015-1712
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
test ! -e source
compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
test "$(docker inspect kms_gateway --format '{{.Image}}')" = 'sha256:b4ea064cbcddc4b4bb7bb1e3ca48952e4cd29c2c7c2f50ede0d8d3a6c4917ad9'
backup=kms-gateway-nginx:before-technical-operation-linked-20261015-1712
if docker image inspect "$backup" >/dev/null 2>&1; then
  echo 'Backup image tag exists; refusing overwrite' >&2
  exit 1
fi
services=(dvadmin3-django kms_generate_java kms_updatedel_java kms_acceptance_backend kms_mysql kms_redis)
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-before.txt
docker tag "$(docker inspect kms_gateway --format '{{.Image}}')" "$backup"
mkdir -p source/dist
tar -xzf frontend.tar.gz -C source/dist
cp frontend.Dockerfile source/
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:technical-operation-linked-20261015-1712 source
rollback() {
  echo 'Deployment failed; restoring previous gateway image' >&2
  docker tag "$backup" kms-gateway-nginx:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
}
trap rollback ERR
docker tag kms-gateway-nginx:technical-operation-linked-20261015-1712 kms-gateway-nginx:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
ready=false
for attempt in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/updatedel/demo || true)
  if [ "$code" = 200 ]; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker exec kms_gateway nginx -t
expected=e5a7cab019410576e51b6d149ed85460e26f56fb4c336ecd265cab4a52dc4881
test "$(sha256sum source/dist/index.html | cut -d ' ' -f 1)" = "$expected"
actual=$(docker exec kms_gateway sha256sum /usr/share/nginx/html/updatedel/index.html | cut -d ' ' -f 1)
test "$expected" = "$actual"
curl -fsk --max-time 10 https://10.112.125.22:8443/updatedel/demo -o served-index.html
test "$(sha256sum served-index.html | cut -d ' ' -f 1)" = "$expected"
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-after.txt
cmp services-before.txt services-after.txt
touch applied
trap - ERR
printf 'DEPLOY_OK index_sha256=%s backend_containers_unchanged=true\n' "$expected"
"${compose[@]}" ps nginx

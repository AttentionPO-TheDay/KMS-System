#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/auth-approval-toast-20261015
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
test ! -e source
compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
test "$(docker inspect kms_gateway --format '{{.Image}}')" = 'sha256:093c0d3fc756eff74df2157575fdcaa30be77f7cce99fe39fd95396ac4a6344f'
if docker image inspect kms-gateway-nginx:before-auth-approval-toast-20261015 >/dev/null 2>&1; then
  echo 'Backup image tag exists; refusing overwrite' >&2
  exit 1
fi
services=(dvadmin3-django kms_generate_java kms_updatedel_java kms_acceptance_backend kms_mysql kms_redis)
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-before.txt
docker tag "$(docker inspect kms_gateway --format '{{.Image}}')" kms-gateway-nginx:before-auth-approval-toast-20261015
mkdir -p source/dist
tar -xzf frontend.tar.gz -C source/dist
cp frontend.Dockerfile source/
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:auth-approval-toast-20261015 source
rollback() {
  echo 'Deployment failed; restoring previous gateway image' >&2
  docker tag kms-gateway-nginx:before-auth-approval-toast-20261015 kms-gateway-nginx:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
}
trap rollback ERR
docker tag kms-gateway-nginx:auth-approval-toast-20261015 kms-gateway-nginx:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
ready=false
for attempt in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/updatedel/demo || true)
  if [ "$code" = 200 ]; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker exec kms_gateway nginx -t
expected=$(sha256sum source/dist/index.html | cut -d ' ' -f 1)
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

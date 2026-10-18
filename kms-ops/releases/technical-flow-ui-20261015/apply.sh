#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/technical-flow-ui-20261015
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
if docker image inspect kms-gateway-nginx:before-technical-flow-ui-20261015 >/dev/null 2>&1; then
  echo 'Backup tag already exists; refusing overwrite' >&2
  exit 1
fi
docker tag "$(docker inspect kms_gateway --format '{{.Image}}')" kms-gateway-nginx:before-technical-flow-ui-20261015
mkdir source
tar -xzf frontend.tar.gz -C source
cp frontend.Dockerfile source/
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:technical-flow-ui-20261015 source
rollback() {
  echo 'Deployment failed; restoring previous gateway image' >&2
  docker tag kms-gateway-nginx:before-technical-flow-ui-20261015 kms-gateway-nginx:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
}
trap rollback ERR
docker tag kms-gateway-nginx:technical-flow-ui-20261015 kms-gateway-nginx:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
ready=false
for attempt in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/updatedel/demo || true)
  if [ "$code" = 200 ]; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker exec kms_gateway nginx -t
docker exec kms_gateway sha256sum /usr/share/nginx/html/updatedel/index.html
sha256sum source/dist/index.html
touch applied
trap - ERR
"${compose[@]}" ps nginx

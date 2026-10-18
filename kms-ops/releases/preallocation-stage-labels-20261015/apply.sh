#!/usr/bin/env bash
set -euo pipefail
umask 077

release=/home/rbf/kms-sys/releases/preallocation-stage-labels-20261015
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
test ! -e source

expected_base=sha256:f375f66364f241393a5d280e6a46b8dcd3d54cbb6f7590644a3c3f41229f0d3b
test "$(docker inspect kms_gateway --format '{{.Image}}')" = "$expected_base"
test "$(docker image inspect kms-gateway-nginx:technical-operation-linked-20261015-1712 --format '{{.Id}}')" = "$expected_base"

compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
backup=kms-gateway-nginx:before-preallocation-stage-labels-20261015
if docker image inspect "$backup" >/dev/null 2>&1; then
  echo 'Backup image tag already exists' >&2
  exit 1
fi

services=(dvadmin3-django kms_generate_java kms_updatedel_java kms_acceptance_backend kms_mysql kms_redis)
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-before.txt
docker tag "$expected_base" "$backup"
mkdir -p source/overlay
tar -xzf frontend-overlay.tar.gz -C source/overlay
cp frontend.Dockerfile source/
docker build --pull=false -f source/frontend.Dockerfile -t kms-gateway-nginx:preallocation-stage-labels-20261015 source

rollback() {
  echo 'Deployment failed; restoring previous gateway image' >&2
  docker tag "$backup" kms-gateway-nginx:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate nginx
}
trap rollback ERR
docker tag kms-gateway-nginx:preallocation-stage-labels-20261015 kms-gateway-nginx:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate nginx

ready=false
for attempt in $(seq 1 10); do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/updatedel/demo || true)
  if [ "$code" = 200 ]; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker exec kms_gateway nginx -t

index_expected=$(sha256sum source/overlay/index.html | cut -d ' ' -f 1)
index_actual=$(docker exec kms_gateway sha256sum /usr/share/nginx/html/updatedel/index.html | cut -d ' ' -f 1)
test "$index_expected" = "$index_actual"
curl -fsk --max-time 10 https://10.112.125.22:8443/updatedel/demo -o served-index.html
test "$(sha256sum served-index.html | cut -d ' ' -f 1)" = "$index_expected"

asset=assets/index-BWYR-UWD-labels20261015.js
asset_expected=$(sha256sum "source/overlay/$asset" | cut -d ' ' -f 1)
asset_actual=$(docker exec kms_gateway sha256sum "/usr/share/nginx/html/updatedel/$asset" | cut -d ' ' -f 1)
test "$asset_expected" = "$asset_actual"
curl -fsk --max-time 10 "https://10.112.125.22:8443/updatedel/$asset" -o served-stage.js
test "$(sha256sum served-stage.js | cut -d ' ' -f 1)" = "$asset_expected"

docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-after.txt
cmp services-before.txt services-after.txt
touch applied
trap - ERR
printf 'DEPLOY_OK index_sha256=%s stage_sha256=%s backend_containers_unchanged=true\n' "$index_expected" "$asset_expected"
"${compose[@]}" ps nginx

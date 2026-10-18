#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=/home/rbf/kms-sys
release=$root/releases/django-chain-write-20261015
cd "$release"
sha256sum -c SHA256SUMS
test ! -e applied
test -f "$root/docker-compose.fisco-enabled.yml"
test ! -L "$root/docker-compose.fisco-enabled.yml"
test "$(sha256sum "$root/docker-compose.fisco-enabled.yml" | cut -d ' ' -f 1)" = 25f1471bbd571e99b55d8348f707f28629cb64b3d65d1c155710480231cb016b
test "$(docker inspect dvadmin3-django --format '{{.Image}}')" = sha256:000f8defdbbee76cb2d12c6b52c79676f173f12b8ffb1f10a9aa9bdd49cd4e11
python3 validate-config.py
compose=(docker compose -p kms-ops -f "$root/docker-compose.yml" -f "$root/docker-compose.fisco-enabled.yml" --profile fabric-did)
services=(kms_gateway kms_generate_java kms_updatedel_java kms_acceptance_backend kms_mysql kms_redis kms-ops-dvadmin3-key-reclaimer-1)
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-before.txt
if [ -e docker-compose.fisco-enabled.before.yml ]; then
  cmp "$root/docker-compose.fisco-enabled.yml" docker-compose.fisco-enabled.before.yml
else
  cp -p "$root/docker-compose.fisco-enabled.yml" docker-compose.fisco-enabled.before.yml
fi
# The host config is root-owned. Mount only the exact source and target files;
# never expose a host directory to the deployment helper.
install_override() {
  docker run --rm --network none --user 0:0 \
    --mount "type=bind,src=$release/$1,dst=/source.yml,readonly" \
    --mount "type=bind,src=$root/docker-compose.fisco-enabled.yml,dst=/target.yml" \
    --entrypoint python kms-dvadmin3-django:local \
    -c 'import shutil; shutil.copyfile("/source.yml", "/target.yml")'
}
rollback() {
  echo 'Deployment failed; restoring original Compose override' >&2
  install_override docker-compose.fisco-enabled.before.yml
  "${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django
}
trap rollback ERR
install_override docker-compose.fisco-enabled.yml
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-deps --no-build --force-recreate dvadmin3-django
test "$(docker exec dvadmin3-django printenv KMS_CHAIN_WRITES_ENABLED)" = true
test "$(docker inspect dvadmin3-django --format '{{.Image}}')" = sha256:000f8defdbbee76cb2d12c6b52c79676f173f12b8ffb1f10a9aa9bdd49cd4e11
ready=false
for attempt in $(seq 1 20); do
  code=$(curl -sk -o readiness.json -w '%{http_code}' --max-time 5 https://10.112.125.22:8443/demo-api/pqkds/node-self/ || true)
  if [ "$code" = 401 ] && grep -q DEMO_CONTEXT_STALE readiness.json; then ready=true; break; fi
  sleep 2
done
test "$ready" = true
docker inspect "${services[@]}" --format '{{.Name}} {{.Id}} {{.State.StartedAt}}' > services-after.txt
cmp services-before.txt services-after.txt
touch applied
trap - ERR
echo 'DEPLOY_OK: Django chain writes enabled; image unchanged; other services unchanged; no key update or migration performed'

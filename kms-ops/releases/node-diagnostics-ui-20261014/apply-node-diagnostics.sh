#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
sha256sum -c SHA256SUMS-node-diagnostics
test -f docker-compose.yml
test -f docker-compose.fisco-enabled.yml
compose=(docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did)
# Requires the previously deployed domain-registry release; do not silently migrate here.
"${compose[@]}" exec -T dvadmin3-django python manage.py shell -c 'from pqkds.models import Domain; Domain.objects.exists()'
stamp=$(date +%Y%m%d-%H%M%S)
for image in kms-dvadmin3-django kms-gateway-nginx; do
  docker tag "$image:local" "$image:before-node-diagnostics-$stamp"
done
printf 'Rollback image suffix: before-node-diagnostics-%s\n' "$stamp"
docker load -i kms-node-diagnostics-images.tar.gz
"${compose[@]}" up -d --no-deps --force-recreate --no-build dvadmin3-django dvadmin3-key-reclaimer nginx
"${compose[@]}" ps dvadmin3-django dvadmin3-key-reclaimer nginx
printf 'Wait for readiness, run bash deploy.sh verify, then refresh the browser.\n'

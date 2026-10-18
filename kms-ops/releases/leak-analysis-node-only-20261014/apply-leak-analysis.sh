#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
sha256sum -c SHA256SUMS-leak-analysis
test -f docker-compose.yml
test -f docker-compose.fisco-enabled.yml
compose=(docker compose -f docker-compose.yml -f docker-compose.fisco-enabled.yml --profile fabric-did)
stamp=$(date +%Y%m%d-%H%M%S)
docker tag kms-gateway-nginx:local "kms-gateway-nginx:before-leak-analysis-$stamp"
printf 'Rollback tag: kms-gateway-nginx:before-leak-analysis-%s\n' "$stamp"
docker load -i kms-leak-analysis-nginx.tar.gz
"${compose[@]}" up -d --no-deps --force-recreate --no-build nginx
"${compose[@]}" ps nginx
printf 'Run bash deploy.sh verify, then refresh the browser with Ctrl+F5.\n'

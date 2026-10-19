#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/did-syspid-20261019
cd "$release"
test "$(pwd -P)" = "$release"
test ! -e applied
test ! -e backup
test ! -e payload
sha256sum -c SHA256SUMS
test "$(sha256sum zulu8.56.0.21-ca-jre8.0.302-linux_x64.tar.gz | cut -d ' ' -f 1)" = 9a0d0eb753c3592faca48d5e9b84bcf5b92301fd09081b191623cb8e478349d7
mkdir payload
tar -xzf payload.tar.gz -C payload
compose=(docker compose -p kms-ops -f /home/rbf/kms-sys/docker-compose.yml -f /home/rbf/kms-sys/docker-compose.fisco-enabled.yml --profile fabric-did)
"${compose[@]}" config --quiet
mkdir -m 700 backup
python3 check_deployment.py before
previous=kms-fabric-did:before-syspid-20261019
candidate=kms-fabric-did:syspid-20261019
if docker image inspect "$previous" >/dev/null 2>&1; then
  echo 'Refusing to overwrite rollback image' >&2
  exit 1
fi
docker tag "$(docker inspect kms_fabric_did --format '{{.Image}}')" "$previous"
docker build --pull=false --build-arg "BASE_IMAGE=$previous" -t "$candidate" .
docker run --rm --network none --entrypoint java "$candidate" -version
docker run --rm --network none --entrypoint java -v "$release/payload/offline-tests:/offline-tests:ro" "$candidate" \
  -cp '/offline-tests/classes:/offline-tests/junit.jar:/offline-tests/hamcrest.jar:/opt/kms-fabric-did/target/kms-fabric-did-1.0.0.jar:/opt/kms-fabric-did/target/lib/*' \
  org.junit.runner.JUnitCore com.kms.fabricdid.BridgeOfflineTest com.kms.fabricdid.SdkDiagnosticsTest
python3 -m unittest discover -s payload/module/tools -p 'test_*.py' -v
rollback() {
  trap - ERR
  echo 'DID deployment verification failed; restoring previous image' >&2
  docker tag "$previous" kms-fabric-did:local
  "${compose[@]}" up -d --no-deps --no-build --force-recreate fabric-did-bridge
}
trap rollback ERR
docker tag "$candidate" kms-fabric-did:local
"${compose[@]}" up -d --no-deps --no-build --force-recreate fabric-did-bridge
python3 check_deployment.py after
touch applied
trap - ERR
"${compose[@]}" ps fabric-did-bridge

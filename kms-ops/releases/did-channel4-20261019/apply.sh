#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/home/rbf/kms-sys/releases/did-channel4-20261019
base=/home/rbf/kms-sys
secrets=$base/fabric-did-secrets/syspid-yunId-channel4
cd "$release"
test "$(pwd -P)" = "$release"
test ! -e applied
test ! -e backup
test ! -e payload
test ! -e "$secrets"
test ! -e "$base/docker-compose.did-channel4.yml"
sha256sum -c SHA256SUMS
mkdir -m 700 backup
python3 check_deployment.py before
mkdir -m 700 payload "$secrets"
tar -xzf payload.tar.gz -C payload
tar -xzf identity.tar.gz -C "$secrets"
find "$secrets" -type d -exec chmod 700 {} +
find "$secrets" -type f -exec chmod 600 {} +
mkdir -p "$secrets/work"
chmod 700 "$secrets/work"
cp fabric.config.properties "$secrets/fabric.config.properties"
previous=kms-fabric-did:before-channel4-20261019
candidate=kms-fabric-did:channel4-20261019
if docker image inspect "$previous" >/dev/null 2>&1; then
  echo 'Refusing to overwrite rollback image' >&2
  exit 1
fi
docker tag "$(docker inspect kms_fabric_did --format '{{.Image}}')" "$previous"
docker build --pull=false --build-arg "BASE_IMAGE=$previous" -t "$candidate" .
docker run --rm --network none --entrypoint java -v "$release/payload/offline-tests:/offline-tests:ro" "$candidate" \
  -cp '/offline-tests/classes:/offline-tests/junit.jar:/offline-tests/hamcrest.jar:/opt/kms-fabric-did/target/kms-fabric-did-1.0.0.jar:/opt/kms-fabric-did/target/lib/*' \
  org.junit.runner.JUnitCore com.kms.fabricdid.BridgeOfflineTest com.kms.fabricdid.SdkDiagnosticsTest com.kms.fabricdid.PrepareSysPidRuntimeTest com.kms.fabricdid.CreatorIdentityTest
python3 -m unittest discover -s payload/module/tools -p 'test_*.py'
changed=0
canary=0
compose=(docker compose -p kms-ops -f "$base/docker-compose.yml" -f "$base/docker-compose.fisco-enabled.yml")
rollback() {
  trap - ERR
  if test "$canary" = 1; then docker stop kms_did_channel4_canary >/dev/null 2>&1 || true; fi
  if test "$changed" = 1; then
    echo 'DID deployment failed; restoring previous image and disabled configuration' >&2
    docker tag "$previous" kms-fabric-did:local
    if test -e "$base/docker-compose.did-channel4.yml"; then mv "$base/docker-compose.did-channel4.yml" "$release/backup/failed-override.yml"; fi
    "${compose[@]}" --profile fabric-did up -d --no-deps --no-build --force-recreate fabric-did-bridge
  fi
}
trap rollback ERR
docker run -d --rm --name kms_did_channel4_canary --network kms-ops_kms_net --env-file backup/canary.env \
  -v "$secrets:/run/fabric-did:ro" -v "$secrets/work:/run/fabric-did/work:rw" -v "$secrets/records:/run/fabric-did/records:rw" "$candidate"
canary=1
python3 check_deployment.py canary
docker stop kms_did_channel4_canary >/dev/null
canary=0
cp docker-compose.did-channel4.yml "$base/docker-compose.did-channel4.yml"
"${compose[@]}" -f "$base/docker-compose.did-channel4.yml" --profile fabric-did config --quiet
changed=1
docker tag "$candidate" kms-fabric-did:local
"${compose[@]}" -f "$base/docker-compose.did-channel4.yml" --profile fabric-did up -d --no-deps --no-build --force-recreate fabric-did-bridge
python3 check_deployment.py after
python3 query_confirmed.py --save
touch applied
trap - ERR

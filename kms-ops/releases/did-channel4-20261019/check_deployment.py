"""Release checks: private service, read-only ledger access, original transaction, other services unchanged."""
import hashlib
import json
from pathlib import Path
import ssl
import sys
import time
import urllib.error
import urllib.request
from query_confirmed import command, container, environment, request, query

ROOT = Path(__file__).resolve().parent
BASE = Path("/home/rbf/kms-sys")
COMPOSE = ["docker", "compose", "-p", "kms-ops", "-f", str(BASE / "docker-compose.yml"),
           "-f", str(BASE / "docker-compose.fisco-enabled.yml")]
FLAGS = ("KMS_CHAIN_WRITES_ENABLED", "FABRIC_DID_WRITE_ENABLED", "FABRIC_DID_CREATE_POLICY_APPROVED")
EXPECTED = {"FABRIC_DID_ENABLED": "true", "FABRIC_DID_CHAIN_ID": "vendor-didchannel4",
            "FABRIC_DID_METHOD_ID": "yunId", "FABRIC_DID_SYSPID_RECORDS_DIR": "/run/fabric-did/records",
            **{key: "false" for key in FLAGS}}


def others():
    ids = command("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=kms-ops").decode().split()
    items = json.loads(command("docker", "inspect", *ids))
    return {c["Name"]: {"id": c["Id"], "startedAt": c["State"]["StartedAt"], "state": c["State"]["Status"]}
            for c in items if c["Name"] != "/kms_fabric_did"}


def wait_ready(item):
    for attempt in range(30):
        try:
            code, response = request(item, "/health", authenticated=False)
            if code == 200:
                data = response["data"]
                assert data["status"] == "READY_READ_ONLY", "DID not ready for read-only access"
                assert data["writeEnabled"] is False
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise RuntimeError("DID_READINESS_TIMEOUT")


def check_service(item):
    env = environment(item)
    assert all(env.get(k) == v for k, v in EXPECTED.items())
    assert not item["HostConfig"]["PortBindings"], "DID must not publish a host port"
    wait_ready(item)
    result = query(item)
    code, response = request(item, "/internal/fabric-did/sys-pids/verify", {"sysPid": "00"}, authenticated=False)
    assert code == 401, "Internal authentication gate failed"
    code, response = request(item, "/internal/fabric-did/sys-pids/onchain", {"sysPid": "00"})
    assert code == 503 and response["data"]["errorCode"] == "CHAIN_WRITES_PAUSED"
    return result


def main():
    action = sys.argv[1]
    if action == "before":
        item = container()
        env = environment(item)
        assert all(env.get(k) == "false" for k in (*FLAGS, "FABRIC_DID_ENABLED"))
        assert not item["HostConfig"]["PortBindings"]
        assert not (BASE / "docker-compose.did-channel4.yml").exists(), "Override already exists"
        desired = json.loads(command(*COMPOSE, "--profile", "fabric-did", "config", "--format", "json"))
        assert desired["services"]["fabric-did-bridge"]["image"] == "kms-fabric-did:local"
        snapshot = {"did": item, "otherServices": others()}
        backup = ROOT / "backup" / "snapshot.json"
        backup.write_text(json.dumps(snapshot), encoding="utf-8"); backup.chmod(0o600)
        # Only the private canary receives these values; never put them in Docker build context or stdout.
        canary_env = {k: v for k, v in env.items() if k.startswith("FABRIC_DID_") or k in (*FLAGS, "INTERNAL_TOKEN")}
        canary_env.update(EXPECTED)
        path = ROOT / "backup" / "canary.env"
        path.write_text("".join(k + "=" + v + "\n" for k, v in canary_env.items()), encoding="utf-8"); path.chmod(0o600)
        print("PRECHECK_OK other_services=" + str(len(snapshot["otherServices"])))
        return
    if action == "canary":
        result = check_service(container("kms_did_channel4_canary"))
        print("CANARY_OK status=" + result["status"] + " transactionValid=true metadataMatches=true writes_disabled=true")
        return
    assert action == "after"
    item = container()
    before = json.loads((ROOT / "backup" / "snapshot.json").read_text(encoding="utf-8"))
    assert others() == before["otherServices"], "Another KMS service changed"
    assert item["Id"] != before["did"]["Id"]
    assert environment(item)["INTERNAL_TOKEN"] == environment(before["did"])["INTERNAL_TOKEN"]
    expected_image = command("docker", "image", "inspect", "kms-fabric-did:channel4-20261019", "--format", "{{.Id}}").decode().strip()
    assert item["Image"] == expected_image
    mounts = {m["Destination"]: m for m in item["Mounts"]}
    secrets = str(BASE / "fabric-did-secrets" / "syspid-yunId-channel4")
    assert mounts["/run/fabric-did"]["Source"] == secrets and not mounts["/run/fabric-did"]["RW"]
    for name in ("records", "work"):
        assert mounts["/run/fabric-did/" + name]["Source"] == secrets + "/" + name and mounts["/run/fabric-did/" + name]["RW"]
    result = check_service(item)
    jar = "/opt/kms-fabric-did/target/kms-fabric-did-1.0.0.jar"
    actual = command("docker", "exec", "kms_fabric_did", "sha256sum", jar).decode().split()[0]
    assert actual == hashlib.sha256((ROOT / "payload/module/target/kms-fabric-did-1.0.0.jar").read_bytes()).hexdigest()
    cert = command("docker", "exec", "kms_gateway", "cat", "/run/kms-server-tls/server.crt").decode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context(cadata=cert)))
    for path in ("/ping", "/updatedel/demo", "/acceptance/"):
        with opener.open("https://10.112.125.22:8443" + path, timeout=10) as response:
            assert response.status == 200
    print("DEPLOY_OK status=" + result["status"] + " writes_disabled=true auth_gate=true tls_pages=200 other_services_unchanged=true")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("DEPLOY_CHECK_FAILED type=" + type(error).__name__ + " detail="
              + (str(error) if isinstance(error, (AssertionError, RuntimeError)) else "see protected diagnostics"), file=sys.stderr)
        sys.exit(1)
